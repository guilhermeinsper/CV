"""Servidor do painel de controle (só no seu computador: http://127.0.0.1:8770).

Lê o banco dados/cv.db e os eventos. Também pode disparar o pipeline e registrar suas validações.
Não usa nenhuma biblioteca externa.
"""
import argparse, json, mimetypes, os, subprocess, sys, threading, time, webbrowser, uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from . import config as C, db, estado, metricas, texto, fila as fila_manager

VERSAO_SERVIDOR = "3.6"
WEB = Path(__file__).resolve().parent / "web"
PROCESSO = {"popen": None, "execucao_id": None, "log": None}
REQUEST=threading.local()
TABELAS = ["videos", "etapas", "falas", "frames", "checagens", "analises_ia", "cv_exemplos", "recomendacoes",
           "notas", "execucoes", "eventos"]


def con():
    current=getattr(REQUEST,'conexao',None)
    if current is None:
        current=db.conectar()
        if getattr(REQUEST,'ativo',False):REQUEST.conexao=current
    return current

def executar_api(fn,arg):
    REQUEST.ativo=True;REQUEST.conexao=None
    try:return fn(arg)
    finally:
        if REQUEST.conexao is not None:REQUEST.conexao.close()
        REQUEST.conexao=None;REQUEST.ativo=False


def pulso_vivo(e):
    if e["status"] != "rodando":
        return False
    try:
        dt = datetime.fromisoformat(e["pulso"])
        return (datetime.now(dt.tzinfo) - dt).total_seconds() < 20
    except Exception:
        return False


def corrigir_orfas(c):
    """Leitura não altera execuções/etapas; ausência de pulso é exposta na projeção."""
    return None


ORDEM = ["baixar", "transcrever", "imagens", "integridade", "interpretar", "relatorio"]
CONCLUIDAS = ("ok", "alerta", "falha", "pulada", "interrompida")


def status_video(etapas):
    return estado.situacao(etapas)

def _status_video_antigo(etapas):
    s = {e["etapa"]: e["status"] for e in etapas}
    v = list(s.values())
    if not v:
        return "sem dados"
    if "rodando" in v:
        return "rodando"
    if "falha" in v or "interrompida" in v:
        return "falha"
    if s.get("interpretar") == "aguardando_ia":
        return "aguardando IA"
    if "alerta" in v:
        return "alerta"
    if "pulada" in v:
        return "incompleto"
    return "ok"


def rede_de(url, perfil, origem):
    return metricas.rede_de(url, perfil)


def _rede_de_antiga(url, perfil, origem):
    u = (url or "").lower()
    for chave, nome in (("tiktok.com", "TikTok"), ("instagram.com", "Instagram"), ("youtube.com", "YouTube"),
                        ("youtu.be", "YouTube"), ("linkedin.com", "LinkedIn")):
        if chave in u:
            return nome
    p = (perfil or "").lower()
    if "snaptik" in p:
        return "TikTok"
    if p == "manual":
        return "Arquivo enviado"
    return "Desconhecida"


def perfil_legivel(perfil):
    return metricas.perfil_legivel(perfil)


def _perfil_legivel_antigo(perfil):
    if (perfil or "").startswith("manual (snaptik"):
        return "desconhecido (baixado à mão)"
    if perfil == "manual":
        return "(sem perfil — arquivo enviado)"
    return "@" + perfil if perfil and not perfil.startswith("@") else (perfil or "desconhecido")


def titulo_curto(v):
    t = (v.get("titulo") or "").strip()
    t = t.split(" #")[0].strip() or t
    return (t[:70] + "…") if len(t) > 70 else (t or "vídeo sem título")


# ------------------------------------------------------------------ API: workflow (agregado da execução)
def ts_num(t):
    try:
        return datetime.fromisoformat(t).timestamp()
    except Exception:
        return 0


def execucoes_ordenadas(c):
    execs = db.linhas(c, "SELECT * FROM execucoes")
    for e in execs:
        if e['status']=='rodando' and not estado.pulso_recente(e):e.update(status_registrado='rodando',status='sem_sinal')
    return sorted(execs, key=lambda e: ts_num(e["inicio"]), reverse=True)


def recusadas(c, ex_id):
    return [r["mensagem"].split(": ", 1)[-1] for r in c.execute(
        "SELECT mensagem FROM eventos WHERE execucao_id=? AND video_id IS NULL AND tipo='erro' AND mensagem LIKE 'Entrada % ignorada:%' ORDER BY id", (ex_id,))]


def resumo_execucao(c, ex_id):
    evs = db.linhas(c, "SELECT video_id, etapa, tipo, status, mensagem, dados, ts FROM eventos WHERE execucao_id=? "
                       "AND video_id IS NOT NULL ORDER BY id", (ex_id,))
    ordem, por_video = [], {}
    for e in evs:
        vid = e["video_id"]
        if vid not in por_video:
            por_video[vid] = {}
            ordem.append(vid)
        if e["etapa"] and e["tipo"] == "inicio":
            por_video[vid][e["etapa"]] = {"status": "rodando", "inicio": e["ts"]}
        elif e["etapa"] and e["tipo"] == "fim":
            d = json.loads(e["dados"]) if e["dados"] else {}
            por_video[vid][e["etapa"]] = {"status": e["status"], "fim": e["ts"], "mensagem": e["mensagem"],
                                          "mantido": bool(d and d.get("mantido"))}
    return ordem, por_video


