"""Teste: vídeo sintético + transcrição e IA simuladas (só para teste; NUNCA usado em produção)."""
import json, os, subprocess, sys, time, tempfile
from pathlib import Path
base = Path(os.environ["CV_BASE"]); base.mkdir(parents=True, exist_ok=True)
(base / ".env").write_text("ANTHROPIC_API_KEY=chave-falsa-de-teste\n")
video = base / "entrada_teste.mp4"
if not video.exists():
    subprocess.run(["ffmpeg","-loglevel","error","-y","-f","lavfi","-i","color=c=white:s=540x960:d=12","-f","lavfi","-i","sine=f=300:d=12",
      "-vf","drawtext=text='EDUCACAO - INSPER':fontsize=34:x=40:y=200:enable='lt(t,4)',drawtext=text='EXPERIENCIA - ITAU BBA':fontsize=34:x=40:y=420:enable='between(t,4,8)',drawtext=text='HABILIDADES - EXCEL':fontsize=34:x=40:y=640:enable='gte(t,8)'",
      "-shortest","-c:v","libx264","-c:a","aac",str(video)], check=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import pipeline, ia
LENTO = float(os.environ.get("LENTO", "0"))
def falsa_transcricao(caminho, cfg, prog):
    segs = [(0.3,3.5,"Coloque a formação no topo do currículo."),(4.2,7.6,"Quantifique cada bullet com números."),(8.4,11.6,"Excel avançado sem prova não convence.")]
    out=[]
    for a,b,t in segs:
        time.sleep(LENTO); out.append({"inicio_s":a,"fim_s":b,"texto":t,"confianca":-0.3}); prog(out[-1], 12.0)
    return out, {"idioma":"pt","prob_idioma":0.99,"duracao_audio_s":12.0,"duracao_com_fala_s":10.0}
def falsa_ia(provedor, modelo, texto, imagens, chave, cfg):
    time.sleep(LENTO)
    ns=[n for n,_,_ in imagens]
    resp={"resumo":"Vídeo de teste.","frames_com_cv":ns[:2],
      "cv_exemplos":[{"frame_n":ns[0],"secao":"Educação","texto_lido":"EDUCACAO - INSPER","legibilidade":"legivel"},
                     {"frame_n":999,"secao":"Outro","texto_lido":"x","legibilidade":"ilegivel"}],
      "recomendacoes":[{"inicio_s":0.3,"fim_s":3.5,"categoria":"estrutura","tipo":"fazer","recomendacao":"Formação no topo.","citacao":"Coloque a formação no topo do currículo","aplica_a":"geral","frame_n":ns[0],"confianca":"alta"},
                       {"inicio_s":4.2,"fim_s":7.6,"categoria":"bullets","tipo":"fazer","recomendacao":"Quantificar bullets.","citacao":"quantifique cada bullet com números","aplica_a":"geral","frame_n":None,"confianca":"alta"},
                       {"inicio_s":8.4,"fim_s":11.6,"categoria":"habilidades","tipo":"evitar","recomendacao":"(INVENTADA) Nunca use Excel.","citacao":"nunca coloque Excel no currículo","aplica_a":"geral","frame_n":None,"confianca":"media"}],
      "trechos_duvidosos":[]}
    return json.dumps(resp), {"entrada":1234,"saida":321,"duracao_s":0.1}, {"teste":True,"imagens_enviadas":[{"n":n} for n in ns]}, {"bruto":"simulado"}
pipeline.transcrever_arquivo = falsa_transcricao
ia.chamar = falsa_ia
sys.exit(pipeline.main(["--arquivo", str(video), "--ia", "claude"] + sys.argv[1:]))
