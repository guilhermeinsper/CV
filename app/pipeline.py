"""Pipeline de vídeos: baixar → transcrever → imagens → integridade → interpretar (IA) → relatório.

Uso (na pasta S:\\CV):
  .venv\\Scripts\\python.exe -m app.pipeline --url https://www.tiktok.com/@perfil/video/123
  .venv\\Scripts\\python.exe -m app.pipeline --links listas\\victhor.txt --limite 3 --ia claude
  .venv\\Scripts\\python.exe -m app.pipeline --arquivo C:\\Downloads\\video.mp4 --ia nenhuma

Cada etapa registra início, progresso, fim e checagens (ver app/registro.py).
"""
import argparse, hashlib, json, math, re, shutil, subprocess, sys, time, traceback
from pathlib import Path
from . import config as C, db, ia, texto
from .registro import Execucao

PROMPT_WHISPER = ("Currículo, estágio, mercado financeiro, DCM, ECM, M&A, research, investment banking, "
                  "valuation, Excel, PowerPoint, VBA, bullet points, LinkedIn, Itaú BBA, BTG, XP, J.P. Morgan.")


# ------------------------------------------------------------------ utilidades
def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def ffprobe(p):
    exe = C.ffmpeg("ffprobe")
    if not exe:
        raise RuntimeError("ffprobe não encontrado (instale o ffmpeg)")
    r = subprocess.run([exe, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
                        "-of", "json", str(p)], capture_output=True, text=True, timeout=60)
    d = json.loads(r.stdout or "{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    tem_audio = any(s.get("codec_type") == "audio" for s in d.get("streams", []))
    return {"duracao_s": float(d.get("format", {}).get("duration") or 0), "largura": v.get("width"),
            "altura": v.get("height"), "tem_audio": tem_audio}


def dhash(caminho, n):
    from PIL import Image
    g = Image.open(caminho).convert("L").resize((n + 1, n))
    px = list(g.getdata())
    return [px[r * (n + 1) + c] > px[r * (n + 1) + c + 1] for r in range(n) for c in range(n)]


def dist_hash(a, b):
    return sum(x != y for x, y in zip(a, b))


def limiar_agrupar(cfg):
    n = cfg["agrupar_tamanho"]
    return round(cfg["agrupar_limiar"] * n * n)


def agrupar(hashes, limiar):
    """Agrupamento guloso em ordem de tempo: uma imagem só é 'diferente' se estiver longe de TODAS as já guardadas.
    Devolve, para cada posição, None (é representante) ou o índice do representante mais parecido."""
    reps, rep_de = [], []
    for i, h in enumerate(hashes):
        melhor = min(((dist_hash(h, hashes[j]), j) for j in reps), default=None)
        if melhor is None or melhor[0] > limiar:
            reps.append(i)
            rep_de.append(None)
        else:
            rep_de.append(melhor[1])
    return rep_de


def fmt(s):
    s = int(round(s or 0))
    return f"{s // 60:02d}:{s % 60:02d}"


def entrada_info(tipo, valor):
    if tipo == "url":
        if "/photo/" in valor:
            raise ValueError(f"post de FOTOS (carrossel), não é vídeo; ainda não suportado: {valor}")
        yt = re.search(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/)|youtu\.be/)([\w-]{11})", valor)
        if yt:  # YouTube: o perfil (canal) vem dos metadados do download
            return {"tipo": "url", "valor": f"https://www.youtube.com/watch?v={yt.group(1)}", "video_id": "yt_" + yt.group(1),
                    "perfil": "desconhecido"}
        if texto.e_texto_url(valor):  # Reddit, páginas de bancos/universidades, guias…
            return {"tipo": "url", "valor": texto.normalizar_url(valor), "video_id": texto.id_de_url(valor),
                    "perfil": texto.perfil_de_url(valor)}
        m = re.search(r"/video/(\d+)", valor)
        p = re.search(r"/@([^/?#]+)", valor)
        if not m:
            raise ValueError(f"link sem /video/<id>: {valor}")
        return {"tipo": "url", "valor": valor, "video_id": m.group(1), "perfil": p.group(1) if p else "desconhecido"}
    caminho = Path(valor)
    if not caminho.exists():
        raise ValueError(f"arquivo não existe: {valor}")
    if texto.e_texto_arquivo(caminho):
        return {"tipo": "arquivo", "valor": str(caminho), "video_id": "tx_" + sha256(caminho)[:16], "perfil": "arquivo_texto"}
    return {"tipo": "arquivo", "valor": str(caminho), "video_id": "local_" + sha256(caminho)[:20], "perfil": "manual"}


def ja_ok(con, vid, etapa):
    r = con.execute("SELECT status, fim FROM etapas WHERE video_id=? AND etapa=?", (vid, etapa)).fetchone()
    return r and r["status"] in ("ok", "alerta"), (r["fim"] if r else None)