def api_painel(q):
    c = con()
    corrigir_orfas(c)
    execs = execucoes_ordenadas(c)
    proc = [e for e in execs if e["disparada_por"] in ("painel", "terminal")]
    ex_id = (q.get("execucao") or [None])[0] or ((proc or execs)[0]["id"] if execs else None)
    ex = next((e for e in execs if e["id"] == ex_id), None)
    ordem, por_video = resumo_execucao(c, ex_id) if ex_id else ([], {})
    validos,invalidos=estado.pendentes(c);ids_validos={r['video_id'] for r in validos}
    recentes=(proc or execs)
    estado_atual=bool(ex and recentes and ex['id']==recentes[0]['id'])
    entradas=json.loads(ex.get('parametros') or '{}').get('entradas',[]) if ex else []
    esperados=[]
    for raw in entradas:
        match=__import__('re').search(r'/video/(\d+)',str(raw))
        yt=__import__('re').search(r'(?:v=|youtu\.be/|/shorts/)([\w-]{11})',str(raw))
        vid_esp=match.group(1) if match else ('yt_'+yt.group(1) if yt else (texto.id_de_url(raw) if texto.e_texto_url(raw) else None))
        if vid_esp and vid_esp not in esperados:esperados.append(vid_esp)
    if estado_atual:
        ordem=list(dict.fromkeys(esperados+ordem))
        por_video={vid:{r['etapa']:r for r in estado.etapas_efetivas(c,vid,ids_validos)} for vid in ordem}
    vivo = bool(ex and estado.pulso_recente(ex))
    agregado = {et: {"total": 0} for et in ORDEM}
    fila = []
    iniciados={r[0] for r in c.execute("SELECT DISTINCT video_id FROM eventos WHERE execucao_id=? AND status='video_inicio'",(ex_id,))}
    for vid in ordem:
        etp = por_video[vid]
        if etp.get('interpretar',{}).get('status')=='aguardando_ia' and any(etp.get(name,{}).get('status') not in ('ok','alerta') for name in ['transcrever','imagens','integridade']):
            etp['interpretar']={**etp['interpretar'],'status':'bloqueada','status_registrado':'aguardando_ia','mensagem':'Pacote registrado sem pré-requisitos técnicos válidos nesta execução.'}
        if not vivo:
            for x in etp.values():
                if x["status"] == "rodando":
                    x["status"] = "sem_sinal"
        for et, x in etp.items():
            if et in agregado:
                agregado[et][x["status"]] = agregado[et].get(x["status"], 0) + 1
                agregado[et]["total"] += 1
                agregado[et]["mantidos"] = agregado[et].get("mantidos", 0) + (1 if x.get("mantido") else 0)
        v = c.execute("SELECT video_id,titulo,perfil,url,origem FROM videos WHERE video_id=?", (vid,)).fetchone()
        v = dict(v) if v else {"video_id": vid, "titulo": None, "perfil": None, "url": None, "origem": None}
        feitas = sum(1 for et in ORDEM if etp.get(et, {}).get("status") in CONCLUIDAS)  # aguardando IA não conta como feita
        atual = next((et for et in ORDEM if etp.get(et, {}).get("status") in ("rodando", "aguardando_ia")), None) \
            or next((et for et in ORDEM if et not in etp), None)
        prog=db.linhas(c,"SELECT dados,mensagem,ts FROM eventos WHERE execucao_id=? AND video_id=? AND tipo='progresso' ORDER BY id DESC LIMIT 1",(ex_id,vid))
        progresso=json.loads(prog[0]['dados'] or '{}') if prog else {}
        frac=min(.99,max(0,progresso.get('ate_s',0)/progresso['total_s'])) if progresso.get('total_s') else 0
        sucesso=sum(etp.get(e,{}).get('status') in ('ok','alerta') for e in estado.TECNICAS)
        if etp.get('transcrever',{}).get('status')!='rodando':frac=0
        fila.append({"video_id": vid, "titulo": titulo_curto(v), "rede": rede_de(v["url"], v["perfil"], v["origem"]),
                     "perfil": perfil_legivel(v["perfil"]), "etapas": {k: x["status"] for k, x in etp.items()},
                     "feitas": feitas, "atual": atual,'progresso':progresso,'preparacao_pct':round(100*(sucesso+frac)/5,1),
                     'iniciado_nesta_execucao':vid in iniciados,'sem_progresso_s':max(0,round(time.time()-ts_num(prog[0]['ts'] if prog else etp.get(atual,{}).get('inicio')))) if atual else None,
                     "status": 'na fila' if vivo and vid not in iniciados else status_video([{"etapa": k, "status": x["status"]} for k, x in etp.items()])})
    ult = db.linhas(c, "SELECT ts, etapa, mensagem, tipo FROM eventos WHERE execucao_id=? ORDER BY id DESC LIMIT 1", (ex_id,)) if ex_id else []
    pend = len(validos)
    lib={}
    for vid in c.execute('SELECT video_id FROM videos'):
        for r in estado.etapas_efetivas(c,vid[0],ids_validos):
            key=r['etapa']+':'+r['status'];lib[key]=lib.get(key,0)+1
    biblioteca = {"videos": c.execute("SELECT COUNT(*) FROM videos").fetchone()[0],
                  "migrados_sem_etapas": c.execute("SELECT COUNT(*) FROM videos v WHERE NOT EXISTS (SELECT 1 FROM etapas e WHERE e.video_id=v.video_id)").fetchone()[0],
                  **{et: {"ok": lib.get(f"{et}:ok", 0) + lib.get(f"{et}:alerta", 0), "falha": lib.get(f"{et}:falha", 0) + lib.get(f"{et}:interrompida", 0),
                          "aguardando": lib.get(f"{et}:aguardando_ia", 0), 'bloqueada':lib.get(f'{et}:bloqueada',0),"pulada": lib.get(f"{et}:pulada", 0)} for et in ORDEM}}
    recus=recusadas(c,ex_id) if ex_id else []
    encerrados=c.execute("SELECT COUNT(DISTINCT video_id) FROM eventos WHERE execucao_id=? AND status='video_fim'",(ex_id,)).fetchone()[0]
    aceitos=len(ordem) if ordem else max(0,(ex or {}).get('total_entradas',0)-len(recus))
    progresso_lote={'enviados':(ex or {}).get('total_entradas',0),'aceitos':aceitos,'recusados':len(recus),
        'encerrados':encerrados,'iniciados':len(iniciados),'a_iniciar':max(0,aceitos-len(iniciados)),
        'pct_encerrado':round(100*(encerrados+len(recus))/max(1,(ex or {}).get('total_entradas',0)),1),
        'pct_preparacao':round(sum(v['preparacao_pct'] for v in fila)/max(1,aceitos),1),
        'preparados':sum(all(v['etapas'].get(e) in ('ok','alerta') for e in estado.TECNICAS) for v in fila)}
    snap = metricas.snapshot(c, ex)
    return {"m": snap, "conferencia": conferir_e_registrar(c, snap), "saude": SAUDE,
            "execucoes": execs, "execucao": ex, "vivo": vivo, "agregado": agregado, "fila": fila,
            "recusadas": recusadas(c, ex_id) if ex_id else [], "biblioteca": biblioteca, "espera": len(ler_espera()),
            "ultimo": ult[0] if ult else None, "aguardando_ia": pend,'pacotes_invalidos':len(invalidos),'progresso_lote':progresso_lote,
            'fila_espera':ler_espera(),'fila_pausada':fila_manager.pausada(),'versao':'3.2.0','escopo':'Estado atual dos vídeos do lote' if estado_atual else 'Histórico desta execução',
            "banco": {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                      for t in ("videos", "falas", "frames", "checagens", "recomendacoes")}}


