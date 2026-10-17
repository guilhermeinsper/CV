"""Contingência: o PRÓPRIO PAINEL põe o próximo lote na fila a cada X minutos, a partir de listas/*.txt,
sem depender do Claude nem do ChatGPT. Só age quando a fila está vazia e nada está rodando.

Liga/desliga e quantidades em config.json → "auto_lote": {"ativo": true, "intervalo_min": 60, ...}.
Registro de tudo em logs/auto_lote.txt.
Regras de segurança: não enfileira Reddit; se o TikTok começar a recusar downloads (403/bloqueio/login/captcha),
para de enfileirar TikTok até a próxima verificação sem bloqueio.
"""
import json, re, time
from datetime import datetime, timedelta, timezone
from . import config as C, db, texto, fila

PADRAO = {"ativo": True, "intervalo_min": 60, "tiktok": 12, "youtube": 3, "texto": 4}
SINAIS_BLOQUEIO = ("403", "forbidden", "captcha", "blocked", "log in", "login", "rate", "429")


def cfg():
    k = dict(PADRAO)
    k.update(C.config().get("auto_lote") or {})
    return k


def _estado_arq():
    return C.DADOS / "auto_lote_estado.json"


def _log(msg):
    C.LOGS.mkdir(parents=True, exist_ok=True)
    with open(C.LOGS / "auto_lote.txt", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def tipo(u):
    l = u.lower()
    if "reddit.com" in l:
        return None
    if "tiktok.com" in l:
        return "tiktok" if "/video/" in l else None
    if "youtube.com" in l or "youtu.be" in l:
        return "youtube"
    return "texto" if texto.e_texto_url(u) else None


def ident(u):
    if texto.e_texto_url(u):
        return texto.id_de_url(u)
    y = re.search(r"(?:v=|youtu\.be/|/shorts/)([\w-]{11})", u)
    m = re.search(r"/video/(\d+)", u)
    return ("yt_" + y.group(1)) if y else (m.group(1) if m else None)


def tiktok_bloqueado(c):
    """3+ downloads do TikTok recusados com sinal de bloqueio nas últimas 3 horas."""
    desde = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(timespec="seconds")
    n = 0
    for r in c.execute("SELECT e.video_id, e.mensagem, e.fim FROM etapas e WHERE e.etapa='baixar' AND e.status='falha'"):
        try:
            recente = datetime.fromisoformat(r[2]).astimezone(timezone.utc).isoformat(timespec="seconds") >= desde
        except (TypeError, ValueError):
            recente = False
        if recente and not str(r[0]).startswith(("yt_", "tx_", "local_")) and any(s in (r[1] or "").lower() for s in SINAIS_BLOQUEIO):
            n += 1
    return n >= 3


def candidatos(c, ja, quantos):
    feitos = {r[0] for r in c.execute("SELECT video_id FROM etapas WHERE etapa='transcrever' AND status IN ('ok','alerta')")}
    falhas = {}
    for r in c.execute("SELECT video_id FROM eventos WHERE etapa='baixar' AND tipo='fim' AND status='falha'"):
        falhas[r[0]] = falhas.get(r[0], 0) + 1
    listas = sorted((C.BASE / "listas").glob("*.txt"), key=lambda p: (p.name != "victhor_cv.txt", p.name))
    out, vistos, conta = [], set(ja), {k: 0 for k in quantos}
    for arq in listas:
        for l in arq.read_text(encoding="utf-8", errors="replace").splitlines():
            l = l.strip()
            if not l.startswith("http"):
                continue
            t = tipo(l)
            if not t or conta.get(t, 0) >= quantos.get(t, 0):
                continue
            i = ident(l)
            if not i or i in vistos or i in feitos or falhas.get(i, 0) >= 2 or (i.startswith("tx_") and falhas.get(i, 0) >= 1):
                continue
            vistos.add(i)
            out.append(l)
            conta[t] += 1
    return out, conta


def talvez_enfileirar(ocupado_fn):
    """Chamado pelo vigia do painel a cada 5 s (com a trava da fila). Devolve a lista enfileirada ou None."""
    k = cfg()
    if not k.get("ativo"):
        return None
    try:
        est = json.loads(_estado_arq().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        est = {}
    if time.time() - est.get("ultimo", 0) < float(k["intervalo_min"]) * 60:
        return None
    if fila.pausada() or fila.ler() or ocupado_fn():
        return None
    c = db.conectar()
    try:
        bloqueado = tiktok_bloqueado(c)
        quantos = {"tiktok": 0 if bloqueado else int(k["tiktok"]), "youtube": int(k["youtube"]), "texto": int(k["texto"])}
        links, conta = candidatos(c, set(), quantos)  # só roda com fila vazia e nada rodando
    finally:
        c.close()
    est["ultimo"] = time.time()
    _estado_arq().write_text(json.dumps(est), encoding="utf-8")
    if bloqueado:
        _log("TikTok recusando downloads (sinal de bloqueio): TikTok fora deste lote automático")
    if not links:
        _log("nada novo nas listas para enfileirar")
        return []
    fila.adicionar(links, [])
    _log(f"lote automático enfileirado: {len(links)} ({conta.get('tiktok', 0)} TikTok, {conta.get('youtube', 0)} YouTube, "
         f"{conta.get('texto', 0)} texto)")
    return links
