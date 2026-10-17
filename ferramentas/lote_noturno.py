"""Lote noturno (ferramenta do Claude). Roda FORA do Windows, pela ponte, a cada hora:
lê uma CÓPIA do banco, confere erros/números, põe o próximo lote em dados/fila_espera.json e escreve o relatório da noite.
O painel (ABRIR_PAINEL.bat) é quem processa a fila. Uso: python3 ferramentas/lote_noturno.py <pasta_temp> [N_tiktok] [N_youtube]"""
import json, os, re, shutil, sqlite3, sys, time, uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
TMP = Path(sys.argv[1]); TMP.mkdir(parents=True, exist_ok=True)
N_TT = int(sys.argv[2]) if len(sys.argv) > 2 else 12
N_YT = int(sys.argv[3]) if len(sys.argv) > 3 else 3
BR = timezone(timedelta(hours=-3)); agora = datetime.now(BR)
RELATORIO = BASE / "relatorios" / "NOITE_2026-10-16.md"
# todas as listas em listas/*.txt (victhor_cv primeiro); cada link vai para TikTok ou YouTube pelo domínio
_todas = sorted((BASE / "listas").glob("*.txt"), key=lambda p: (p.name != "victhor_cv.txt", p.name))
LISTAS = [str(p.relative_to(BASE)) for p in _todas]
N_RE = int(sys.argv[4]) if len(sys.argv) > 4 else 40   # vídeos antigos a reagrupar por rodada (rápido: não baixa nada)

sys.path.insert(0, str(BASE))
from app import texto as TX  # mesma identidade das fontes de texto usada pelo programa
N_TX = int(sys.argv[5]) if len(sys.argv) > 5 else 4

def ident(u):
    if TX.e_texto_url(u): return TX.id_de_url(u)
    y = re.search(r"(?:v=|youtu\.be/|/shorts/)([\w-]{11})", u); m = re.search(r"/video/(\d+)", u)
    return ("yt_" + y.group(1)) if y else (m.group(1) if m else None)

for f in ("cv.db", "cv.db-wal"):
    src = BASE / "dados" / f
    if src.exists(): shutil.copy2(src, TMP / f)
    elif (TMP / f).exists(): (TMP / f).unlink()
c = sqlite3.connect(TMP / "cv.db"); c.row_factory = sqlite3.Row
st = {}
for r in c.execute("SELECT video_id, etapa, status FROM etapas"): st.setdefault(r["video_id"], {})[r["etapa"]] = r["status"]
falhas_baixar = {}
for r in c.execute("SELECT video_id FROM eventos WHERE etapa='baixar' AND tipo='fim' AND status='falha'"):
    falhas_baixar[r[0]] = falhas_baixar.get(r[0], 0) + 1
execs = sorted([dict(r) for r in c.execute("SELECT * FROM execucoes")], key=lambda e: datetime.fromisoformat(e["inicio"]).timestamp())
ativa = [e for e in execs if e["status"] == "rodando" and e["disparada_por"] in ("painel", "terminal")]
fila = json.loads((BASE / "dados" / "fila_espera.json").read_text(encoding="utf-8") or "[]") if (BASE / "dados" / "fila_espera.json").exists() else []
na_fila = {ident(x) for l in fila for x in l.get("links", [])}
for e in ativa: na_fila |= {ident(x) for x in json.loads(e["parametros"] or "{}").get("entradas", [])}

def candidatos(listas, n, dominio):
    out = []
    if n <= 0: return out
    for arq in listas:
        p = BASE / arq
        if not p.exists(): continue
        for l in p.read_text(encoding="utf-8").splitlines():
            l = l.strip()
            if not l.startswith("http"): continue
            if (dominio == "texto" and not TX.e_texto_url(l)) or (dominio != "texto" and dominio not in l): continue
            if "reddit.com" in l.lower(): continue  # Reddit só pelo usuário (o Claude não tem acesso ao Reddit e não contorna)
            i = ident(l)
            if not i or i in na_fila or i in [ident(x) for x in out]: continue
            s = st.get(i, {})
            if s.get("transcrever") in ("ok", "alerta"): continue           # já feito
            if falhas_baixar.get(i, 0) >= 2: continue                         # falhou 2x no download: desiste e reporta
            if i.startswith("tx_") and falhas_baixar.get(i, 0) >= 1: continue   # página que recusou (ex.: 403): respeita, não insiste
            out.append(l)
            if len(out) >= n: return out
    return out

novos = candidatos(LISTAS, N_TT, "tiktok.com") + candidatos(LISTAS, N_YT, "youtube.com") + candidatos(LISTAS, N_TX, "texto")
# vídeos antigos com imagens no agrupamento velho (v1): reprocessa só o agrupamento + pacote da IA (não baixa de novo)
def agrup(vid):
    r = c.execute("SELECT status, metricas FROM etapas WHERE video_id=? AND etapa='imagens'", (vid,)).fetchone()
    if not r or r["status"] not in ("ok", "alerta"): return None
    try: return json.loads(r["metricas"] or "{}").get("agrupamento") or "v1"
    except ValueError: return "v1"
