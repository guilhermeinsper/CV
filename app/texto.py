"""Fontes de TEXTO (Reddit, páginas de bancos, guias de universidades, arquivos .md/.txt/.html).

Seguem as mesmas 6 etapas dos vídeos, adaptadas:
  baixar      → busca a página (ou copia o arquivo) e guarda texto.md + fonte.json + o original
  transcrever → divide o texto em trechos numerados (viram "falas"; a IA cita literalmente)
  imagens     → não há imagens (etapa ok, registrada como "fonte de texto")
  integridade → confere se o texto existe, tem tamanho mínimo e se os trechos no banco batem com o arquivo
  interpretar / relatório → iguais aos vídeos (o pacote vai sem imagens)
"""
import hashlib, html, json, re, time, urllib.parse, urllib.request
from html.parser import HTMLParser
from pathlib import Path
from . import config as C, db

EXTENSOES = (".md", ".txt", ".html", ".htm")
DOMINIOS_VIDEO = ("tiktok.com", "youtube.com", "youtu.be", "instagram.com")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
MIN_CARACTERES = 300
MAX_TRECHO = 600


def e_texto_url(url):
    u = str(url).lower()
    return u.startswith("http") and not any(d in u for d in DOMINIOS_VIDEO)


def e_texto_arquivo(caminho):
    return Path(str(caminho)).suffix.lower() in EXTENSOES


def normalizar_url(url):
    p = urllib.parse.urlsplit(str(url).strip())
    host = p.netloc.lower().replace("old.reddit.com", "www.reddit.com")
    if host == "reddit.com":
        host = "www.reddit.com"
    query = "" if "reddit.com" in host else urllib.parse.urlencode(
        [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if not k.lower().startswith("utm_")])
    return urllib.parse.urlunsplit((p.scheme.lower() or "https", host, p.path.rstrip("/") or "/", query, ""))


def id_de_url(url):
    return "tx_" + hashlib.sha1(normalizar_url(url).encode("utf-8")).hexdigest()[:16]


def perfil_de_url(url):
    p = urllib.parse.urlsplit(normalizar_url(url))
    m = re.match(r"/r/([^/]+)", p.path)
    if "reddit.com" in p.netloc and m:
        return "r/" + m.group(1)
    return "site:" + p.netloc.replace("www.", "")


# ------------------------------------------------------------------ leitura de HTML
EXTRATOR = "v2"  # v2: ignora menus/rodapés/barras laterais e prefere o conteúdo principal (<main>/<article>)
RUIDO = re.compile(r"(^|[\s_-])(nav|navbar|menu|footer|header|sidebar|cookie|modal|breadcrumb|share|social|related|"
                   r"comments?|newsletter|subscribe|banner|popup|signup|login|promo|advert|ads)([\s_-]|$)", re.I)
VAZIOS = {"br", "img", "hr", "input", "meta", "link", "source", "area", "base", "col", "embed", "param", "track", "wbr"}


class _Texto(HTMLParser):
    BLOCO = {"p", "li", "h1", "h2", "h3", "h4", "h5", "blockquote", "pre", "td", "dd", "dt", "br", "div", "section", "article"}
    PULAR = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "button", "iframe", "select"}

    def __init__(self, filtrar_classes=True):
        super().__init__(convert_charrefs=True)
        self.filtrar = filtrar_classes
        self.partes, self.atual, self.titulo, self._no_titulo = [], [], "", False
        self.pilha = []  # (tag, pula?, principal?)

    def _pulando(self):
        return any(x[1] for x in self.pilha)

    def _principal(self):
        return any(x[2] for x in self.pilha)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        marca = f"{a.get('class') or ''} {a.get('id') or ''} {a.get('role') or ''}"
        if tag in self.BLOCO:
            self._fecha()
        if tag not in VAZIOS:
            pula = tag in self.PULAR or (self.filtrar and (bool(RUIDO.search(marca)) or a.get("aria-hidden") == "true"))
            principal = tag in ("main", "article") or (a.get("role") == "main")
            self.pilha.append((tag, pula, principal))
        if tag == "title":
            self._no_titulo = True
        if tag in ("h1", "h2", "h3", "h4") and not self._pulando():
            self.atual.append("## ")
        if tag == "li" and not self._pulando():
            self.atual.append("- ")

    def handle_endtag(self, tag):
        if tag in self.BLOCO:
            self._fecha()
        if tag == "title":
            self._no_titulo = False
        for i in range(len(self.pilha) - 1, -1, -1):  # fecha até a tag correspondente (HTML mal formado)
            if self.pilha[i][0] == tag:
                del self.pilha[i:]
                break

    def handle_data(self, data):
        if self._no_titulo:
            self.titulo += data
        elif not self._pulando():
            self.atual.append(data)

    def _fecha(self):
        t = re.sub(r"\s+", " ", "".join(self.atual)).strip()
        if t and t not in ("##", "-"):
            self.partes.append((t, self._principal()))
        self.atual = []

    def resultado(self):
        self._fecha()
        principal = [t for t, p in self.partes if p]
        usar = principal if len(" ".join(principal)) >= 400 else [t for t, _ in self.partes]
        return self.titulo.strip(), "\n\n".join(usar)