def api_etapa(q):
    """Detalhe de uma etapa numa execução: situação de cada vídeo, checagens e eventos."""
    c = con()
    ex_id, et = q["execucao"][0], q["etapa"][0]
    painel=api_painel({'execucao':[ex_id]});ordem=[v['video_id'] for v in painel['fila']]
    _,por_video=resumo_execucao(c,ex_id)
    if painel['escopo'].startswith('Estado atual'):
        por_video={vid:{r['etapa']:r for r in estado.etapas_efetivas(c,vid)} for vid in ordem}
    vids = []
    for vid in ordem:
        x = por_video[vid].get(et)
        v = c.execute("SELECT titulo, perfil FROM videos WHERE video_id=?", (vid,)).fetchone()
        vids.append({"video_id": vid, "titulo": titulo_curto(dict(v)) if v else vid, "status": x["status"] if x else "não chegou",
                     "mensagem": (x or {}).get("mensagem")})
    ch = db.linhas(c, "SELECT k.*, v.titulo FROM checagens k LEFT JOIN videos v USING(video_id) WHERE k.execucao_id=? AND k.etapa=? ORDER BY k.id",
                   (ex_id, et))
    evs = db.linhas(c, "SELECT * FROM eventos WHERE execucao_id=? AND etapa=? ORDER BY id LIMIT 400", (ex_id, et))
    return {"videos": vids, "checagens": ch, "eventos": evs}


# ------------------------------------------------------------------ API: fontes (vídeos agrupados)
def api_fontes(q):
    c = con()
    return {"fontes": metricas.snapshot(c)["fontes"]}


# ------------------------------------------------------------------ API: analítico
def segs(a, b):
    try:
        return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()
    except Exception:
        return None


