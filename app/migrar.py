"""Migração da fase anterior (ChatGPT/Codex) para a estrutura nova. NÃO apaga nada.

  python -m app.migrar            -> só simula e mostra o plano
  python -m app.migrar --executar -> move a fase antiga para arquivo/, importa os dados no banco novo e confere contagens

Tudo que é movido fica listado em arquivo/<pasta>/MOVIMENTACOES.csv. A migração aparece no painel como uma execução.
"""
import argparse, csv, json, shutil, sqlite3, sys
from pathlib import Path
from . import config as C, db
from .registro import Execucao

FICA = {".venv", "app", "dados", "logs", "relatorios", "curriculos", "arquivo", "listas", "config.json", ".env",
        ".env.exemplo", "ABRIR_PAINEL.bat", "RODAR_TERMINAL.bat", "LEIA-ME.md", "MAPA_DO_PROJETO.md", "AGENTS.md", "CLAUDE.md"}
NOME_ARQ = "fase1_chatgpt_2026-10-16"
ORIGEM = "migrado:fase-chatgpt"


def plano():
    destino = C.ARQUIVO / NOME_ARQ
    mover = [p for p in sorted(C.BASE.iterdir()) if p.name not in FICA]
    # AGENTS.md / CLAUDE.md / MAPA antigos também vão para o arquivo (serão reescritos)
    for nome in ("AGENTS.md", "CLAUDE.md", "MAPA_DO_PROJETO.md"):
        p = C.BASE / nome
        if p.exists() and not (destino / nome).exists():
            mover.append(p)
    return destino, mover


def caminho_antigo(destino, p):
    """Converte um caminho da fase antiga para o novo local dentro de arquivo/."""
    if not p:
        return None
    s = str(p).replace("\\", "/")
    for pref in ("S:/CV/", "s:/CV/", "S:/cv/"):
        if s.startswith(pref):
            s = s[len(pref):]
    return C.rel(destino / s)


def importar_cvdb(con, ex, destino):
    antigo = destino / "cv.db"
    if not antigo.exists():
        return {}
    o = sqlite3.connect(f"file:{antigo}?mode=ro", uri=True)
    o.row_factory = sqlite3.Row
    cont = {}
    for v in o.execute("SELECT * FROM videos"):
        vid = v["video_id"]
        # copia o vídeo para a estrutura nova, para poder ser reprocessado pelo programa novo
        pasta = C.VIDEOS / (v["perfil"] or "desconhecido") / vid
        pasta.mkdir(parents=True, exist_ok=True)
        orig = next(iter(sorted((destino / "videos").glob(f"*{vid}*.mp4"))), None) if (destino / "videos").exists() else None
        arq_video = None
        if orig:
            shutil.copy2(orig, pasta / "video.mp4")
            arq_video = C.rel(pasta / "video.mp4")
            info = orig.with_suffix(".info.json")
            if info.exists():
                shutil.copy2(info, pasta / "video.info.json")
        con.execute("INSERT OR REPLACE INTO videos(video_id,perfil,url,titulo,descricao,duracao_s,pasta,arquivo_video,origem,criado_em,atualizado_em)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (vid, v["perfil"], v["url"], (v["descricao"] or vid)[:120], v["descricao"], v["duracao_s"],
                     C.rel(pasta), arq_video, ORIGEM, v["processado_em"], db.agora()))
        con.execute("INSERT INTO notas(video_id,tipo,texto,origem) VALUES(?,?,?,?)",
                    (vid, "metodo_fase_anterior", v["metodo"], ORIGEM))
    falas = o.execute("SELECT * FROM falas ORDER BY video_id, inicio_s").fetchall()
    for i, f in enumerate(falas):
        con.execute("INSERT INTO falas(video_id,n,inicio_s,fim_s,texto,confianca,origem) VALUES(?,?,?,?,?,?,?)",
                    (f["video_id"], i, f["inicio_s"], f["fim_s"], f["texto"], None, f"{ORIGEM} ({f['revisao']})"))
    cont["falas"] = len(falas)
    mapa = {}
    frames = o.execute("SELECT * FROM frames ORDER BY video_id, t_s").fetchall()
    for i, f in enumerate(frames):
        mapa[f["id"]] = i
        con.execute("INSERT INTO frames(video_id,n,t_s,arquivo,unico,mostra_cv,origem) VALUES(?,?,?,?,?,?,?)",
                    (f["video_id"], i, f["t_s"], caminho_antigo(destino, f["arquivo"]), 1, f["mostra_cv"], ORIGEM))
    cont["frames"] = len(frames)
    cvs = o.execute("SELECT * FROM cv_exemplos").fetchall()
    for c in cvs:
        con.execute("INSERT INTO cv_exemplos(video_id,frame_n,secao,texto_lido,legibilidade,origem) VALUES(?,?,?,?,?,?)",
                    (c["video_id"], mapa.get(c["frame_id"]), c["secao"],
                     (c["texto_lido"] or "") + (f"\n[nota: {c['notas']}]" if c["notas"] else ""), c["legibilidade"], ORIGEM))
    cont["cv_exemplos"] = len(cvs)
    recs = o.execute("SELECT * FROM recomendacoes").fetchall()
    for r in recs:
        con.execute("INSERT INTO recomendacoes(video_id,inicio_s,fim_s,categoria,tipo,recomendacao,citacao,citacao_verificada,"
                    "frame_n,confianca,origem,validacao) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (r["video_id"], r["inicio_s"], r["fim_s"], r["categoria"], None,
                     (r["titulo"] + ": " if r["titulo"] else "") + (r["recomendacao"] or ""), r["citacao"], None,
                     mapa.get(r["frame_id"]), r["certeza_extracao"], f"{ORIGEM} (origem: {r['origem']})",
                     "pendente"))
    cont["recomendacoes"] = len(recs)
    n_notas = 0
    for tabela, tipo, campo in (("observacoes", "analise_fase_anterior", "texto"), ("incertezas", "trecho_duvidoso", None),
                                ("recursos", "recurso_citado", None)):
        try:
            rows = o.execute(f"SELECT * FROM {tabela}").fetchall()
        except sqlite3.OperationalError:
            continue
        for r in rows:
            d = dict(r)
            if tabela == "incertezas":
                txt, ini, fim = f"{d['termo']} — {d['notas']}", d["inicio_s"], d["fim_s"]
            elif tabela == "recursos":
                txt, ini, fim = f"{d['rotulo']} ({d['origem']}): {d['status']}. {d['notas'] or ''}", None, None
            else:
                txt, ini, fim = d["texto"], None, None
            con.execute("INSERT INTO notas(video_id,tipo,inicio_s,fim_s,texto,origem) VALUES(?,?,?,?,?,?)",
                        (d["video_id"], tipo, ini, fim, txt, ORIGEM))
            n_notas += 1
    cont["notas_cvdb"] = n_notas
    return cont