def html_para_texto(conteudo):
    p = _Texto()
    p.feed(conteudo)
    titulo, texto = p.resultado()
    if len(texto) < 400:  # o filtro por classe apagou demais (ex.: o site inteiro dentro de um "wrapper-header"): sem ele
        q = _Texto(filtrar_classes=False)
        q.feed(conteudo)
        titulo2, texto2 = q.resultado()
        if len(texto2) > len(texto):
            return titulo2 or titulo, texto2
    return titulo, texto


def _baixar(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en,pt;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        bruto = r.read(5_000_000)
        cs = r.headers.get_content_charset() or "utf-8"
        return bruto.decode(cs, errors="replace"), r.headers.get_content_type()


def reddit_para_texto(dados):
    """JSON de um post do Reddit → (título, texto). Post + comentários (mais votados primeiro)."""
    post = dados[0]["data"]["children"][0]["data"]
    titulo = post.get("title") or ""
    partes = [f"# {titulo}", f"Post de u/{post.get('author')} em r/{post.get('subreddit')} · {post.get('score')} votos"]
    if post.get("selftext"):
        partes.append(post["selftext"].strip())
    coms = []

    def andar(lista, nivel):
        for ch in lista:
            d = ch.get("data") or {}
            if ch.get("kind") == "t1" and d.get("body") and d.get("body") not in ("[deleted]", "[removed]"):
                coms.append((d.get("score") or 0, nivel, d.get("author"), d["body"].strip()))
                rep = d.get("replies")
                if isinstance(rep, dict):
                    andar(rep["data"]["children"], nivel + 1)
    andar(dados[1]["data"]["children"], 0)
    coms.sort(key=lambda x: -x[0])
    for score, nivel, autor, corpo in coms[:40]:
        partes.append(f"Comentário de u/{autor} ({score} votos):\n{corpo}")
    return titulo, "\n\n".join(partes)


# ------------------------------------------------------------------ etapas
def etapa_baixar(ex, con, ent, pasta, cfg, refazer):
    vid = ent["video_id"]
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / "texto.md"
    fonte = {}
    antiga = json.loads((pasta / "fonte.json").read_text(encoding="utf-8")) if (pasta / "fonte.json").exists() else None
    if ent["tipo"] == "url" and antiga and antiga.get("extrator") != EXTRATOR and (pasta / "original.html").exists() and not refazer:
        # página já baixada com o extrator antigo: reextrai do HTML guardado (não baixa de novo)
        titulo, texto = html_para_texto((pasta / "original.html").read_text(encoding="utf-8"))
        fonte = {**antiga, "extrator": EXTRATOR, "reextraido_em": db.agora()}
        arq.write_text(texto, encoding="utf-8")
        como = f"texto reextraído do HTML guardado (extrator {EXTRATOR})"
    elif arq.exists() and not refazer and antiga:
        fonte = antiga
        como = "já estava salvo; mantido"
    elif ent["tipo"] == "url":
        url = normalizar_url(ent["valor"])
        ex.evento(vid, "baixar", "progresso", "rodando", f"Buscando a página: {url}")
        if "reddit.com" in url and "/comments/" in url:
            bruto, _ = _baixar(url + ".json?raw_json=1&limit=200", cfg["timeout_download_s"])
            (pasta / "original.json").write_text(bruto, encoding="utf-8")
            titulo, texto = reddit_para_texto(json.loads(bruto))
        else:
            bruto, tipo = _baixar(url, cfg["timeout_download_s"])
            if "html" in (tipo or "") or bruto.lstrip()[:1] == "<":
                (pasta / "original.html").write_text(bruto, encoding="utf-8")
                titulo, texto = html_para_texto(bruto)
            else:
                (pasta / "original.txt").write_text(bruto, encoding="utf-8")
                titulo, texto = "", bruto
        fonte = {"url": url, "titulo": html.unescape(titulo)[:300], "buscado_em": db.agora(), "como": "urllib (programa)",
                 "extrator": EXTRATOR}
        arq.write_text(texto, encoding="utf-8")
        como = "página baixada agora"
    else:
        origem = Path(ent["valor"])
        conteudo = origem.read_text(encoding="utf-8", errors="replace")
        if origem.suffix.lower() in (".html", ".htm"):
            titulo, texto = html_para_texto(conteudo)
        else:
            primeira = next((l for l in conteudo.splitlines() if l.strip()), "")
            titulo, texto = primeira.lstrip("# ").strip(), conteudo
        # um .md salvo por nós pode trazer a URL de origem numa linha "Fonte: <url>"
        m = re.search(r"^Fonte:\s*(https?://\S+)", conteudo, re.M)
        fonte = {"url": m.group(1) if m else None, "titulo": titulo[:300], "arquivo_original": str(origem),
                 "buscado_em": db.agora(), "como": "arquivo local copiado (o original não foi alterado)", "extrator": EXTRATOR}
        arq.write_text(texto, encoding="utf-8")
        como = fonte["como"]
    (pasta / "fonte.json").write_text(json.dumps(fonte, ensure_ascii=False, indent=1), encoding="utf-8")
    texto = arq.read_text(encoding="utf-8")
    h = hashlib.sha256(arq.read_bytes()).hexdigest()
    agora = db.agora()
    con.execute(
        "INSERT INTO videos(video_id,perfil,url,titulo,duracao_s,pasta,arquivo_video,sha256,tamanho_bytes,origem,criado_em,"
        "atualizado_em,ultima_execucao) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(video_id) DO UPDATE SET "
        "url=COALESCE(excluded.url,videos.url),titulo=COALESCE(excluded.titulo,videos.titulo),duracao_s=0,"
        "pasta=excluded.pasta,arquivo_video=excluded.arquivo_video,sha256=excluded.sha256,"
        "tamanho_bytes=excluded.tamanho_bytes,atualizado_em=excluded.atualizado_em,ultima_execucao=excluded.ultima_execucao",
        (vid, ent["perfil"], fonte.get("url"), fonte.get("titulo") or None, 0, C.rel(pasta), C.rel(arq), h,
         arq.stat().st_size, "programa:texto", agora, agora, ex.id))
    con.commit()
    n = len(texto)
    st = "ok" if n >= MIN_CARACTERES else "alerta"
    ex.checagem(vid, "baixar", "texto salvo tem conteúdo", f"≥ {MIN_CARACTERES} caracteres", f"{n} caracteres", st,
                "" if st == "ok" else "Texto muito curto: a página pode exigir login ou ter bloqueado o acesso.")
    return st, f"{como} · {n} caracteres · {len(texto.split())} palavras", {
        "arquivo": C.rel(arq), "caracteres": n, "palavras": len(texto.split()), "url": fonte.get("url"), "como": como}


def dividir(texto):
    trechos = []
    for par in re.split(r"\n\s*\n", texto):
        par = re.sub(r"[ \t]+", " ", par).strip()
        if not par:
            continue
        while len(par) > MAX_TRECHO:  # parágrafo longo: corta no fim de frase mais próximo
            corte = max(par.rfind(". ", 0, MAX_TRECHO), par.rfind("? ", 0, MAX_TRECHO), par.rfind("! ", 0, MAX_TRECHO))
            corte = corte + 1 if corte > MAX_TRECHO // 3 else MAX_TRECHO
            trechos.append(par[:corte].strip())
            par = par[corte:].strip()
        if par:
            trechos.append(par)
    return trechos


def etapa_trechos(ex, con, vid, pasta, video, cfg):
    texto = (pasta / "texto.md").read_text(encoding="utf-8")
    trechos = dividir(texto)
    segs = [{"inicio_s": float(i), "fim_s": float(i + 1), "texto": t, "confianca": None} for i, t in enumerate(trechos)]
    (pasta / "transcricao.json").write_text(json.dumps({"info": {"tipo": "texto", "trechos": len(segs)}, "segmentos": segs},
                                                       ensure_ascii=False, indent=1), encoding="utf-8")
    con.execute("DELETE FROM falas WHERE video_id=?", (vid,))
    con.executemany("INSERT INTO falas(video_id,n,inicio_s,fim_s,texto,confianca,origem) VALUES(?,?,?,?,?,?,?)",
                    [(vid, i, s["inicio_s"], s["fim_s"], s["texto"], None, "programa:texto") for i, s in enumerate(segs)])
    con.commit()
    palavras = sum(len(s["texto"].split()) for s in segs)
    m = {"trechos": len(segs), "palavras": palavras, "tipo": "texto"}
    if not segs:
        return "alerta", "texto vazio", m
    return "ok", f"{len(segs)} trechos numerados · {palavras} palavras (fonte de texto)", m


def etapa_sem_imagens(ex, con, vid, pasta, video, cfg):
    from .pipeline import AGRUPAMENTO
    con.execute("DELETE FROM frames WHERE video_id=?", (vid,))
    con.commit()
    return "ok", "fonte de texto: não há imagens", {"texto": True, "unicas_guardadas": 0, "agrupamento": AGRUPAMENTO}


def etapa_integridade(ex, con, vid, pasta, video, cfg):
    piores = []

    def chk(nome, esp, obt, st, expl):
        ex.checagem(vid, "integridade", nome, esp, obt, st, expl)
        piores.append(st)
    arq = pasta / "texto.md"
    n = len(arq.read_text(encoding="utf-8")) if arq.exists() else 0
    chk("texto da fonte salvo no disco", "existe", "existe" if arq.exists() else "não existe",
        "ok" if arq.exists() else "falha", "" if arq.exists() else "texto.md sumiu")
    chk("texto com tamanho mínimo", f"≥ {MIN_CARACTERES}", n, "ok" if n >= MIN_CARACTERES else "alerta",
        "" if n >= MIN_CARACTERES else "Texto curto: confira se a página abriu de verdade (login/bloqueio).")
    try:
        segs = json.loads((pasta / "transcricao.json").read_text(encoding="utf-8"))["segmentos"]
    except (OSError, ValueError, KeyError):
        segs = None
    falas = con.execute("SELECT COUNT(*) FROM falas WHERE video_id=?", (vid,)).fetchone()[0]
    st = "ok" if segs is not None and len(segs) == falas else "falha"
    chk("trechos no banco = trechos do arquivo", len(segs) if segs is not None else None, falas, st,
        "" if st == "ok" else "Dados perdidos ao gravar no banco.")
    status = "falha" if "falha" in piores else ("alerta" if "alerta" in piores else "ok")
    ok = piores.count("ok")
    return status, f"{ok} de {len(piores)} checagens ok", {"checagens": len(piores), "ok": ok,
                                                            "alertas": piores.count("alerta"), "falhas": piores.count("falha")}


INSTR_TEXTO = """
ATENÇÃO: esta fonte é TEXTO (post do Reddit, página de banco/universidade ou guia), não um vídeo.
- Os "trechos" abaixo são parágrafos numerados; "inicio_s"/"fim_s" = número do trecho (ex.: trecho [3.0s–4.0s] → 3.0 e 4.0).
- Não há imagens: use "frames_com_cv": [], "descricoes_imagens": [] e "frame_n": null.
- Em comentários do Reddit, diga em "recomendacao" quando é opinião de um usuário (e quantos votos tinha), não regra oficial.
"""