def api_analitico(q):
    c = con()
    corrigir_orfas(c)
    execs = execucoes_ordenadas(c)
    for e in execs:
        e["duracao_s"] = segs(e["inicio"], e["fim"]) if e["fim"] else None
        e["parametros"] = None
    fins = db.linhas(c, "SELECT mensagem FROM eventos WHERE status='video_fim'")
    res = {"ok": 0, "com alerta": 0, "com falha": 0, "aguardando IA": 0}
    for f in fins:
        m = f["mensagem"] or ""
        k = "com falha" if "falha" in m else "com alerta" if "alerta" in m else "aguardando IA" if "aguardando" in m else "ok"
        res[k] += 1
    # tempo por etapa: pares início/fim de etapas que rodaram de verdade (não "mantidas")
    tempos, abertos = {}, {}
    for e in db.linhas(c, "SELECT execucao_id, video_id, etapa, tipo, ts, dados FROM eventos WHERE etapa IS NOT NULL AND tipo IN ('inicio','fim') ORDER BY id"):
        k = (e["execucao_id"], e["video_id"], e["etapa"])
        if e["tipo"] == "inicio":
            abertos[k] = e["ts"]
        elif k in abertos:
            d = json.loads(e["dados"]) if e["dados"] else {}
            if not (d and d.get("mantido")):
                s = segs(abertos[k], e["ts"])
                if s is not None:
                    tempos.setdefault(e["etapa"], []).append(s)
            abertos.pop(k, None)
    tempo_etapa = {et: {"media_s": round(sum(v) / len(v), 1), "max_s": round(max(v), 1), "n": len(v)}
                   for et, v in tempos.items()}
    resultado_etapa = {et: {} for et in ORDEM}
    for row in c.execute('SELECT video_id FROM videos'):
        for r in estado.etapas_efetivas(c,row[0]):
            if r['etapa'] in resultado_etapa:
                bucket=resultado_etapa[r['etapa']];bucket[r['status']]=bucket.get(r['status'],0)+1
    por_dia = {}
    for e in execs:
        d = (e["inicio"] or "")[:10]
        por_dia.setdefault(d, {})
        por_dia[d][e["status"]] = por_dia[d].get(e["status"], 0) + 1
    alertas = db.linhas(c, "SELECT ts, video_id, etapa, tipo, mensagem FROM eventos WHERE tipo IN ('erro','alerta') ORDER BY id DESC LIMIT 25")
    inicios = {r["k"]: r["ts"] for r in db.linhas(c, "SELECT execucao_id||'|'||video_id k, ts FROM eventos WHERE status='video_inicio'")}
    duracoes = [segs(inicios[r["k"]], r["ts"]) for r in db.linhas(
        c, "SELECT execucao_id||'|'||video_id k, ts FROM eventos WHERE status='video_fim'") if r["k"] in inicios]
    duracoes = [d for d in duracoes if d is not None and d >= 0]
    agora = metricas.snapshot(c)
    return {"agora": {"biblioteca": agora["biblioteca"], "ia": agora["ia"]}, "explica": metricas.EXPLICA,
            "execucoes": execs, "resultado_videos": res, "tempo_etapa": tempo_etapa, "resultado_etapa": resultado_etapa,
            "por_dia": dict(sorted(por_dia.items())), "alertas": alertas,
            "kpis": {"execucoes": len([e for e in execs if e["disparada_por"] in ("painel", "terminal")]),
                     "importacoes": len([e for e in execs if e["disparada_por"] == "importacao_ia"]),
                     "videos_processados": c.execute("SELECT COUNT(DISTINCT video_id) FROM eventos WHERE status='video_fim'").fetchone()[0],
                     "passagens": sum(res.values()),
                     "tempo_medio_video_s": round(sum(duracoes) / len(duracoes), 1) if duracoes else None,
                     "aguardando_ia": len(estado.pendentes(c)[0]),
                     'videos_com_falha':c.execute("SELECT COUNT(DISTINCT video_id) FROM etapas WHERE status IN ('falha','interrompida')").fetchone()[0],
                     "problemas_abertos": c.execute("SELECT COUNT(*) FROM checagens k JOIN etapas e ON e.video_id=k.video_id AND e.etapa=k.etapa AND e.execucao_id=k.execucao_id WHERE k.status<>'ok'").fetchone()[0]}}


# ------------------------------------------------------------------ envio e processamento
def salvar_envio(nome, dados):
    pasta = C.DADOS / "entrada"
    pasta.mkdir(parents=True, exist_ok=True)
    seguro = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in Path(nome).name)[:120] or "video.mp4"
    alvo = pasta / f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:12]}_{seguro}"
    alvo.write_bytes(dados)
    return {"ok": True, "arquivo": C.rel(alvo), "tamanho_mb": round(len(dados) / 1e6, 2)}


def ler_espera():
    return fila_manager.ler()


def gravar_espera(lista):
    return fila_manager.gravar(lista)


def ocupado():
    p = PROCESSO["popen"]
    if p is not None and p.poll() is None:
        return True
    c = db.conectar()  # conexão própria: não fecha a conexão da requisição em andamento
    try:return any(estado.pulso_recente(e) for e in db.linhas(c,"SELECT * FROM execucoes WHERE status='rodando' AND disparada_por IN ('painel','terminal')"))
    finally:c.close()