def ler_csv(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def importar_lote_ia(con, destino):
    base = destino / "processamento_ia"
    if not (base / "analises_ia.json").exists():
        return {}
    d = json.loads((base / "analises_ia.json").read_text(encoding="utf-8-sig"))
    cont = {"videos_lote": 0, "falas_lote": 0, "frames_lote": 0, "notas_lote": 0}
    for v in d.get("videos", []):
        vid = v["video_id"]
        con.execute("INSERT OR REPLACE INTO videos(video_id,perfil,url,titulo,duracao_s,pasta,origem,criado_em,atualizado_em,sha256)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (vid, "manual (snaptik, origem desconhecida)", None,
                     v.get("titulo_descritivo_atribuido_pela_ia") or vid, v.get("duracao_s"),
                     C.rel(base / vid), ORIGEM, db.agora(), db.agora(), v.get("sha256")))
        cont["videos_lote"] += 1
        for tipo, chave in (("resumo_fase_anterior", "resumo"), ("aplicacao_no_projeto", "aplicacao_no_projeto"),
                            ("ressalvas", "ressalvas")):
            if v.get(chave):
                con.execute("INSERT INTO notas(video_id,tipo,texto,origem) VALUES(?,?,?,?)", (vid, tipo, v[chave], ORIGEM))
                cont["notas_lote"] += 1
        for e in v.get("evidencias") or []:
            con.execute("INSERT INTO notas(video_id,tipo,inicio_s,fim_s,texto,origem) VALUES(?,?,?,?,?,?)",
                        (vid, f"evidencia ({e.get('origem')})", e.get("inicio_s"), e.get("fim_s"), e.get("texto"), ORIGEM))
            cont["notas_lote"] += 1
        con.execute("INSERT INTO notas(video_id,tipo,texto,origem) VALUES(?,?,?,?)",
                    (vid, "arquivo_original", f"{v.get('arquivo_original')} (enviado à Lixeira na fase anterior)", ORIGEM))
    if (base / "falas.csv").exists():
        for r in ler_csv(base / "falas.csv"):
            con.execute("INSERT INTO falas(video_id,n,inicio_s,fim_s,texto,origem) VALUES(?,?,?,?,?,?)",
                        (r["video_id"], int(r["numero"]), float(r["inicio_s"]), float(r["fim_s"]), r["texto"],
                         f"{ORIGEM} ({r.get('estado')})"))
            cont["falas_lote"] += 1
    if (base / "frames.csv").exists():
        for r in ler_csv(base / "frames.csv"):
            con.execute("INSERT INTO frames(video_id,n,t_s,arquivo,unico,origem) VALUES(?,?,?,?,?,?)",
                        (r["video_id"], int(r["numero"]), float(r["t_s"]), caminho_antigo(destino, r["arquivo"]), 1, ORIGEM))
            cont["frames_lote"] += 1
    return cont


