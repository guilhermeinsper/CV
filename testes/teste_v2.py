"""Teste v2: 2 vídeos sintéticos, transcrição simulada (LENTO s por trecho), IA pelo chat (pacote)."""
import os, subprocess, sys, time
from pathlib import Path
base = Path(os.environ["CV_BASE"]); base.mkdir(parents=True, exist_ok=True)
vids = []
for i, (txt, d) in enumerate([("EDUCACAO - INSPER", 12), ("EXPERIENCIA - ITAU BBA", 9)]):
    v = base / f"cv_teste_{i+1}.mp4"
    if not v.exists():
        subprocess.run(["ffmpeg","-loglevel","error","-y","-f","lavfi","-i",f"color=c=white:s=540x960:d={d}","-f","lavfi","-i",f"sine=f=300:d={d}",
          "-vf",f"drawtext=text='{txt}':fontsize=34:x=40:y=200:enable='lt(t,4)',drawtext=text='HABILIDADES - EXCEL':fontsize=34:x=40:y=640:enable='gte(t,4)'",
          "-shortest","-c:v","libx264","-c:a","aac",str(v)], check=True)
    vids.append(str(v))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import pipeline
LENTO = float(os.environ.get("LENTO", "0"))
def falsa(caminho, cfg, prog):
    out = []
    for a, b, t in [(0.3,3.5,"Coloque a formação no topo do currículo."),(4.2,7.6,"Quantifique cada bullet com números.")]:
        time.sleep(LENTO); out.append({"inicio_s":a,"fim_s":b,"texto":t,"confianca":-0.3}); prog(out[-1], 9.0)
    return out, {"idioma":"pt","prob_idioma":0.99,"duracao_audio_s":9.0,"duracao_com_fala_s":7.0}
pipeline.transcrever_arquivo = falsa
sys.exit(pipeline.main(["--ia", "chat", "--limite", "0", "--disparada-por", "painel"] + sum([["--arquivo", v] for v in vids], []) + sys.argv[1:]))