velhos = [dict(r) for r in c.execute("SELECT video_id, url FROM videos WHERE url LIKE 'http%' ORDER BY criado_em")]
def conf_antiga(vid):
    r = c.execute("SELECT status, metricas FROM etapas WHERE video_id=? AND etapa='interpretar'", (vid,)).fetchone()
    if not r or r["status"] not in ("ok", "alerta"): return False
    try: return json.loads(r["metricas"] or "{}").get("conferencia") != "v3"
    except ValueError: return True
reagrupar_todos = [v for v in velhos if v["video_id"] not in na_fila
                   and (agrup(v["video_id"]) not in (None, "v2") or conf_antiga(v["video_id"]))]
reagrupar = [v["url"] for v in reagrupar_todos[:N_RE]]
if reagrupar:
    novos += [u for u in reagrupar if u not in novos]
if novos:
    fila.append({"id": uuid.uuid4().hex[:12], "links": novos, "arquivos": [], "pedido_em": agora.isoformat(timespec="seconds"), "origem": "lote_noturno"})
    tmp = BASE / "dados" / f"fila_espera_{uuid.uuid4().hex[:6]}.tmp"; tmp.write_text(json.dumps(fila, ensure_ascii=False, indent=2), encoding="utf-8"); tmp.replace(BASE / "dados" / "fila_espera.json")
(BASE / "dados" / "fila_controle.json").write_text(json.dumps({"pausada": False, "ts": agora.isoformat(timespec="seconds"), "por": "lote_noturno"}), encoding="utf-8")

# ---- situação
def conta(cond): return sum(1 for v, s in st.items() if cond(s))
total_videos = c.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
transcritos = conta(lambda s: s.get("transcrever") in ("ok", "alerta"))
prontos_ia = conta(lambda s: s.get("interpretar") == "aguardando_ia")
com_falha = conta(lambda s: any(x in ("falha", "interrompida") for x in s.values()))
causas = c.execute("SELECT etapa, mensagem, COUNT(*) n FROM etapas WHERE status IN ('falha','interrompida') GROUP BY etapa, mensagem ORDER BY n DESC LIMIT 6").fetchall()
desde = (agora - timedelta(minutes=65))
recentes = [e for e in execs if datetime.fromisoformat(e["inicio"]).astimezone(BR) >= desde]
pulso_ok = None
if ativa:
    pulso_ok = (datetime.now(timezone.utc) - datetime.fromisoformat(ativa[-1]["pulso"]).astimezone(timezone.utc)).total_seconds() < 60
painel_vivo = (time.time() - (BASE / "dados" / "PENDENTES_IA.md").stat().st_mtime) < 60 if (BASE / "dados" / "PENDENTES_IA.md").exists() else False
tt_rest = len(candidatos(LISTAS, 10**6, "tiktok.com")); yt_rest = len(candidatos(LISTAS, 10**6, "youtube.com")); tx_rest = len(candidatos(LISTAS, 10**6, "texto"))
desist = [v for v, n in falhas_baixar.items() if n >= 2]
L = [f"\n## {agora:%H:%M} — verificação da hora",
     f"- Painel no ar: **{'sim' if painel_vivo else 'NÃO (a fila não anda sem ele)'}** · processamento ativo: {'sim' if ativa else 'não'}" + (f" (sinal de vida {'ok' if pulso_ok else 'PERDIDO'})" if ativa else ""),
     f"- Biblioteca: **{total_videos}** vídeos · **{transcritos}** transcritos · **{prontos_ia}** prontos para a IA · **{com_falha}** com falha",
     f"- Execuções na última hora: " + (", ".join(f"{datetime.fromisoformat(e['inicio']).astimezone(BR):%H:%M} {e['status']} ({e['total_entradas']} itens) — {e['resumo'] or '…'}" for e in recentes) or "nenhuma"),
     f"- Novo lote na fila: **{len(novos)}** ({len(novos) - len(reagrupar)} novos: {sum(1 for x in novos if 'tiktok' in x and x not in reagrupar)} TikTok, {sum(1 for x in novos if 'youtube' in x and x not in reagrupar)} YouTube, {sum(1 for x in novos if TX.e_texto_url(x) and x not in reagrupar)} texto; {len(reagrupar)} antigos para reagrupar imagens) · lotes esperando: {len(fila)}",
     f"- Ainda por processar nas listas: {tt_rest} TikTok · {yt_rest} YouTube · {tx_rest} páginas de texto · desistidos (download falhou 2x): {len(desist)}"]
if causas: L.append("- Causas de falha (estado atual): " + "; ".join(f"{r['n']}× {r['etapa']}: {r['mensagem'][:110]}" for r in causas))
if not RELATORIO.exists():
    RELATORIO.write_text("# Relatório da noite 16→17/10/2026 (Claude, verificação de hora em hora)\n"
                         "Fontes: listas/victhor_cv.txt, listas/noite_1_victhor_carreira.txt (TikTok), listas/noite_2_youtube_ib_resume.txt (YouTube).\n"
                         "Só a parte do PROGRAMA (baixar → transcrever → imagens → integridade → pacote IA). A interpretação fica para depois da sua validação.\n", encoding="utf-8")
with open(RELATORIO, "a", encoding="utf-8") as f: f.write("\n".join(L) + "\n")
print("\n".join(L))
