"""MOTOR ÚNICO DE NÚMEROS do painel. Toda página usa só isto. Somente leitura.

Três recortes, sempre rotulados:
- AGORA (biblioteca): estado atual de cada vídeo.
- LOTE: estado atual dos vídeos de um lote (execução).
- HISTÓRICO: o que aconteceu ao longo do tempo (eventos). Fica em api_analitico/api_resumo.
"""
import json, re
from . import db, estado, texto

ETAPAS = ["baixar", "transcrever", "imagens", "integridade", "interpretar", "relatorio"]
# ordem de prioridade: a primeira que aparecer define a situação do vídeo
SITUACOES = ["rodando", "sem sinal", "falha", "bloqueado", "aguardando IA", "alerta", "incompleto", "concluído",
             "na fila", "migrado"]
EXPLICA = {
    "rodando": "Em processamento agora.",
    "sem sinal": "Marcado como rodando, mas o processo parou de dar sinal de vida (pode ter sido fechado).",
    "falha": "Alguma etapa não terminou. A causa está em ‘Falhas e alertas’; dá para reprocessar.",
    "bloqueado": "O pacote para a IA existe, mas não corresponde à transcrição/imagens atuais. Será refeito ao reprocessar.",
    "aguardando IA": "O programa terminou a parte dele; o pacote está pronto esperando o Claude/ChatGPT no chat.",
    "alerta": "Terminou, mas alguma checagem pede conferência (ex.: citação não encontrada, trecho sem fala).",
    "incompleto": "Alguma etapa foi pulada (o motivo está registrado).",
    "concluído": "Todas as 6 etapas terminaram e as checagens passaram.",
    "na fila": "Registrado, ainda não começou a ser processado.",
    "migrado": "Veio da fase anterior (ChatGPT/Codex) já processado, sem as etapas deste programa. Para rastreio completo, reprocessar.",
}


def situacao(st_por_etapa, origem=None):
    v = set(st_por_etapa.values())
    if not v:
        return "migrado" if (origem or "").startswith("migrado") else "na fila"
    if "rodando" in v: return "rodando"
    if "sem_sinal" in v: return "sem sinal"
    if v & {"falha", "interrompida"}: return "falha"
    if st_por_etapa.get("interpretar") == "bloqueada": return "bloqueado"
    if st_por_etapa.get("interpretar") == "aguardando_ia": return "aguardando IA"
    if "alerta" in v: return "alerta"
    if "pulada" in v or len(st_por_etapa) < 6: return "incompleto"
    return "concluído"


def rede_de(url, perfil):
    u = (url or "").lower()
    for chave, nome in (("tiktok.com", "TikTok"), ("instagram.com", "Instagram"), ("youtube.com", "YouTube"),
                        ("youtu.be", "YouTube"), ("linkedin.com", "LinkedIn"), ("reddit.com", "Reddit"),
                        ("//x.com", "X"), ("twitter.com", "X")):
        if chave in u:
            return nome
    if u.startswith("http"):
        return "Web"
    p = (perfil or "").lower()
    if p == "arquivo_texto": return "Arquivo de texto"
    if "snaptik" in p: return "TikTok"
    if p == "manual": return "Arquivo enviado"
    return "Desconhecida"


def perfil_legivel(perfil):
    if (perfil or "").startswith("manual (snaptik"): return "desconhecido (baixado à mão)"
    if perfil == "manual": return "(sem perfil — arquivo enviado)"
    if not perfil or perfil == "desconhecido": return "desconhecido"
    if perfil == "arquivo_texto": return "(arquivo de texto)"
    if perfil.startswith("site:"): return perfil[5:]
    if "/" in perfil or ("." in perfil and not perfil.startswith("@") and " " not in perfil and perfil.count(".") >= 1
                         and perfil.split(".")[-1] in ("com", "org", "edu", "br", "net", "io", "co", "uk", "gov")):
        return perfil  # r/Subreddit ou domínio de site
    return perfil if perfil.startswith("@") else "@" + perfil


def titulo_curto(t, vid):
    t = (t or "").strip()
    t = t.split(" #")[0].strip() or t
    if not t or t.startswith("http"):
        return f"vídeo {vid[-6:]}"
    return (t[:70] + "…") if len(t) > 70 else t