def api_processar(corpo):
    links = [l.strip() for l in (corpo.get("links") or "").splitlines() if l.strip() and not l.strip().startswith("#")]
    arquivos = [a for a in corpo.get("arquivos") or []]
    if not links and not arquivos:
        return {"erro": "envie um vídeo ou cole pelo menos um link"}
    with fila_manager.LOCK:
        if ocupado() or ler_espera():return fila_manager.adicionar(links,arquivos)
        unique=set();links=[x for x in links if not (estado.identidade(x) in unique or unique.add(estado.identidade(x)))];arquivos=list(dict.fromkeys(arquivos))
        return iniciar(links, arquivos)


def iniciar(links, arquivos):
    arquivos = [str(C.BASE / a) for a in arquivos]
    cmd = [sys.executable, "-u", "-m", "app.pipeline", "--limite", "0", "--ia", "chat", "--disparada-por", "painel"]
    for l in links:
        cmd += ["--url", l]
    for a in arquivos:
        cmd += ["--arquivo", a]
    C.LOGS.mkdir(parents=True, exist_ok=True)
    log = C.LOGS / f"terminal_{time.strftime('%Y%m%d_%H%M%S')}.txt"
    f = open(log, "w", encoding="utf-8")
    flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.Popen(cmd, cwd=Path(__file__).resolve().parent.parent, stdout=f, stderr=subprocess.STDOUT,
                            creationflags=flags, env=env)
    PROCESSO.update(popen=proc, log=log)
    time.sleep(2)  # confere se o processo realmente começou (não aceitar "ok" silencioso)
    if proc.poll() is not None and proc.returncode != 0:
        f.flush()
        fim = log.read_text(encoding="utf-8", errors="replace")[-600:]
        return {"erro": f"o processamento não conseguiu iniciar (código {proc.returncode}). Detalhe: {fim}"}
    return {"ok": True, "videos": len(links) + len(arquivos)}


def api_reprocessar_falhas(corpo):
    c = con()
    vids = db.linhas(c, "SELECT DISTINCT v.video_id, v.url, v.arquivo_video FROM videos v JOIN etapas e USING(video_id) "
                        "WHERE e.status IN ('falha','interrompida')")
    links = [v["url"] for v in vids if v["url"]]
    arquivos = [v["arquivo_video"] for v in vids if not v["url"] and v["arquivo_video"]]
    if not links and not arquivos:
        return {"erro": "não há vídeos com falha para reprocessar"}
    return api_processar({"links": "\n".join(links), "arquivos": arquivos})


def vigiar():
    """A cada 5 s: importa respostas da IA do chat e inicia o próximo lote da fila de espera."""
    from . import importar_ia, reinicio
    codigo0 = reinicio.assinatura_codigo()
    while True:
        time.sleep(5)
        try:  # existe um painel mais novo? então este se desliga (nunca dois painéis tocando a fila ao mesmo tempo)
            dono = PID_ARQ.read_text(encoding="utf-8").strip() if PID_ARQ.exists() else ""
            if dono and dono != str(os.getpid()):
                with open(C.LOGS / "reinicios_painel.txt", "a", encoding="utf-8") as f:
                    f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} painel pid {os.getpid()} desligado: há um painel mais novo (pid {dono})\n")
                os._exit(0)
        except Exception as e:
            print(f"[painel duplicado] erro: {e}", flush=True)
        try:  # código do programa mudou (ou há pedido por arquivo)? reinicia o painel quando estiver ocioso
            if not ocupado():
                if reinicio.pedido_por_flag("servidor"):
                    time.sleep(60); continue
                if reinicio.assinatura_codigo() != codigo0:
                    codigo0 = reinicio.assinatura_codigo()
                    if reinicio.disparar("o código do programa mudou"):
                        time.sleep(60); continue
        except Exception as e:
            print(f"[reinício do painel] erro: {e}", flush=True)
        try:
            importar_ia.importar_prontos("importacao_ia")
            c=con()
            try:
                from .pipeline import atualizar_lista_pendentes
                atualizar_lista_pendentes(c)
            finally:c.close()
        except Exception as e:
            print(f"[importação IA] erro: {e}", flush=True)
        try:
            with fila_manager.LOCK:
                fila = fila_manager.normalizar()
                if not fila:  # contingência: o painel enfileira sozinho a partir de listas/*.txt (config "auto_lote")
                    try:
                        from . import auto_lote
                        if auto_lote.talvez_enfileirar(ocupado):
                            fila = fila_manager.normalizar()
                    except Exception as e:
                        print(f"[lote automático] erro: {e}", flush=True)
                if fila and not fila_manager.pausada() and not ocupado():
                    lote=fila[0]
                    result=iniciar(lote['links'],lote['arquivos'])
                    if result.get('ok'):
                        fila_manager.historico(lote,'Iniciado pelo supervisor.');gravar_espera(fila[1:])
                    else:
                        fila_manager.controlar({'acao':'pausar'});print(result.get('erro'),flush=True)
        except Exception as e:
            print(f"[fila de espera] erro: {e}", flush=True)