def contar_antigo(destino_ou_base):
    """Conta as linhas da fase antiga, antes de importar, para comparar depois."""
    r = {}
    cvdb = destino_ou_base / "cv.db"
    if cvdb.exists():
        o = sqlite3.connect(f"file:{cvdb}?mode=ro", uri=True)
        for t in ("videos", "falas", "frames", "cv_exemplos", "recomendacoes", "observacoes", "incertezas", "recursos"):
            try:
                r[f"cv.db/{t}"] = o.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except sqlite3.OperationalError:
                pass
    base = destino_ou_base / "processamento_ia"
    if (base / "falas.csv").exists():
        r["lote/falas.csv"] = len(ler_csv(base / "falas.csv"))
        r["lote/frames.csv"] = len(ler_csv(base / "frames.csv"))
        r["lote/videos"] = len(json.loads((base / "analises_ia.json").read_text(encoding="utf-8-sig")).get("videos", []))
    return r


def main():
    C.utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--executar", action="store_true")
    a = ap.parse_args()
    destino, mover = plano()
    print(f"Pasta do projeto: {C.BASE}")
    print(f"Destino do material antigo: {C.rel(destino)}")
    print(f"Itens a mover ({len(mover)}):")
    for p in mover:
        print(f"  {'[pasta]' if p.is_dir() else '[arq]  '} {p.name}")
    antes = contar_antigo(C.BASE)
    print("Contagens da fase antiga (antes):", json.dumps(antes, ensure_ascii=False))
    if C.DB_PATH.exists():
        print("ATENÇÃO: dados/cv.db já existe; a migração não será refeita.")
        return 1
    if not a.executar:
        print("\nSIMULAÇÃO: nada foi alterado. Rode com --executar para aplicar.")
        return 0

    C.garantir_pastas()
    destino.mkdir(parents=True, exist_ok=True)
    ex = Execucao({"migracao": True, "itens": [p.name for p in mover]}, len(mover), "nenhuma", None, "migracao")
    falhas_mov = []
    with open(destino / "MOVIMENTACOES.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["origem", "destino", "tipo", "resultado"])
        for p in mover:
            alvo = destino / p.name
            tipo = "pasta" if p.is_dir() else "arquivo"
            try:
                shutil.move(str(p), str(alvo))
                w.writerow([p.name, C.rel(alvo), tipo, "movido"])
                ex.evento(None, None, "info", "movido", f"Movido para o arquivo: {p.name}")
            except Exception as e:
                falhas_mov.append(p.name)
                w.writerow([p.name, C.rel(alvo), tipo, f"FALHOU: {e}"])
                ex.evento(None, None, "erro", "falha", f"Não consegui mover {p.name}: {e}")
            f.flush()
    ex.checagem(None, None, "migração: itens movidos para arquivo/", len(mover), len(mover) - len(falhas_mov),
                "ok" if not falhas_mov else "alerta", "" if not falhas_mov else "Ficaram no lugar: " + ", ".join(falhas_mov))
    con = db.conectar()
    c1 = importar_cvdb(con, ex, destino)
    c2 = importar_lote_ia(con, destino)
    con.commit()
    depois = {**c1, **c2}
    ex.evento(None, None, "info", "importado", "Dados importados no banco novo", depois)
    pares = [("falas do vídeo do Victhor", antes.get("cv.db/falas"), c1.get("falas")),
             ("imagens do vídeo do Victhor", antes.get("cv.db/frames"), c1.get("frames")),
             ("trechos de CV lidos", antes.get("cv.db/cv_exemplos"), c1.get("cv_exemplos")),
             ("recomendações", antes.get("cv.db/recomendacoes"), c1.get("recomendacoes")),
             ("notas (observações+incertezas+recursos)",
              sum(antes.get(f"cv.db/{t}", 0) for t in ("observacoes", "incertezas", "recursos")), c1.get("notas_cvdb")),
             ("vídeos do lote sobre IA", antes.get("lote/videos"), c2.get("videos_lote")),
             ("falas do lote sobre IA", antes.get("lote/falas.csv"), c2.get("falas_lote")),
             ("imagens do lote sobre IA", antes.get("lote/frames.csv"), c2.get("frames_lote"))]
    falhou = False
    for nome, a_, d_ in pares:
        st = "ok" if a_ == d_ else "falha"
        falhou |= st == "falha"
        ex.checagem(None, None, f"migração: {nome}", a_, d_, st, "" if st == "ok" else "Contagem diferente: dados podem ter se perdido.")
        print(f"  [{st}] {nome}: antes {a_} · depois {d_}")
    faltando = [r["arquivo"] for r in db.linhas(con, "SELECT arquivo FROM frames WHERE arquivo IS NOT NULL")
                if not (C.BASE / r["arquivo"]).exists()]
    st = "ok" if not faltando else "alerta"
    ex.checagem(None, None, "migração: arquivos de imagem encontrados no novo caminho", "todos",
                f"faltam {len(faltando)}", st, "; ".join(faltando[:5]))
    print(f"  [{st}] imagens com caminho válido (faltando: {len(faltando)})")
    ex.encerrar("concluida" if not falhou else "falhou",
                f"migração: {len(mover)} itens movidos para {C.rel(destino)}; contagens {'conferem' if not falhou else 'NÃO conferem'}")
    return 0 if not falhou else 1


if __name__ == "__main__":
    sys.exit(main())
