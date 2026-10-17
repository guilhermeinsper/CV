"""Caminhos, configuração e chaves. Tudo relativo à pasta do projeto (S:\\CV)."""
import json, os, shutil, sys
from pathlib import Path

BASE = Path(os.environ.get("CV_BASE") or Path(__file__).resolve().parent.parent)
APP = BASE / "app"
DADOS = BASE / "dados"
VIDEOS = DADOS / "videos"
DB_PATH = Path(os.environ["CV_DB"]) if os.environ.get("CV_DB") else DADOS / "cv.db"
LOGS = BASE / "logs"
EVENTOS_JSONL = LOGS / "eventos.jsonl"
RELATORIOS = BASE / "relatorios"
CURRICULOS = BASE / "curriculos"
ARQUIVO = BASE / "arquivo"

PADRAO = {
    "intervalo_frames_s": 1.5,
    "dhash_tamanho": 32,
    "dhash_limiar": 12,
    "modelo_whisper": "small",
    "idioma": "auto",
    "max_imagens_ia": 60,
    "agrupar_tamanho": 16,   # assinatura visual 16x16 para juntar imagens quase iguais
    "agrupar_limiar": 0.15,  # até 15% de diferença = mesma tela (só a pessoa/legenda mudou)
    "agrupar_limiar_max": 0.20,  # só para caber no pacote da IA: representantes com até 20% de diferença
    "lado_maior_imagem_ia": 1568,
    "timeout_download_s": 180,
    "timeout_ia_s": 300,
    "pausa_entre_downloads_s": 4,
    "lacuna_alerta_s": 8,
    "modelos": {
        "claude": ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"],
        "openai": ["gpt-5"],
    },
}


def config():
    c = dict(PADRAO)
    arq = BASE / "config.json"
    if arq.exists():
        try:
            c.update(json.loads(arq.read_text(encoding="utf-8")))
        except Exception as e:  # config quebrado não derruba o programa
            print(f"[config] config.json inválido, usando padrão: {e}", file=sys.stderr)
    return c


def chaves():
    """Lê S:\\CV\\.env (linhas CHAVE=valor). Nunca imprime os valores."""
    d = {}
    arq = BASE / ".env"
    if arq.exists():
        for linha in arq.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                d[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        if os.environ.get(k):
            d.setdefault(k, os.environ[k])
    return d


def ffmpeg(nome="ffmpeg"):
    """Acha o ffmpeg/ffprobe sem depender de quem abriu o painel (PATH diferente quebrou o lote das 20h01).
    Ordem: variável CV_FFMPEG_DIR → config.json "ffmpeg_dir" → PATH → atalhos do winget → pasta do pacote winget."""
    exe = nome + (".exe" if os.name == "nt" else "")
    dirs = [os.environ.get("CV_FFMPEG_DIR"), config().get("ffmpeg_dir")]
    for d in dirs:
        if d and (Path(d) / exe).exists():
            return str(Path(d) / exe)
    achado = shutil.which(nome)
    if achado:
        return achado
    home = os.environ.get("LOCALAPPDATA") or (os.environ.get("USERPROFILE") and str(Path(os.environ["USERPROFILE"]) / "AppData" / "Local"))
    if home:
        cand = Path(home) / "Microsoft" / "WinGet" / "Links" / exe
        if cand.exists():
            return str(cand)
        for cand in sorted((Path(home) / "Microsoft" / "WinGet" / "Packages").glob(f"Gyan.FFmpeg*/**/bin/{exe}")):
            return str(cand)
    return None


def fixar_ffmpeg():
    """Grava no config.json a pasta onde o ffmpeg foi achado, para todas as execuções futuras usarem a mesma."""
    achado = ffmpeg("ffmpeg")
    if not achado:
        return None
    pasta = str(Path(achado).parent)
    arq = BASE / "config.json"
    try:
        c = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
        if c.get("ffmpeg_dir") != pasta:
            c["ffmpeg_dir"] = pasta
            arq.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return pasta


def rel(p):
    """Caminho relativo à pasta do projeto, com barras normais (portável)."""
    try:
        return Path(p).resolve().relative_to(BASE.resolve()).as_posix()
    except Exception:
        return str(p)


def abs_(r):
    return BASE / r


def garantir_pastas():
    for p in (DADOS, VIDEOS, LOGS, RELATORIOS, CURRICULOS, ARQUIVO):
        p.mkdir(parents=True, exist_ok=True)


def utf8_stdout():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