def estado_videos(c, pend=None):
    """Lista com o estado ATUAL de cada vídeo da biblioteca (a fonte de verdade de todas as páginas)."""
    validos, _ = pend or estado.pendentes(c)
    ids_validos = {r["video_id"] for r in validos}
    out = []
    for v in db.linhas(c, "SELECT video_id,perfil,url,titulo,origem,duracao_s,criado_em,atualizado_em FROM videos"):
        st = {r["etapa"]: r["status"] for r in estado.etapas_efetivas(c, v["video_id"], ids_validos)}
        out.append({"video_id": v["video_id"], "titulo": titulo_curto(v["titulo"], v["video_id"]),
                    "rede": rede_de(v["url"], v["perfil"]), "perfil": perfil_legivel(v["perfil"]),
                    "origem": v["origem"], "duracao_s": v["duracao_s"] or 0, "etapas": st,
                    "situacao": situacao(st, v["origem"]), "atualizado": v["atualizado_em"] or v["criado_em"] or ""})
    return out


def contar(lista):
    n = len(lista)
    sit = {s: 0 for s in SITUACOES}
    for v in lista:
        sit[v["situacao"]] = sit.get(v["situacao"], 0) + 1
    et = {}
    for e in ETAPAS:
        cont = {"feito": 0, "alerta": 0, "falha": 0, "rodando": 0, "aguardando": 0, "bloqueada": 0, "pulada": 0}
        for v in lista:
            s = v["etapas"].get(e)
            if s in ("ok", "alerta"): cont["feito"] += 1
            if s == "alerta": cont["alerta"] += 1
            if s in ("falha", "interrompida", "sem_sinal"): cont["falha"] += 1
            if s == "rodando": cont["rodando"] += 1
            if s == "aguardando_ia": cont["aguardando"] += 1
            if s == "bloqueada": cont["bloqueada"] += 1
            if s == "pulada": cont["pulada"] += 1
        cont["nao_rodou"] = n - sum(1 for v in lista if e in v["etapas"])
        et[e] = cont
    return {"videos": n, "situacao": sit, "etapas": et}


def lote(c, ex, todos):
    if not ex:
        return None
    entradas = json.loads(ex.get("parametros") or "{}").get("entradas", [])
    ids = []
    for r in c.execute("SELECT video_id FROM eventos WHERE execucao_id=? AND video_id IS NOT NULL ORDER BY id", (ex["id"],)):
        if r[0] not in ids:
            ids.append(r[0])
    for raw in entradas:  # vídeos ainda não iniciados neste lote
        m = re.search(r"/video/(\d+)", str(raw))
        y = re.search(r"(?:v=|youtu\.be/|/shorts/)([\w-]{11})", str(raw))
        vid = m.group(1) if m else ("yt_" + y.group(1) if y else None)
        if not vid and texto.e_texto_url(raw):
            vid = texto.id_de_url(raw)
        if vid and vid not in ids:
            ids.append(vid)
    recusadas = [r[0].split(": ", 1)[-1] for r in c.execute(
        "SELECT mensagem FROM eventos WHERE execucao_id=? AND video_id IS NULL AND tipo='erro' AND mensagem LIKE 'Entrada % ignorada:%' ORDER BY id",
        (ex["id"],))]
    por_id = {v["video_id"]: v for v in todos}
    lista = [por_id.get(i) or {"video_id": i, "titulo": f"vídeo {i[-6:]}", "rede": "?", "perfil": "?", "origem": None,
                               "duracao_s": 0, "etapas": {}, "situacao": "na fila", "atualizado": ""} for i in ids]
    return {"execucao_id": ex["id"], "inicio": ex["inicio"], "status": ex["status"], "disparada_por": ex["disparada_por"],
            "entradas": ex.get("total_entradas") or len(entradas), "recusadas": recusadas,
            "lista": lista, **contar(lista)}


_CACHE_SNAP = {}


