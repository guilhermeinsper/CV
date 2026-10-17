"""Simula a IA do chat respondendo aos pacotes pendentes (citação inventada + 1 imagem sem descrição, de propósito)."""
import json, os, sys
from pathlib import Path
base = Path(os.environ["CV_BASE"])
for ped in base.glob("dados/videos/*/*/ia/pedido_chat.json"):
    if (ped.parent / "resposta_chat.json").exists(): continue
    p = json.loads(ped.read_text(encoding="utf-8")); ns = [i["n"] for i in p["imagens_enviadas"]]
    r = {"modelo_declarado": "Claude (app) — SIMULAÇÃO DE TESTE", "resumo": "teste", "frames_com_cv": ns[:1],
         "cv_exemplos": [{"frame_n": ns[0], "secao": "Educação", "texto_lido": "EDUCACAO - INSPER", "legibilidade": "legivel"}],
         "recomendacoes": [{"inicio_s":0.3,"fim_s":3.5,"categoria":"estrutura","tipo":"fazer","recomendacao":"Formação no topo.","citacao":"Coloque a formação no topo do currículo","aplica_a":"geral","frame_n":ns[0],"confianca":"alta"},
                           {"inicio_s":4.2,"fim_s":7.6,"categoria":"bullets","tipo":"fazer","recomendacao":"(INVENTADA)","citacao":"use sempre fonte Comic Sans","aplica_a":"geral","frame_n":None,"confianca":"baixa"}],
         "trechos_duvidosos": [], "descricoes_imagens": [{"n": n, "descricao": "tela branca com texto"} for n in ns[:-1]]}
    (ped.parent / "resposta_chat.json").write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    print("resposta gravada:", ped.parent)
