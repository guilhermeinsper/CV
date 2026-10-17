"""Importa as respostas que a IA do chat (Claude/ChatGPT no app) gravou em dados/videos/**/ia/resposta_chat.json.

O painel roda isto sozinho a cada poucos segundos. Também dá para rodar à mão:
  .venv\\Scripts\\python.exe -m app.importar_ia
"""
import json, os, sys
from pathlib import Path
from . import config as C, db, ia, pipeline
from .registro import Execucao


def prontos(con):
    """Vídeos com pacote para a IA cuja resposta já chegou (ou chegou de novo depois de uma falha)."""
    out = []
    for r in db.linhas(con, "SELECT e.video_id, e.status, e.fim, v.pasta FROM etapas e JOIN videos v USING(video_id) "
                            "WHERE e.etapa='interpretar' AND e.status IN ('aguardando_ia','falha')"):
        resp = C.BASE / r["pasta"] / "ia" / "resposta_chat.json"
        if not resp.exists() or not (C.BASE / r["pasta"] / "ia" / "pedido_chat.json").exists():
            continue
        if r["status"] == "falha":  # só tenta de novo se a resposta for mais nova que a falha
            try:
                from datetime import datetime
                if os.path.getmtime(resp) <= datetime.fromisoformat(r["fim"]).timestamp():
                    continue
            except Exception:
                continue
        out.append(r)
    return out


def importar_video(ex, con, vid, pasta):
    cfg = C.config()
    pasta_ia = pasta / "ia"
    ex.etapa_inicio(vid, "interpretar")
    try:
        from .estado import pacote_valido
        valido,motivo=pacote_valido(con,vid)
        if not valido:raise RuntimeError(motivo)
        pedido = json.loads((pasta_ia / "pedido_chat.json").read_text(encoding="utf-8"))
        bruto = (pasta_ia / "resposta_chat.json").read_text(encoding="utf-8-sig")
        d = ia.extrair_json(bruto)
        # resposta de um pacote anterior? (o pacote pode ter sido refeito enquanto a IA lia o antigo)
        env_ns = {i["n"] for i in pedido.get("imagens_enviadas", [])}
        desc_ns = {x.get("n") for x in d.get("descricoes_imagens") or []}
        pac = str(d.get("pacote") or "").strip()
        if (pac and pac != pedido.get("criado_em")) or (desc_ns and len(desc_ns - env_ns) > len(desc_ns & env_ns)):
            import time as _t
            destino = pasta_ia / f"resposta_chat_pacote_antigo_{_t.strftime('%Y%m%d_%H%M%S')}.json"
            (pasta_ia / "resposta_chat.json").replace(destino)
            ex.etapa_fim(vid, "interpretar", "aguardando_ia",
                         "a resposta da IA era de um pacote anterior (imagens diferentes do pacote atual); "
                         f"guardada em {destino.name}. A IA precisa ler o pacote atual.",
                         {"pacote": C.rel(pasta_ia / "PARA_IA.md"), "resposta_antiga": C.rel(destino)})
            pipeline.atualizar_lista_pendentes(con)
            return "aguardando_ia"
        falas = db.linhas(con, "SELECT n, inicio_s, fim_s, texto FROM falas WHERE video_id=? ORDER BY n", (vid,))
        if len(falas) != pedido["trechos"]:
            raise RuntimeError(f"a transcrição mudou desde que o pacote foi criado ({pedido['trechos']} → {len(falas)} trechos); refaça a IA")
        frames_todos = db.linhas(con, "SELECT n, t_s, arquivo, unico FROM frames WHERE video_id=? ORDER BY n", (vid,))
        enviados = pedido["imagens_enviadas"]
        unicos = [f for f in frames_todos if f["unico"]]
        modelo = str(d.get("modelo_declarado") or "não declarado")[:80]
        ex.evento(vid, "interpretar", "progresso", "rodando", f"Importando resposta da IA do chat ({modelo}) e conferindo")
        status, msg, m = pipeline.gravar_interpretacao(
            ex, con, vid, d, enviados, unicos, falas, frames_todos, "chat", modelo, {},
            pasta_ia / "pedido_chat.json", pasta_ia / "resposta_chat.json", cfg, exigir_descricoes=True,
            cobertura=pedido.get("cobertura"))
        m["modelo_declarado_pela_ia"] = modelo
        ex.etapa_fim(vid, "interpretar", status, msg, m)
    except Exception as e:
        ex.etapa_fim(vid, "interpretar", "falha", f"resposta da IA não pôde ser importada: {e}", {"erro": str(e)})
        status = "falha"
    video = dict(con.execute("SELECT * FROM videos WHERE video_id=?", (vid,)).fetchone())
    pipeline.rodar_etapa(ex, vid, "relatorio", lambda: pipeline.etapa_relatorio(ex, con, vid, pasta, video))
    pipeline.atualizar_lista_pendentes(con)
    return status


def importar_prontos(disparada_por="terminal"):
    con = db.conectar()
    lista = prontos(con)
    if not lista:
        return 0
    ex = Execucao({"importacao_ia": [r["video_id"] for r in lista]}, len(lista), "chat", None, disparada_por)
    cont = {}
    for r in lista:
        ex.evento(r["video_id"], None, "info", "video_inicio", "Resposta da IA encontrada; importando")
        st = importar_video(ex, con, r["video_id"], C.BASE / r["pasta"])
        cont[st] = cont.get(st, 0) + 1
        ex.evento(r["video_id"], None, "info", "video_fim", f"Importação: {st}", {"interpretar": st})
    ex.encerrar("concluida", f"{len(lista)} resposta(s) da IA importada(s): " + ", ".join(f"{v} {k}" for k, v in cont.items()))
    return len(lista)


if __name__ == "__main__":
    C.utf8_stdout()
    n = importar_prontos()
    print(f"{n} resposta(s) importada(s)." if n else "Nenhuma resposta nova da IA para importar.")
    sys.exit(0)