def api_eventos(q):
    c = con()
    ex = (q.get("execucao") or [None])[0]
    desde = int((q.get("desde") or [0])[0])
    filtro, args = "WHERE execucao_id=? AND id>?", [ex, desde]
    for campo in ("video", "etapa"):
        val = (q.get(campo) or [None])[0]
        if val:
            filtro += f" AND {'video_id' if campo == 'video' else 'etapa'}=?"
            args.append(val)
    rows = db.linhas(c, f"SELECT * FROM eventos {filtro} ORDER BY id LIMIT 2000", args)
    for r in rows:
        r["dados"] = json.loads(r["dados"]) if r["dados"] else None
    return {"eventos": rows}


def api_video(q):
    c = con()
    vid = q["id"][0]
    v = c.execute("SELECT * FROM videos WHERE video_id=?", (vid,)).fetchone()
    if not v:
        return {"erro": "vídeo não encontrado"}
    et = estado.etapas_efetivas(c,vid)
    for e in et:
        e["metricas"] = json.loads(e["metricas"]) if e["metricas"] else None
    ult_exec = v["ultima_execucao"]
    return {
        "video": dict(v), "etapas": et, "status": status_video(et),
        "falas": db.linhas(c, "SELECT * FROM falas WHERE video_id=? ORDER BY n", (vid,)),
        "frames": db.linhas(c, "SELECT * FROM frames WHERE video_id=? ORDER BY n", (vid,)),
        "checagens": db.linhas(c, "SELECT k.* FROM checagens k JOIN etapas e ON e.video_id=k.video_id AND e.etapa=k.etapa AND e.execucao_id=k.execucao_id WHERE k.video_id=? ORDER BY k.id", (vid,)),
        "analises": db.linhas(c, "SELECT * FROM analises_ia WHERE video_id=? ORDER BY id DESC", (vid,)),
        "cv_exemplos": db.linhas(c, "SELECT * FROM cv_exemplos WHERE video_id=? ORDER BY id", (vid,)),
        "recomendacoes": db.linhas(c, "SELECT * FROM recomendacoes WHERE video_id=? ORDER BY inicio_s", (vid,)),
        "notas": db.linhas(c, "SELECT * FROM notas WHERE video_id=? ORDER BY inicio_s", (vid,)),
    }


def api_falhas(q):
    c = con()
    # causa raiz = falha/interrompida; "pulada" é consequência e fica separada
    causas = db.linhas(c, "SELECT etapa, status, mensagem, COUNT(*) n FROM etapas WHERE status IN ('falha','interrompida') "
                          "GROUP BY etapa, status, mensagem ORDER BY n DESC")
    consequencias = db.linhas(c, "SELECT etapa, mensagem, COUNT(*) n FROM etapas WHERE status='pulada' GROUP BY etapa, mensagem ORDER BY n DESC")
    agora = metricas.snapshot(c)["biblioteca"]
    ULT_ = "JOIN etapas e ON e.video_id=k.video_id AND e.etapa=k.etapa AND e.execucao_id=k.execucao_id"
    tipos_chk = db.linhas(c, f"SELECT k.etapa, k.nome, k.status, COUNT(*) n FROM checagens k {ULT_} WHERE k.status<>'ok' GROUP BY 1,2,3 ORDER BY n DESC")
    videos_falha={r[0] for r in c.execute("SELECT DISTINCT video_id FROM etapas WHERE status IN ('falha','interrompida')")}
    videos_alerta={r[0] for r in c.execute("SELECT DISTINCT video_id FROM etapas WHERE status='alerta'")}-videos_falha
    return {'resumo_atual':{'videos_com_falha':agora["situacao"]["falha"],'videos_com_alerta':agora["situacao"]["alerta"],
                            'videos_bloqueados':agora["situacao"]["bloqueado"],'videos':agora["videos"]},
            "consequencias": consequencias, "causas": causas, "tipos_checagem": tipos_chk,
        "etapas": db.linhas(c, "SELECT e.*, v.titulo FROM etapas e LEFT JOIN videos v USING(video_id) "
                               "WHERE e.status IN ('falha','interrompida','pulada') ORDER BY e.fim DESC LIMIT 300"),
        "checagens": db.linhas(c, "SELECT k.*, v.titulo FROM checagens k JOIN videos v ON v.video_id=k.video_id JOIN etapas e ON e.video_id=k.video_id AND e.etapa=k.etapa AND e.execucao_id=k.execucao_id "
                                  "WHERE k.status<>'ok' ORDER BY k.id DESC LIMIT 500"),
        "citacoes": db.linhas(c, "SELECT r.id, r.video_id, r.inicio_s, r.citacao, r.recomendacao, v.titulo FROM recomendacoes r "
                                 "LEFT JOIN videos v USING(video_id) WHERE r.citacao_verificada=0 LIMIT 300"),
        "execucoes": db.linhas(c, "SELECT * FROM execucoes WHERE status IN ('falhou','interrompida') ORDER BY inicio DESC LIMIT 50"),
    }