def snapshot(c, ex=None):
    chave = (estado.assinatura(c), ex["id"] if ex else None, ex["status"] if ex else None)
    if _CACHE_SNAP.get("chave") == chave:
        return _CACHE_SNAP["valor"]
    valor = _snapshot(c, ex)
    _CACHE_SNAP.update(chave=chave, valor=valor)
    return valor


def _snapshot(c, ex=None):
    """Tudo numa única leitura do banco (transação), para os números não se contradizerem
    quando o programa grava no meio da conta."""
    abriu = not c.in_transaction
    if abriu:
        c.execute("BEGIN")
    try:
        return _snapshot_tx(c, ex)
    finally:
        if abriu and c.in_transaction:
            c.execute("COMMIT")


def _snapshot_tx(c, ex=None):
    pend = estado.pendentes(c)
    todos = estado_videos(c, pend)
    fontes = {}
    for v in todos:
        fontes.setdefault((v["rede"], v["perfil"]), []).append(v)
    lista_fontes = []
    for (rede, perfil), vs in fontes.items():
        k = contar(vs)
        lista_fontes.append({"rede": rede, "perfil": perfil, "videos": k["videos"], "situacao": k["situacao"],
                             "duracao_s": sum(v["duracao_s"] for v in vs),
                             "atualizado": max((v["atualizado"] for v in vs), default="")})
    lista_fontes.sort(key=lambda f: (-f["videos"], f["rede"], f["perfil"]))
    bib = contar(todos)
    validos, invalidos = pend
    banco = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("videos", "falas", "frames", "recomendacoes")}
    banco["videos_com_falha"] = c.execute("SELECT COUNT(DISTINCT e.video_id) FROM etapas e JOIN videos v USING(video_id) "
                                          "WHERE e.status IN ('falha','interrompida')").fetchone()[0]
    banco["etapas_sem_video"] = c.execute("SELECT COUNT(DISTINCT video_id) FROM etapas "
                                          "WHERE video_id NOT IN (SELECT video_id FROM videos)").fetchone()[0]
    return {"biblioteca": bib, "fontes": lista_fontes, "lote": lote(c, ex, todos),
            "ia": {"prontos": len(validos), "bloqueados": len(invalidos)},
            "banco": banco,
            "explica": EXPLICA, "ordem_situacoes": SITUACOES}


def conferir(c, snap):
    """Autoconferência: os números das páginas batem entre si? Devolve lista de verificações."""
    b = snap["biblioteca"]
    r = []
    def chk(nome, a, e):
        r.append({"nome": nome, "ok": a == e, "valor": a, "esperado": e})
    chk("soma das fontes = vídeos da biblioteca", sum(f["videos"] for f in snap["fontes"]), b["videos"])
    chk("soma das situações = vídeos da biblioteca", sum(b["situacao"].values()), b["videos"])
    chk("vídeos no banco = vídeos da biblioteca", snap["banco"]["videos"], b["videos"])
    chk("IA: prontos = etapa Interpretar aguardando", snap["ia"]["prontos"], b["etapas"]["interpretar"]["aguardando"])
    chk("IA: bloqueados = etapa Interpretar bloqueada", snap["ia"]["bloqueados"], b["etapas"]["interpretar"]["bloqueada"])
    vf = snap["banco"].get("videos_com_falha")
    if vf is None:
        vf = c.execute("SELECT COUNT(DISTINCT e.video_id) FROM etapas e JOIN videos v USING(video_id) WHERE e.status IN ('falha','interrompida')").fetchone()[0]
    chk("vídeos com falha (banco) = situação falha", vf, b["situacao"]["falha"])
    orf = snap["banco"].get("etapas_sem_video")
    if orf is None:
        orf = c.execute("SELECT COUNT(DISTINCT video_id) FROM etapas WHERE video_id NOT IN (SELECT video_id FROM videos)").fetchone()[0]
    chk("etapas sem vídeo registrado (devem ser 0)", orf, 0)
    if snap["lote"]:
        L = snap["lote"]
        chk("lote: soma das situações = vídeos do lote", sum(L["situacao"].values()), L["videos"])
        chk("lote: aceitos + recusados = entradas", L["videos"] + len(L["recusadas"]), L["entradas"])
    return r