# ------------------------------------------------------------------ etapa 1: baixar
def etapa_baixar(ex, con, ent, pasta, cfg, refazer):
    vid = ent["video_id"]
    pasta.mkdir(parents=True, exist_ok=True)
    existente = next((p for p in pasta.glob("video.*") if p.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv")), None)
    if existente and not refazer:
        origem_msg = "já estava baixado; mantido"
    elif ent["tipo"] == "url":
        cmd = [sys.executable, "-m", "yt_dlp", "--impersonate", "chrome", "--socket-timeout", "20", "--retries", "2",
               "--no-check-formats", "-S", "vcodec:h264,res:1080", "--write-info-json", "--no-progress",
               "--force-overwrites", "-o", str(pasta / "video.%(ext)s"), ent["valor"]]
        ex.evento(vid, "baixar", "progresso", "rodando", "Chamando yt-dlp (imitando o Chrome)…", {"comando": cmd[2:]})
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=cfg["timeout_download_s"],
                               encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"download passou de {cfg['timeout_download_s']} s e foi interrompido")
        (pasta / "download_log.txt").write_text((r.stdout or "") + "\n--- erros ---\n" + (r.stderr or ""), encoding="utf-8")
        if r.returncode != 0:
            ultimas = [l for l in (r.stderr or "").splitlines() if l.strip()]
            raise RuntimeError("yt-dlp falhou: " + (ultimas[-1][:300] if ultimas else f"código {r.returncode}")
                               + " (detalhes em download_log.txt)")
        existente = next((p for p in pasta.glob("video.*") if p.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv")), None)
        origem_msg = "baixado agora pelo yt-dlp"
    else:
        destino = pasta / ("video" + Path(ent["valor"]).suffix.lower())
        shutil.copy2(ent["valor"], destino)
        existente = destino
        origem_msg = "copiado do arquivo local (o original não foi alterado)"
    if not existente or existente.stat().st_size == 0:
        raise RuntimeError("arquivo de vídeo não encontrado ou vazio após o download")

    meta = {}
    info = pasta / "video.info.json"
    if info.exists():
        d = json.loads(info.read_text(encoding="utf-8"))
        meta = {"titulo": (d.get("title") or "")[:300], "descricao": d.get("description"),
                "duracao": d.get("duration"), "views": d.get("view_count"), "publicado": d.get("upload_date"),
                "perfil": d.get("uploader_id") or d.get("uploader"), "url": d.get("webpage_url")}
    pr = ffprobe(existente)
    tamanho, h = existente.stat().st_size, sha256(existente)
    agora = db.agora()
    con.execute(
        "INSERT INTO videos(video_id,perfil,url,titulo,descricao,duracao_s,views,publicado_em,pasta,arquivo_video,sha256,"
        "tamanho_bytes,origem,criado_em,atualizado_em,ultima_execucao) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT(video_id) DO UPDATE SET perfil=excluded.perfil,url=COALESCE(excluded.url,videos.url),"
        "titulo=COALESCE(excluded.titulo,videos.titulo),descricao=COALESCE(excluded.descricao,videos.descricao),"
        "duracao_s=excluded.duracao_s,views=COALESCE(excluded.views,videos.views),"
        "publicado_em=COALESCE(excluded.publicado_em,videos.publicado_em),pasta=excluded.pasta,"
        "arquivo_video=excluded.arquivo_video,sha256=excluded.sha256,tamanho_bytes=excluded.tamanho_bytes,"
        "atualizado_em=excluded.atualizado_em,ultima_execucao=excluded.ultima_execucao",
        (vid, ent["perfil"] if ent["perfil"] != "desconhecido" else (meta.get("perfil") or "desconhecido"),
         meta.get("url") or (ent["valor"] if ent["tipo"] == "url" else None), meta.get("titulo") or Path(ent["valor"]).name,
         meta.get("descricao"), pr["duracao_s"], meta.get("views"), meta.get("publicado"), C.rel(pasta),
         C.rel(existente), h, tamanho, "programa", agora, agora, ex.id))
    con.commit()

    status = "ok"
    ex.checagem(vid, "baixar", "arquivo de vídeo existe e não está vazio", "> 0 bytes", f"{tamanho} bytes", "ok", "")
    ex.checagem(vid, "baixar", "vídeo tem faixa de áudio", "sim", "sim" if pr["tem_audio"] else "não",
                "ok" if pr["tem_audio"] else "alerta", "" if pr["tem_audio"] else "Sem áudio não há o que transcrever.")
    if not pr["tem_audio"]:
        status = "alerta"
    if meta.get("duracao"):
        dif = abs(pr["duracao_s"] - float(meta["duracao"]))
        st = "ok" if dif <= 2 else "alerta"
        ex.checagem(vid, "baixar", "duração do arquivo = duração informada pelo TikTok", f"{meta['duracao']} s",
                    f"{pr['duracao_s']:.1f} s", st, "" if st == "ok" else "Download pode estar incompleto.")
        if st != "ok":
            status = "alerta"
    m = {"arquivo": C.rel(existente), "tamanho_mb": round(tamanho / 1e6, 2), "duracao_s": round(pr["duracao_s"], 1),
         "resolucao": f"{pr['largura']}x{pr['altura']}", "sha256": h[:16] + "…", "como": origem_msg}
    return status, f"{origem_msg} · {fmt(pr['duracao_s'])} · {m['tamanho_mb']} MB · {m['resolucao']}", m


# ------------------------------------------------------------------ etapa 2: transcrever
_modelo_whisper = {}


def carregar_audio(caminho):
    """Extrai o áudio com o ffmpeg (16 kHz, mono). Não depende do PyAV, cuja versão nova quebrou o Whisper."""
    import numpy as np
    exe = C.ffmpeg("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg não encontrado")
    r = subprocess.run([exe, "-nostdin", "-loglevel", "error", "-i", str(caminho), "-vn", "-f", "s16le", "-ac", "1",
                        "-ar", "16000", "-"], capture_output=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg não conseguiu extrair o áudio: " + r.stderr.decode(errors="replace")[-300:])
    return np.frombuffer(r.stdout, np.int16).astype(np.float32) / 32768.0


def transcrever_arquivo(caminho, cfg, ao_progresso):
    """Transcrição local com faster-whisper. Separada para poder ser testada isoladamente."""
    from faster_whisper import WhisperModel
    audio = carregar_audio(caminho)
    if audio.size < 1600:  # menos de 0,1 s de áudio
        return [], {"idioma": None, "prob_idioma": None, "duracao_audio_s": round(audio.size / 16000, 2), "duracao_com_fala_s": 0}
    nome = cfg["modelo_whisper"]
    if nome not in _modelo_whisper:
        try:
            _modelo_whisper[nome] = WhisperModel(nome, device="cpu", compute_type="int8")
        except Exception as e:
            raise RuntimeError(f"não consegui carregar o modelo de transcrição '{nome}' ({e})")
    idioma = None if cfg["idioma"] == "auto" else cfg["idioma"]
    segs, info = _modelo_whisper[nome].transcribe(audio, language=idioma, vad_filter=True,
                                                   initial_prompt=PROMPT_WHISPER)
    saida = []
    for s in segs:
        saida.append({"inicio_s": round(s.start, 2), "fim_s": round(s.end, 2), "texto": s.text.strip(),
                      "confianca": round(s.avg_logprob, 3)})
        ao_progresso(saida[-1], info.duration)
    return saida, {"idioma": info.language, "prob_idioma": round(info.language_probability, 3),
                   "duracao_audio_s": round(info.duration, 2),
                   "duracao_com_fala_s": round(getattr(info, "duration_after_vad", info.duration) or 0, 2)}


def etapa_transcrever(ex, con, vid, pasta, video, cfg):
    ultimo = [0.0]

    def progresso(seg, total):
        if time.time() - ultimo[0] > 2:
            ultimo[0] = time.time()
            ex.evento(vid, "transcrever", "progresso", "rodando",
                      f"Transcrevendo… chegou em {fmt(seg['fim_s'])} de {fmt(total)}",
                      {"ate_s": seg["fim_s"], "total_s": total})

    segs, info = transcrever_arquivo(pasta / Path(video["arquivo_video"]).name, cfg, progresso)
    (pasta / "transcricao.json").write_text(json.dumps({"info": info, "segmentos": segs}, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    con.execute("DELETE FROM falas WHERE video_id=?", (vid,))
    con.executemany("INSERT INTO falas(video_id,n,inicio_s,fim_s,texto,confianca,origem) VALUES(?,?,?,?,?,?,?)",
                    [(vid, i, s["inicio_s"], s["fim_s"], s["texto"], s["confianca"], f"programa:whisper-{cfg['modelo_whisper']}")
                     for i, s in enumerate(segs)])
    con.commit()
    m = {"trechos": len(segs), **info, "ultimo_fim_s": segs[-1]["fim_s"] if segs else 0,
         "palavras": sum(len(s["texto"].split()) for s in segs)}
    if not segs:
        return "alerta", "nenhuma fala detectada (vídeo pode ser só imagem ou música)", m
    return "ok", f"{len(segs)} trechos · {m['palavras']} palavras · idioma {info['idioma']}", m


# ------------------------------------------------------------------ etapa 3: imagens
def etapa_imagens(ex, con, vid, pasta, video, cfg):
    exe = C.ffmpeg("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg não encontrado")
    intervalo = cfg["intervalo_frames_s"]
    destino, tmp = pasta / "frames", pasta / "_frames_tmp"
    shutil.rmtree(destino, ignore_errors=True)
    shutil.rmtree(tmp, ignore_errors=True)
    destino.mkdir(parents=True)
    tmp.mkdir()
    r = subprocess.run([exe, "-loglevel", "error", "-y", "-i", str(pasta / Path(video["arquivo_video"]).name),
                        "-vf", f"fps=1/{intervalo}", "-q:v", "3", str(tmp / "f_%05d.jpg")],
                       capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg falhou: " + (r.stderr or "")[-300:])
    arquivos = sorted(tmp.glob("f_*.jpg"))
    from PIL import Image
    linhas, guardados = [], []  # guardados: (n, hash)
    limiar = limiar_agrupar(cfg)
    for i, f in enumerate(arquivos):
        t = round(i * intervalo, 2)
        h = dhash(f, cfg["agrupar_tamanho"])
        melhor = min(((dist_hash(h, hg), ng) for ng, hg in guardados), default=None)
        if melhor is None or melhor[0] > limiar:
            nome = f"n{i:04d}_t{t:07.1f}.jpg"
            f.replace(destino / nome)
            w, hh = Image.open(destino / nome).size
            linhas.append((vid, i, t, C.rel(destino / nome), 1, None, w, hh, None, 0, "programa:ffmpeg"))
            guardados.append((i, h))
        else:
            f.unlink()
            linhas.append((vid, i, t, None, 0, melhor[1], None, None, None, 0, "programa:ffmpeg"))
        if i % 20 == 0:
            ex.evento(vid, "imagens", "progresso", "rodando", f"Comparando imagens… {i + 1} de {len(arquivos)}")
    shutil.rmtree(tmp, ignore_errors=True)
    con.execute("DELETE FROM frames WHERE video_id=?", (vid,))
    con.executemany("INSERT INTO frames(video_id,n,t_s,arquivo,unico,igual_a_n,largura,altura,mostra_cv,enviado_ia,origem)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?)", linhas)
    con.commit()
    unicos = sum(1 for l in linhas if l[4])
    m = {"amostradas": len(linhas), "unicas_guardadas": unicos, "repetidas_descartadas": len(linhas) - unicos,
         "intervalo_s": intervalo, "agrupamento": AGRUPAMENTO, "limiar_bits": limiar}
    return "ok", f"{len(linhas)} amostras (1 a cada {intervalo}s) · {unicos} diferentes guardadas", m


AGRUPAMENTO = "v2"
CONFERENCIA = "v3"  # versão das regras de conferência da resposta da IA (mudou → reconfere respostas já importadas)


def conferencia_antiga(con, vid):
    r = con.execute("SELECT status, metricas FROM etapas WHERE video_id=? AND etapa='interpretar'", (vid,)).fetchone()
    if not r or r["status"] not in ("ok", "alerta"):
        return False
    try:
        return json.loads(r["metricas"] or "{}").get("conferencia") != CONFERENCIA
    except ValueError:
        return True


def etapa_reagrupar(ex, con, vid, cfg):
    """Vídeos antigos: junta imagens quase iguais (mesmo fundo; só a pessoa/legenda mudou) SEM apagar arquivos."""
    frames = db.linhas(con, "SELECT n, arquivo, unico FROM frames WHERE video_id=? ORDER BY n", (vid,))
    cand = [f for f in frames if f["unico"] and f["arquivo"] and (C.BASE / f["arquivo"]).is_file()]
    if not cand:
        raise RuntimeError("nenhuma imagem guardada no disco para reagrupar; reprocesse o vídeo")
    hashes = []
    for i, f in enumerate(cand):
        hashes.append(dhash(C.BASE / f["arquivo"], cfg["agrupar_tamanho"]))
        if i % 20 == 0:
            ex.evento(vid, "imagens", "progresso", "rodando", f"Reagrupando imagens parecidas… {i + 1} de {len(cand)}")
    limiar = limiar_agrupar(cfg)
    rep_de = agrupar(hashes, limiar)
    juntadas = [(cand[r]["n"], vid, cand[i]["n"]) for i, r in enumerate(rep_de) if r is not None]
    con.executemany("UPDATE frames SET unico=0, igual_a_n=? WHERE video_id=? AND n=?", juntadas)
    con.commit()
    antes, depois = len(cand), len(cand) - len(juntadas)
    m = {"amostradas": len(frames), "unicas_guardadas": depois, "repetidas_descartadas": len(frames) - depois,
         "intervalo_s": cfg["intervalo_frames_s"], "agrupamento": AGRUPAMENTO, "limiar_bits": limiar,
         "reagrupadas_de": antes}
    return "ok", (f"{len(frames)} amostras · reagrupadas: {antes} → {depois} diferentes "
                  f"(quase iguais juntadas; arquivos mantidos)"), m


def precisa_reagrupar(con, vid):
    r = con.execute("SELECT status, metricas FROM etapas WHERE video_id=? AND etapa='imagens'", (vid,)).fetchone()
    if not r or r["status"] not in ("ok", "alerta"):
        return False
    try:
        m = json.loads(r["metricas"] or "{}")
    except ValueError:
        m = {}
    return m.get("agrupamento") != AGRUPAMENTO


def imagens_nao_vistas(con, vid):
    """Imagens diferentes que a IA ainda não recebeu (unico=1 e enviado_ia=0)."""
    return con.execute("SELECT COUNT(*) FROM frames WHERE video_id=? AND unico=1 AND COALESCE(enviado_ia,0)=0",
                       (vid,)).fetchone()[0]


# ------------------------------------------------------------------ etapa 4: integridade
def etapa_integridade(ex, con, vid, pasta, video, cfg):
    dur = video["duracao_s"] or 0
    falas = db.linhas(con, "SELECT inicio_s, fim_s FROM falas WHERE video_id=? ORDER BY n", (vid,))
    frames = db.linhas(con, "SELECT n, arquivo, unico FROM frames WHERE video_id=?", (vid,))
    piores = []

    def chk(nome, esp, obt, st, expl):
        ex.checagem(vid, "integridade", nome, esp, obt, st, expl)
        piores.append(st)

    bruto = pasta / "transcricao.json"
    st_tr = con.execute("SELECT status FROM etapas WHERE video_id=? AND etapa='transcrever'", (vid,)).fetchone()
    if st_tr and st_tr["status"] in ("falha", "interrompida"):
        # não repete a falha da transcrição como várias falhas de integridade: registra uma só vez, apontando a causa
        chk("transcrição disponível para conferir", "sim", "não", "alerta",
            "A etapa Transcrever falhou; a causa está nela. A transcrição não pôde ser conferida.")
        falas = None
    else:
        n_bruto = len(json.loads(bruto.read_text(encoding="utf-8"))["segmentos"]) if bruto.exists() else None
        chk("trechos no banco = trechos da transcrição bruta", n_bruto, len(falas),
            "ok" if n_bruto == len(falas) else "falha", "" if n_bruto == len(falas) else "Dados perdidos ao gravar no banco.")
    if falas is None:
        pass
    elif falas:
        fim = falas[-1]["fim_s"]
        cob = fim / dur if dur else 0
        sobra = dur - fim
        st = "ok" if sobra <= max(cfg["lacuna_alerta_s"], 0.15 * dur) else "alerta"
        chk("transcrição vai até o fim do vídeo", f"até ~{fmt(dur)}", f"até {fmt(fim)} ({cob:.0%})", st,
            "" if st == "ok" else f"Últimos {sobra:.0f}s sem fala reconhecida (pode ser música ou silêncio; confira).")
        lac, ant = [], 0.0
        for f in falas:
            if f["inicio_s"] - ant > cfg["lacuna_alerta_s"]:
                lac.append(f"{fmt(ant)}–{fmt(f['inicio_s'])}")
            ant = f["fim_s"]
        chk(f"sem lacunas de fala maiores que {cfg['lacuna_alerta_s']}s", "nenhuma", ", ".join(lac) or "nenhuma",
            "ok" if not lac else "alerta", "" if not lac else "Trechos sem fala: confira se o autor falava ali.")
    else:
        chk("existe fala transcrita", "≥ 1 trecho", "0", "alerta", "Nenhuma fala: só as imagens serão analisadas.")
    esperado = max(1, math.ceil(dur / cfg["intervalo_frames_s"])) if dur else None
    st = "ok" if esperado and abs(esperado - len(frames)) <= 1 else "falha"
    chk("imagens amostradas = duração ÷ intervalo", esperado, len(frames), st,
        "" if st == "ok" else "Faltam imagens em parte do vídeo.")
    unicos = [f for f in frames if f["unico"]]
    faltando = [f["n"] for f in unicos if not (C.BASE / f["arquivo"]).exists()]
    chk("arquivos das imagens guardadas existem no disco", len(unicos), len(unicos) - len(faltando),
        "ok" if not faltando else "falha", "" if not faltando else f"Imagens ausentes: {faltando[:10]}")
    status = "falha" if "falha" in piores else ("alerta" if "alerta" in piores else "ok")
    ok = piores.count("ok")
    return status, f"{ok} de {len(piores)} checagens ok", {"checagens": len(piores), "ok": ok,
                                                            "alertas": piores.count("alerta"), "falhas": piores.count("falha")}


# ------------------------------------------------------------------ etapa 5: interpretar (IA)
def escolher_pacote(unicos, cfg):
    """Escolhe as imagens do pacote da IA. Até o limite: todas. Acima: agrupa de novo com tolerância maior
    (até agrupar_limiar_max) e manda um representante por grupo. Devolve (enviados, cobertura), onde cobertura diz
    quantas imagens diferentes ficaram vistas ou representadas por uma enviada quase igual."""
    maximo = cfg["max_imagens_ia"]
    if len(unicos) <= maximo:
        return unicos, {"limiar": None, "representadas": len(unicos), "total": len(unicos)}
    n = cfg["agrupar_tamanho"]
    hashes = [dhash(C.BASE / f["arquivo"], n) for f in unicos]
    frac = cfg["agrupar_limiar"]
    while True:
        frac = round(min(frac + 0.01, cfg["agrupar_limiar_max"]), 2)
        lim = round(frac * n * n)
        rep_de = agrupar(hashes, lim)
        idx = [i for i, r in enumerate(rep_de) if r is None]
        if len(idx) <= maximo or frac >= cfg["agrupar_limiar_max"]:
            break
    if len(idx) > maximo:  # nem com a tolerância máxima coube: amostra uniforme dos representantes
        passo = len(idx) / maximo
        idx = [idx[int(i * passo)] for i in range(maximo)]
    cobertas = sum(1 for h in hashes if min(dist_hash(h, hashes[j]) for j in idx) <= lim)
    return [unicos[i] for i in idx], {"limiar": frac, "representadas": cobertas, "total": len(unicos)}


def escolher_frames(unicos, maximo):
    if len(unicos) <= maximo:
        return unicos
    passo = len(unicos) / maximo
    return [unicos[int(i * passo)] for i in range(maximo)]


INSTR_CHAT_EXTRA = """
Além do formato acima, inclua OBRIGATORIAMENTE:
 "modelo_declarado": "nome do modelo/app que fez esta análise (ex.: Claude no app, ChatGPT no app)",
 "descricoes_imagens": [{"n": <número>, "descricao": "o que aparece nesta imagem, 1 frase"}]  <- UMA para CADA imagem listada
 "pacote": "o código do pacote escrito no topo deste arquivo"  <- prova de que a resposta é deste pacote (ele pode ser refeito)
O programa confere se todas as imagens listadas foram descritas e se cada citação existe na transcrição.
"""


def preparar_pacote_chat(ex, con, vid, pasta, cfg):
    """Modo sem chave de API: o programa monta o pacote; a IA do chat (Claude/ChatGPT no app) responde num arquivo."""
    from . import texto as texto_mod
    e_texto = vid.startswith("tx_")
    falas = db.linhas(con, "SELECT n, inicio_s, fim_s, texto FROM falas WHERE video_id=? ORDER BY n", (vid,))
    frames_todos = db.linhas(con, "SELECT n, t_s, arquivo, unico FROM frames WHERE video_id=? ORDER BY n", (vid,))
    unicos = [f for f in frames_todos if f["unico"]]
    enviados, cobertura = escolher_pacote(unicos, cfg)
    pasta_ia = pasta / "ia"
    pasta_ia.mkdir(exist_ok=True)
    resp = pasta_ia / "resposta_chat.json"
    if resp.exists():  # resposta antiga de outro pacote não pode ser reaproveitada
        resp.replace(pasta_ia / f"resposta_chat_antiga_{time.strftime('%Y%m%d_%H%M%S')}.json")
    texto = "\n".join(f"[{f['inicio_s']:.1f}s–{f['fim_s']:.1f}s] {f['texto']}" for f in falas) or "(nenhuma fala detectada)"
    pedido = {"video_id": vid, "criado_em": db.agora(), "execucao_id": ex.id, "modo": "chat",
              'sha256_transcricao':sha256(pasta/'transcricao.json'),
              "trechos": len(falas), "imagens_enviadas": [{"n": f["n"], "t_s": f["t_s"], "arquivo": f["arquivo"]} for f in enviados],
              "imagens_unicas": len(unicos), "imagens_amostradas": len(frames_todos), "cobertura": cobertura,
              "transcricao_enviada": texto}
    (pasta_ia / "pedido_chat.json").write_text(json.dumps(pedido, ensure_ascii=False, indent=1), encoding="utf-8")
    L = ["# PARA A IA — interpretar este vídeo", "", f"Pacote: `{pedido['criado_em']}` (copie este código no campo \"pacote\" da resposta)", "",
         f"Grave sua resposta em: `{C.rel(resp)}` (JSON puro, UTF-8). Não altere nenhum outro arquivo.", "",
         "## Instruções", ia.INSTRUCOES, INSTR_CHAT_EXTRA, *([texto_mod.INSTR_TEXTO] if e_texto else []), "",
         *([] if e_texto else [f"## Imagens ({len(enviados)} de {len(unicos)} imagens diferentes do vídeo) — abra TODAS",
                               *[f"- Imagem n={f['n']} (t={f['t_s']:.1f}s): `{f['arquivo']}`" for f in enviados], ""]),
         f"## {'Texto da fonte' if e_texto else 'Transcrição automática'} ({len(falas)} trechos)", "```", texto, "```"]
    (pasta_ia / "PARA_IA.md").write_text("\n".join(L), encoding="utf-8")
    con.execute("UPDATE frames SET enviado_ia=0, mostra_cv=NULL WHERE video_id=?", (vid,))
    con.executemany("UPDATE frames SET enviado_ia=1 WHERE video_id=? AND n=?", [(vid, f["n"]) for f in enviados])
    con.commit()
    atualizar_lista_pendentes(con)
    return "aguardando_ia", (f"pacote pronto ({len(falas)} trechos + {len(enviados)}/{len(unicos)} imagens). "
                             f"Peça no chat: 'interprete os vídeos pendentes'"), {
        "modo": "chat", "pacote": C.rel(pasta_ia / "PARA_IA.md"), "trechos": len(falas),
        "imagens_no_pacote": f"{len(enviados)}/{len(unicos)}"}


def atualizar_lista_pendentes(con):
    from .estado import pendentes
    pend,_ = pendentes(con)
    L = ["# Vídeos aguardando interpretação pela IA", "",
         "Para cada item: abra o PARA_IA.md, siga as instruções e grave o resposta_chat.json na mesma pasta.",
         "O painel importa e confere a resposta sozinho (a cada poucos segundos).", ""]
    aviso = C.BASE / "revisoes" / "AVISOS_PARA_IA.md"  # recados do Claude (dono do código) para a IA que interpreta
    if aviso.exists():
        try:
            L += ["## ⚠ AVISOS DO CLAUDE — leia antes de continuar (arquivo revisoes/AVISOS_PARA_IA.md)", "",
                  aviso.read_text(encoding="utf-8").strip(), "", "---", ""]
        except OSError:
            pass
    L += [f"- [ ] {(p['titulo'] or p['video_id'])[:70]} → `{p['pasta']}/ia/PARA_IA.md`" for p in pend] or ["(nenhum pendente)"]
    import uuid
    target=C.DADOS/'PENDENTES_IA.md';tmp=target.with_name('PENDENTES_IA_'+uuid.uuid4().hex+'.tmp')
    tmp.write_text('\n'.join(L),encoding='utf-8');tmp.replace(target)
    return len(pend)


def etapa_interpretar(ex, con, vid, pasta, video, cfg, provedor, modelo):
    if provedor in (None, "nenhuma"):
        return "pulada", "IA desligada nesta execução (--ia nenhuma)", {}
    if provedor == "chat":
        return preparar_pacote_chat(ex, con, vid, pasta, cfg)
    chaves = C.chaves()
    nome_chave = {"claude": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}.get(provedor)
    if not chaves.get(nome_chave):
        return "pulada", f"sem chave {nome_chave} no arquivo .env — nada foi enviado à IA", {}
    falas = db.linhas(con, "SELECT n, inicio_s, fim_s, texto FROM falas WHERE video_id=? ORDER BY n", (vid,))
    frames_todos = db.linhas(con, "SELECT n, t_s, arquivo, unico FROM frames WHERE video_id=? ORDER BY n", (vid,))
    unicos = [f for f in frames_todos if f["unico"]]
    enviados, cobertura = escolher_pacote(unicos, cfg)
    texto = "\n".join(f"[{f['inicio_s']:.1f}s–{f['fim_s']:.1f}s] {f['texto']}" for f in falas) or "(nenhuma fala detectada)"
    ex.evento(vid, "interpretar", "progresso", "rodando",
              f"Enviando à IA ({provedor}/{modelo}): {len(falas)} de {len(falas)} trechos + {len(enviados)} de {len(unicos)} imagens diferentes")
    resposta_txt, uso, pedido, bruto = ia.chamar(provedor, modelo, texto,
                                                 [(f["n"], f["t_s"], C.BASE / f["arquivo"]) for f in enviados],
                                                 chaves[nome_chave], cfg)
    pasta_ia = pasta / "ia"
    pasta_ia.mkdir(exist_ok=True)
    carimbo = time.strftime("%Y%m%d_%H%M%S")
    arq_ped, arq_resp = pasta_ia / f"pedido_{carimbo}.json", pasta_ia / f"resposta_{carimbo}.json"
    arq_ped.write_text(json.dumps(pedido, ensure_ascii=False, indent=1), encoding="utf-8")
    arq_resp.write_text(json.dumps(bruto, ensure_ascii=False, indent=1), encoding="utf-8")
    d = ia.extrair_json(resposta_txt)
    return gravar_interpretacao(ex, con, vid, d, enviados, unicos, falas, frames_todos, provedor, modelo, uso,
                                arq_ped, arq_resp, cfg, exigir_descricoes=False, cobertura=cobertura)


def gravar_interpretacao(ex, con, vid, d, enviados, unicos, falas, frames_todos, provedor, modelo, uso,
                         arq_ped, arq_resp, cfg, exigir_descricoes, cobertura=None):
    origem = f"ia:{provedor}:{modelo}"
    cur = con.execute(
        "INSERT INTO analises_ia(ts,video_id,execucao_id,provedor,modelo,status,trechos_enviados,trechos_total,frames_enviados,"
        "frames_unicos,frames_total,tokens_entrada,tokens_saida,duracao_s,arquivo_pedido,arquivo_resposta,resumo,origem)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (db.agora(), vid, ex.id, provedor, modelo, "ok", len(falas), len(falas), len(enviados), len(unicos),
         len(frames_todos), uso.get("entrada"), uso.get("saida"), uso.get("duracao_s"), C.rel(arq_ped), C.rel(arq_resp),
         d.get("resumo"), origem))
    aid = cur.lastrowid
    # análises anteriores da IA são substituídas, exceto o que você já validou
    con.execute("DELETE FROM recomendacoes WHERE video_id=? AND origem LIKE 'ia:%' AND validacao='pendente' AND analise_id<>?", (vid, aid))
    con.execute("DELETE FROM cv_exemplos WHERE video_id=? AND origem LIKE 'ia:%' AND analise_id<>?", (vid, aid))
    con.execute("DELETE FROM notas WHERE video_id=? AND origem LIKE 'ia:%'", (vid,))
    enviados_n = {f["n"] for f in enviados}
    con.execute("UPDATE frames SET enviado_ia=0, mostra_cv=NULL WHERE video_id=?", (vid,))
    con.executemany("UPDATE frames SET enviado_ia=1, mostra_cv=0 WHERE video_id=? AND n=?", [(vid, n) for n in enviados_n])
    com_cv = [n for n in d.get("frames_com_cv") or [] if n in enviados_n]
    con.executemany("UPDATE frames SET mostra_cv=1 WHERE video_id=? AND n=?", [(vid, n) for n in com_cv])

    refs_invalidas = 0
    for c in d.get("cv_exemplos") or []:
        fn = c.get("frame_n")
        if fn is not None and fn not in enviados_n:
            refs_invalidas += 1
            fn = None
        con.execute("INSERT INTO cv_exemplos(video_id,analise_id,frame_n,secao,texto_lido,legibilidade,origem) VALUES(?,?,?,?,?,?,?)",
                    (vid, aid, fn, c.get("secao"), c.get("texto_lido"), c.get("legibilidade"), origem))
    transc_norm = ia.normalizar(" ".join(f["texto"] for f in falas))
    recs = d.get("recomendacoes") or []
    nao_conferidas = []
    for r_ in recs:
        cit = r_.get("citacao") or ""
        ok_cit = 1 if cit and ia.normalizar(cit) in transc_norm else 0
        if not ok_cit:
            nao_conferidas.append(cit[:60])
        fn = r_.get("frame_n")
        if fn is not None and fn not in enviados_n:
            refs_invalidas += 1
            fn = None
        con.execute("INSERT INTO recomendacoes(video_id,analise_id,inicio_s,fim_s,categoria,tipo,recomendacao,citacao,"
                    "citacao_verificada,aplica_a,frame_n,confianca,origem) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (vid, aid, r_.get("inicio_s"), r_.get("fim_s"), r_.get("categoria"), r_.get("tipo"),
                     r_.get("recomendacao"), cit, ok_cit, r_.get("aplica_a"), fn, r_.get("confianca"), origem))
    for t in d.get("trechos_duvidosos") or []:
        con.execute("INSERT INTO notas(video_id,tipo,inicio_s,fim_s,texto,origem) VALUES(?,?,?,?,?,?)",
                    (vid, "trecho_duvidoso", t.get("inicio_s"), t.get("fim_s"),
                     f"{t.get('texto', '')} — {t.get('motivo', '')}", origem))
    descritas = {x.get("n") for x in d.get("descricoes_imagens") or [] if x.get("descricao")}
    for x in d.get("descricoes_imagens") or []:
        if x.get("n") in enviados_n:
            con.execute("INSERT INTO notas(video_id,tipo,inicio_s,texto,origem) VALUES(?,?,?,?,?)",
                        (vid, f"descricao_imagem n={x.get('n')}", None, x.get("descricao"), origem))
    con.commit()

    piores = []

    def chk(nome, esp, obt, st, expl):
        ex.checagem(vid, "interpretar", nome, esp, obt, st, expl)
        piores.append(st)

    chk("trechos de fala no pacote da IA", len(falas), len(falas), "ok", "A transcrição inteira foi incluída.")
    if len(enviados) == len(unicos):
        chk("imagens diferentes no pacote da IA", len(unicos), len(enviados), "ok", "Todas as imagens diferentes foram enviadas.")
    elif cobertura and cobertura.get("limiar"):
        falta = cobertura["total"] - cobertura["representadas"]
        chk("imagens diferentes vistas ou representadas no pacote da IA", cobertura["total"], cobertura["representadas"],
            "ok" if falta == 0 else "alerta",
            (f"{len(enviados)} imagens enviadas; as outras {len(unicos) - len(enviados)} diferem até "
             f"{round(cobertura['limiar'] * 100)}% de uma enviada (mesma tela, só a pessoa/legenda mudou).")
            if falta == 0 else f"{falta} imagens diferentes NÃO foram vistas nem representadas (limite de {cfg['max_imagens_ia']}).")
    else:
        chk("imagens diferentes no pacote da IA", len(unicos), len(enviados), "alerta",
            f"Limite de {cfg['max_imagens_ia']} imagens: as demais NÃO foram vistas pela IA.")
    if exigir_descricoes:
        faltam = sorted(enviados_n - descritas)
        chk("imagens descritas pela IA (prova de que abriu cada uma)", len(enviados_n), len(enviados_n & descritas),
            "ok" if not faltam else "alerta", "" if not faltam else f"Imagens sem descrição: {faltam[:15]}")
    chk("citações encontradas literalmente na transcrição", len(recs), len(recs) - len(nao_conferidas),
        "ok" if not nao_conferidas else "alerta",
        "" if not nao_conferidas else "Citações não encontradas (possível paráfrase ou invenção): " + " | ".join(nao_conferidas[:5]))
    refs_total = sum(1 for x in list(d.get("cv_exemplos") or []) + list(recs) if x.get("frame_n") is not None)
    chk("referências a imagens que existem no pacote", refs_total, refs_total - refs_invalidas,
        "ok" if not refs_invalidas else "alerta",
        f"{refs_total} referência(s) a imagens na resposta; todas são de imagens do pacote." if not refs_invalidas
        else f"{refs_invalidas} de {refs_total} referência(s) apontam para imagens que a IA não recebeu; foram removidas.")
    status = "alerta" if "alerta" in piores else "ok"
    m = {"provedor": provedor, "modelo": modelo, "trechos_enviados": f"{len(falas)}/{len(falas)}",
         "imagens_enviadas": f"{len(enviados)}/{len(unicos)}", "recomendacoes": len(recs),
         "citacoes_conferidas": f"{len(recs) - len(nao_conferidas)}/{len(recs)}",
         "secoes_cv_lidas": len(d.get("cv_exemplos") or []), "imagens_com_cv": len(com_cv)}
    m["conferencia"] = CONFERENCIA
    if exigir_descricoes:
        m["imagens_descritas"] = f"{len(enviados_n & descritas)}/{len(enviados_n)}"
    else:
        m.update(tokens_entrada=uso.get("entrada"), tokens_saida=uso.get("saida"), segundos=uso.get("duracao_s"))
    return status, (f"{len(recs)} recomendações · citações conferidas {m['citacoes_conferidas']} · "
                    f"{'imagens descritas ' + m['imagens_descritas'] if exigir_descricoes else 'viu ' + m['imagens_enviadas'] + ' imagens'}"), m


# ------------------------------------------------------------------ etapa 6: relatório
def etapa_relatorio(ex, con, vid, pasta, video):
    v = dict(con.execute("SELECT * FROM videos WHERE video_id=?", (vid,)).fetchone())
    et = db.linhas(con, "SELECT * FROM etapas WHERE video_id=? ORDER BY rowid", (vid,))
    ch = db.linhas(con, "SELECT * FROM checagens WHERE video_id=? AND execucao_id=? ORDER BY id", (vid, ex.id))
    recs = db.linhas(con, "SELECT * FROM recomendacoes WHERE video_id=? ORDER BY inicio_s", (vid,))
    L = [f"# {v.get('titulo') or vid}", "", f"- Perfil: {v.get('perfil')}", f"- Link: {v.get('url') or '-'}",
         f"- Duração: {fmt(v.get('duracao_s'))}", f"- Execução: {ex.id}", "", "## Etapas"]
    L += [f"- {db.NOMES_ETAPAS.get(e['etapa'], e['etapa'])}: **{e['status']}** — {e['mensagem'] or ''}" for e in et]
    L += ["", "## Checagens do programa"] + [f"- [{c['status']}] {c['nome']}: esperado {c['esperado']}, obtido {c['obtido']} {c['explicacao'] or ''}" for c in ch]
    L += ["", f"## Recomendações ({len(recs)})"]
    L += [f"- {fmt(r['inicio_s'])} [{r['categoria']}/{r['tipo']}] {r['recomendacao']} — “{r['citacao']}” "
          f"(citação {'conferida' if r['citacao_verificada'] else 'NÃO encontrada'}; validação: {r['validacao']}; origem {r['origem']})" for r in recs]
    (pasta / "RESUMO.md").write_text("\n".join(L), encoding="utf-8")
    return "ok", "RESUMO.md gerado na pasta do vídeo", {"arquivo": C.rel(pasta / "RESUMO.md")}


# ------------------------------------------------------------------ orquestração
def rodar_etapa(ex, vid, etapa, fn):
    ex.etapa_inicio(vid, etapa)
    try:
        status, msg, m = fn()
    except Exception as e:
        ex.etapa_fim(vid, etapa, "falha", f"ERRO: {e}", {"erro": str(e), "detalhe": traceback.format_exc()[-1500:]})
        return "falha"
    ex.etapa_fim(vid, etapa, status, msg, m)
    return status


def processar(ex, con, ent, cfg, args):
    vid = ent["video_id"]
    pasta = C.VIDEOS / re.sub(r"[^\w.\-]", "_", ent["perfil"]) / vid
    if not args.reprocessar:  # vídeo já existente: reaproveita a pasta onde ele está
        r = con.execute("SELECT pasta FROM videos WHERE video_id=?", (vid,)).fetchone()
        if r and r["pasta"] and (C.BASE / r["pasta"]).exists() and r["pasta"].startswith("dados/"):
            pasta = C.BASE / r["pasta"]
    resultado = {}
    # registra o vídeo JÁ NA ENTRADA: se o download falhar, ele aparece com título/link e pode ser reprocessado
    if not con.execute("SELECT 1 FROM videos WHERE video_id=?", (vid,)).fetchone():
        con.execute("INSERT INTO videos(video_id,perfil,url,titulo,pasta,origem,criado_em,atualizado_em,ultima_execucao) VALUES(?,?,?,?,?,?,?,?,?)",
                    (vid, ent["perfil"], ent["valor"] if ent["tipo"] == "url" else None,
                     ent["valor"] if ent["tipo"] == "url" else Path(ent["valor"]).name, C.rel(pasta), "programa",
                     db.agora(), db.agora(), ex.id))
        con.commit()

    def manter_ou(etapa, fn):
        if etapa == "interpretar" and not args.reprocessar and not args.refazer_ia:
            r = con.execute("SELECT status FROM etapas WHERE video_id=? AND etapa='interpretar'", (vid,)).fetchone()
            ped = pasta / "ia" / "pedido_chat.json"
            n_falas = con.execute("SELECT COUNT(*) FROM falas WHERE video_id=?", (vid,)).fetchone()[0]
            from .estado import pacote_valido
            velho = not pacote_valido(con,vid)[0]
            if r and r["status"] == "aguardando_ia" and velho:
                ex.evento(vid, "interpretar", "info", "rodando", "Pacote antigo não corresponde à transcrição atual; refazendo")
                return rodar_etapa(ex, vid, etapa, fn)
            faltam = imagens_nao_vistas(con, vid)
            n_unicos = con.execute("SELECT COUNT(*) FROM frames WHERE video_id=? AND unico=1", (vid,)).fetchone()[0]
            try:
                sem_cobertura = n_unicos > cfg["max_imagens_ia"] and "cobertura" not in json.loads(ped.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                sem_cobertura = False
            if r and r["status"] in ("aguardando_ia", "ok", "alerta") and faltam and (n_unicos <= cfg["max_imagens_ia"] or sem_cobertura):
                ex.evento(vid, "interpretar", "info", "rodando",
                          f"{faltam} imagem(ns) diferente(s) não estavam no pacote da IA; refazendo o pacote")
                return rodar_etapa(ex, vid, etapa, fn)
            if r and r["status"] in ("ok", "alerta") and (pasta / "ia" / "resposta_chat.json").exists() \
                    and conferencia_antiga(con, vid):
                ex.evento(vid, "interpretar", "info", "rodando", "Reconferindo a resposta da IA com as regras de conferência atuais")
                from .importar_ia import importar_video
                return "importada:" + importar_video(ex, con, vid, pasta)
            if r and r["status"] == "aguardando_ia":
                if (pasta / "ia" / "resposta_chat.json").exists():
                    from .importar_ia import importar_video
                    return "importada:" + importar_video(ex, con, vid, pasta)
                ex.etapa_inicio(vid, etapa)
                ex.etapa_fim(vid, etapa, "aguardando_ia", "pacote já está pronto; ainda sem resposta da IA",
                             {"pacote": C.rel(pasta / "ia" / "PARA_IA.md")})
                return "aguardando_ia"
        feito, quando = ja_ok(con, vid, etapa)
        if feito and not args.reprocessar and not (etapa == "interpretar" and args.refazer_ia):
            ant = dict(con.execute("SELECT status, mensagem, metricas FROM etapas WHERE video_id=? AND etapa=?",
                                   (vid, etapa)).fetchone())
            m = json.loads(ant["metricas"]) if ant["metricas"] else {}
            m.update(mantido=True, feito_em=str(quando)[:16])
            ex.etapa_inicio(vid, etapa)
            # mantém o status ORIGINAL (um alerta antigo continua alerta)
            msg_orig = re.sub(r"^(?:mantido de \d{4}-\d\d-\d\dT\d\d:\d\d: )+", "", ant["mensagem"] or "")
            ex.etapa_fim(vid, etapa, ant["status"], f"mantido de {str(quando)[:16]}: {msg_orig}", m)
            return ant["status"]
        return rodar_etapa(ex, vid, etapa, fn)

    e_texto = vid.startswith("tx_")
    if e_texto:
        resultado["baixar"] = rodar_etapa(ex, vid, "baixar", lambda: texto.etapa_baixar(ex, con, ent, pasta, cfg, args.reprocessar))
    else:
        resultado["baixar"] = rodar_etapa(ex, vid, "baixar", lambda: etapa_baixar(ex, con, ent, pasta, cfg, args.reprocessar))
    if resultado["baixar"] == "falha":
        for e in db.ETAPAS[1:]:
            ex.etapa_inicio(vid, e)
            ex.etapa_fim(vid, e, "pulada", "não executada: o download falhou")
        return resultado
    video = dict(con.execute("SELECT * FROM videos WHERE video_id=?", (vid,)).fetchone())
    if e_texto:
        # texto: trechos sempre recalculados do texto.md (rápido; se o texto não mudou, o pacote continua válido)
        resultado["transcrever"] = rodar_etapa(ex, vid, "transcrever", lambda: texto.etapa_trechos(ex, con, vid, pasta, video, cfg))
        resultado["imagens"] = rodar_etapa(ex, vid, "imagens", lambda: texto.etapa_sem_imagens(ex, con, vid, pasta, video, cfg))
        resultado["integridade"] = rodar_etapa(ex, vid, "integridade", lambda: texto.etapa_integridade(ex, con, vid, pasta, video, cfg))
    else:
        resultado["transcrever"] = manter_ou("transcrever", lambda: etapa_transcrever(ex, con, vid, pasta, video, cfg))
    if e_texto:
        pass
    elif not args.reprocessar and precisa_reagrupar(con, vid):
        resultado["imagens"] = rodar_etapa(ex, vid, "imagens", lambda: etapa_reagrupar(ex, con, vid, cfg))
    else:
        resultado["imagens"] = manter_ou("imagens", lambda: etapa_imagens(ex, con, vid, pasta, video, cfg))
    if not e_texto:
        resultado["integridade"] = rodar_etapa(ex, vid, "integridade", lambda: etapa_integridade(ex, con, vid, pasta, video, cfg))
    if resultado["transcrever"] == "falha" or resultado["integridade"] == "falha":
        motivo = "a transcrição falhou" if resultado["transcrever"] == "falha" else "a checagem de integridade falhou"
        ex.etapa_inicio(vid, "interpretar")
        ex.etapa_fim(vid, "interpretar", "pulada", f"não preparada para a IA porque {motivo}; corrija e reprocesse")
        resultado["interpretar"] = "pulada"
        atualizar_lista_pendentes(con)
    else:
        resultado["interpretar"] = manter_ou("interpretar", lambda: etapa_interpretar(
            ex, con, vid, pasta, video, cfg, args.ia, args.modelo))
        if str(resultado["interpretar"]).startswith("importada:"):  # o importador já gerou o relatório
            resultado["interpretar"] = resultado["interpretar"].split(":", 1)[1]
            resultado["relatorio"] = "ok"
            return resultado
    resultado["relatorio"] = rodar_etapa(ex, vid, "relatorio", lambda: etapa_relatorio(ex, con, vid, pasta, video))
    atualizar_lista_pendentes(con)
    return resultado


def main(argv=None):
    C.utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", action="append", default=[], help="link de vídeo (pode repetir)")
    ap.add_argument("--links", type=Path, help="arquivo .txt com um link por linha (# = comentário)")
    ap.add_argument("--arquivo", action="append", default=[], help="vídeo já baixado (pode repetir)")
    ap.add_argument("--limite", type=int, default=1, help="máximo de vídeos nesta execução (0 = todos). Padrão: 1")
    ap.add_argument("--ia", choices=["chat", "nenhuma", "claude", "openai"], default="chat",
                    help="chat (padrão): prepara o pacote para a IA do app; claude/openai: via API paga")
    ap.add_argument("--modelo", default=None)
    ap.add_argument("--reprocessar", action="store_true", help="refaz todas as etapas, mesmo as já feitas")
    ap.add_argument("--refazer-ia", action="store_true", help="refaz só a interpretação da IA")
    ap.add_argument("--disparada-por", default="terminal")
    args = ap.parse_args(argv)
    cfg = C.config()
    C.garantir_pastas()
    if args.ia in ("claude", "openai") and not args.modelo:
        args.modelo = cfg["modelos"][args.ia][0]

    brutas = [("url", u) for u in args.url] + [("arquivo", a) for a in args.arquivo]
    if args.links:
        for l in args.links.read_text(encoding="utf-8-sig").splitlines():
            l = l.strip()
            if l and not l.startswith("#"):
                brutas.append(("url", l))
    if args.limite > 0:
        brutas = brutas[: args.limite]
    if not brutas:
        ap.error("nenhuma entrada: use --url, --links ou --arquivo")

    ex = Execucao({"entradas": [b[1] for b in brutas], "ia": args.ia, "modelo": args.modelo,
                   "reprocessar": args.reprocessar, "refazer_ia": args.refazer_ia, "config": cfg},
                  len(brutas), args.ia, args.modelo, args.disparada_por)
    try:  # reinício do painel pedido por arquivo (atualização de código sem fechar a janela à mão)
        from . import reinicio
        reinicio.pedido_por_flag("pipeline")
    except Exception as e:
        print(f"[reinício do painel] não foi possível: {e}", flush=True)
    con = db.conectar()
    contagem = {"ok": 0, "com_alerta": 0, "com_falha": 0, "aguardando_IA": 0}
    try:
        for i, (tipo, valor) in enumerate(brutas, 1):
            try:
                ent = entrada_info(tipo, valor)
            except Exception as e:
                ex.evento(None, None, "erro", "falha", f"Entrada {i} ignorada: {e}")
                contagem["com_falha"] += 1
                continue
            ex.evento(ent["video_id"], None, "info", "video_inicio", f"Vídeo {i} de {len(brutas)}: {valor}",
                      {"indice": i, "total": len(brutas), "perfil": ent["perfil"]})
            res = processar(ex, con, ent, cfg, args)
            pior = ("com_falha" if "falha" in res.values() else "com_alerta" if "alerta" in res.values()
                    else "aguardando_IA" if "aguardando_ia" in res.values() else "ok")
            contagem[pior] += 1
            ex.evento(ent["video_id"], None, "info", "video_fim", f"Vídeo {i} terminou: {pior.replace('_', ' ')}", res)
            if tipo == "url" and i < len(brutas):
                time.sleep(cfg["pausa_entre_downloads_s"])
        resumo = (f"{len(brutas)} vídeo(s): {contagem['ok']} ok, {contagem['com_alerta']} com alerta, "
                  f"{contagem['com_falha']} com falha, {contagem['aguardando_IA']} aguardando a IA")
        ex.encerrar("concluida", resumo)
    except KeyboardInterrupt:
        ex.encerrar("interrompida", "interrompida pelo usuário (Ctrl+C)")
        return 130
    except Exception as e:
        ex.evento(None, None, "erro", "falha", f"Erro inesperado: {e}", {"detalhe": traceback.format_exc()[-2000:]})
        ex.encerrar("falhou", str(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