def api_tabela(q):
    c = con()
    nome = q.get("nome", ["videos"])[0]
    if nome not in TABELAS:
        return {"erro": "tabela inválida"}
    pagina = int(q.get("pagina", [0])[0])
    busca = (q.get("q") or [""])[0].strip()
    cols = [r[1] for r in c.execute(f"PRAGMA table_info({nome})")]
    where, args = "", []
    if busca:
        where = "WHERE " + " OR ".join(f"CAST({col} AS TEXT) LIKE ?" for col in cols)
        args = [f"%{busca}%"] * len(cols)
    total = c.execute(f"SELECT COUNT(*) FROM {nome} {where}", args).fetchone()[0]
    rows = db.linhas(c, f"SELECT * FROM {nome} {where} ORDER BY rowid DESC LIMIT 100 OFFSET ?", args + [pagina * 100])
    return {"tabela": nome, "colunas": cols, "linhas": rows, "total": total, "pagina": pagina,
            "contagens": {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABELAS}}


def api_config(q):
    cfg, ch = C.config(), C.chaves()
    return {"modelos": cfg["modelos"], "chaves": {"claude": bool(ch.get("ANTHROPIC_API_KEY")),
                                                  "openai": bool(ch.get("OPENAI_API_KEY"))},
            "config": {k: v for k, v in cfg.items() if k != "modelos"}, "base": str(C.BASE),
            "rodando_pelo_painel": PROCESSO["popen"] is not None and PROCESSO["popen"].poll() is None}


def api_validar(corpo):
    c = con()
    st = corpo.get("validacao")
    if st not in ("pendente", "certa", "errada", "ajustar"):
        return {"erro": "validação inválida"}
    c.execute("UPDATE recomendacoes SET validacao=?, validacao_nota=?, validado_em=? WHERE id=?",
              (st, corpo.get("nota"), db.agora() if st != "pendente" else None, int(corpo["id"])))
    c.commit()
    return {"ok": True}


def api_resumo(q):
    from .resumo import resumir
    try:
        return resumir(con(), q.get('periodo', ['hoje'])[0], q.get('data', [None])[0])
    except ValueError as e:
        return {'erro': str(e)}


SAUDE = {}


def verificar_saude():
    """O que o programa precisa para rodar, conferido ao abrir o painel."""
    pasta = C.fixar_ffmpeg()
    if pasta:
        os.environ["CV_FFMPEG_DIR"] = pasta  # processos filhos herdam e acham o ffmpeg mesmo com PATH diferente
    whisper = Path(os.environ.get("USERPROFILE") or Path.home()) / ".cache" / "huggingface" / "hub"
    modelo = C.config()["modelo_whisper"]
    tem_modelo = any(whisper.glob(f"models--*faster-whisper-{modelo}*")) if whisper.exists() else False
    try:
        import yt_dlp
        ytv = yt_dlp.version.__version__
    except Exception:
        ytv = None
    SAUDE.clear()
    SAUDE.update({"versao_servidor": VERSAO_SERVIDOR, "ffmpeg": C.ffmpeg("ffmpeg"), "ffprobe": C.ffmpeg("ffprobe"), "yt_dlp": ytv,
                  "modelo_whisper": modelo, "modelo_baixado": tem_modelo, "python": sys.executable,
                  "ok": bool(C.ffmpeg("ffmpeg") and C.ffmpeg("ffprobe") and ytv and tem_modelo)})
    return SAUDE


def reparar_orfaos():
    """Vídeos cujo download falhou antes da correção não tinham linha em 'videos'. Cria a linha a partir do evento de entrada."""
    import re as _re
    c = db.conectar()
    try:
        for (vid,) in c.execute("SELECT DISTINCT video_id FROM etapas WHERE video_id NOT IN (SELECT video_id FROM videos)").fetchall():
            ev = c.execute("SELECT ts, mensagem FROM eventos WHERE video_id=? AND status='video_inicio' ORDER BY id LIMIT 1", (vid,)).fetchone()
            url = ev["mensagem"].split(": ", 1)[-1] if ev else None
            perfil = (_re.search(r"/@([^/?#]+)", url or "") or [None, "desconhecido"])[1]
            c.execute("INSERT INTO videos(video_id,perfil,url,titulo,origem,criado_em,atualizado_em) VALUES(?,?,?,?,?,?,?)",
                      (vid, perfil, url, url, "programa", ev["ts"] if ev else db.agora(), db.agora()))
        c.commit()
    finally:
        c.close()


def api_saude(q):
    return verificar_saude()


_ULT_CONF = {"chave": None}


def conferir_e_registrar(c, snap):
    """Autoconferência + registro em logs/conferencia_falhas.jsonl quando algum número não bate (para diagnóstico)."""
    conf = metricas.conferir(c, snap)
    ruins = [x for x in conf if not x["ok"]]
    chave = json.dumps(ruins, sort_keys=True, default=str)
    if ruins and chave != _ULT_CONF["chave"]:
        try:
            C.LOGS.mkdir(parents=True, exist_ok=True)
            with open(C.LOGS / "conferencia_falhas.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": db.agora(), "ruins": ruins, "lote": (snap.get("lote") or {}).get("execucao_id"),
                                    "situacao": snap["biblioteca"]["situacao"]}, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass
    _ULT_CONF["chave"] = chave
    return conf


def api_metricas(q):
    c = con()
    execs = execucoes_ordenadas(c)
    proc = [e for e in execs if e["disparada_por"] in ("painel", "terminal")]
    ex_id = (q.get("execucao") or [None])[0]
    ex = next((e for e in execs if e["id"] == ex_id), None) or (proc[0] if proc else None)
    snap = metricas.snapshot(c, ex)
    return {"m": snap, "conferencia": conferir_e_registrar(c, snap)}


GET = {"/api/metricas": api_metricas, "/api/saude": api_saude, "/api/resumo": api_resumo, "/api/painel": api_painel, "/api/etapa": api_etapa, "/api/eventos": api_eventos, "/api/fontes": api_fontes,
       "/api/video": api_video, "/api/falhas": api_falhas, "/api/tabela": api_tabela, "/api/analitico": api_analitico}
POST = {"/api/processar": api_processar, "/api/validar": api_validar, "/api/reprocessar_falhas": api_reprocessar_falhas}
POST['/api/fila']=fila_manager.controlar


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _arquivo(self, p):
        if not p.exists() or not p.is_file():
            self.send_error(404)
            return
        b = p.read_bytes()
        self.send_response(200)
        self.send_header('cache-control','no-store, max-age=0')
        self.send_header("content-type", (mimetypes.guess_type(str(p))[0] or "application/octet-stream")
                         + ("; charset=utf-8" if p.suffix in (".html", ".js", ".css", ".md", ".json", ".txt") else ""))
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path in GET:
                return self._json(executar_api(GET[u.path],q))
            if u.path == "/midia":  # só arquivos dentro de dados/, logs/ ou arquivo/
                alvo = (C.BASE / q["p"][0]).resolve()
                if not any(str(alvo).startswith(str((C.BASE / d).resolve())) for d in ("dados", "logs", "arquivo")):
                    return self.send_error(403)
                return self._arquivo(alvo)
            nome = "index.html" if u.path in ("/", "") else u.path.lstrip("/")
            alvo = (WEB / nome).resolve()
            if not str(alvo).startswith(str(WEB.resolve())):
                return self.send_error(403)
            return self._arquivo(alvo)
        except Exception as e:
            return self._json({"erro": str(e)}, 500)

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("content-length") or 0)
        if u.path == "/api/enviar":  # upload do vídeo em bytes puros
            try:
                return self._json(salvar_envio(parse_qs(u.query).get("nome", ["video.mp4"])[0], self.rfile.read(n)))
            except Exception as e:
                return self._json({"erro": str(e)}, 500)
        corpo = json.loads(self.rfile.read(n) or b"{}")
        if u.path not in POST:
            return self.send_error(404)
        try:
            return self._json(executar_api(POST[u.path],corpo))
        except Exception as e:
            return self._json({"erro": str(e)}, 500)


class _Servidor(ThreadingHTTPServer):
    # no Windows, "reuse address" deixa DOIS painéis ocuparem a mesma porta; aqui não pode
    allow_reuse_address = os.name != "nt"


PID_ARQ = C.DADOS / "painel.pid"


def main():
    C.utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--porta", type=int, default=8770)
    ap.add_argument("--sem-navegador", action="store_true")
    a = ap.parse_args()
    C.garantir_pastas()
    db.conectar().close()
    fila_manager.normalizar()
    reparar_orfaos()
    sd = verificar_saude()
    print(f"Saúde: ffmpeg={'ok' if sd['ffmpeg'] else 'NÃO ACHADO'} · ffprobe={'ok' if sd['ffprobe'] else 'NÃO ACHADO'} · "
          f"yt-dlp={sd['yt_dlp'] or 'NÃO ACHADO'} · modelo {sd['modelo_whisper']}={'ok' if sd['modelo_baixado'] else 'NÃO BAIXADO'}", flush=True)
    srv = None
    for tentativa in range(15):  # num reinício automático o painel antigo pode levar alguns segundos para liberar a porta
        try:
            srv = _Servidor(("127.0.0.1", a.porta), H)
            break
        except OSError:
            time.sleep(2)
    if srv is None:
        print(f"ERRO: a porta {a.porta} já está em uso por outro painel. Feche as outras janelas pretas do painel "
              f"(ou reinicie o PC) e abra o ABRIR_PAINEL.bat de novo.", flush=True)
        with open(C.LOGS / "reinicios_painel.txt", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} FALHA: painel novo não conseguiu a porta {a.porta} (o antigo continua)\n")
        return
    PID_ARQ.write_text(str(os.getpid()), encoding="utf-8")  # o painel "dono" da vez; outro mais antigo se desliga sozinho
    with open(C.LOGS / "reinicios_painel.txt", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} painel no ar (versão {VERSAO_SERVIDOR}, pid {os.getpid()})\n")
    threading.Thread(target=vigiar, daemon=True).start()
    url = f"http://127.0.0.1:{a.porta}"
    print(f"Painel no ar: {url}  (feche esta janela para desligar)", flush=True)
    if not a.sem_navegador:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
