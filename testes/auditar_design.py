"""Fotografia somente de leitura do painel; não executa vídeos nem escreve estados."""
import hashlib
import json
import sqlite3
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


def main():
    def api(nome):
        with urllib.request.urlopen('http://127.0.0.1:8770/api/'+nome, timeout=30) as r:
            return json.load(r)
    painel=api('painel')
    anterior=json.loads((BASE/'relatorios/auditoria_correcao_painel.json').read_text(encoding='utf-8'))
    c=sqlite3.connect((BASE/'dados/cv.db').as_uri()+'?mode=ro', uri=True)
    try:
        novas=c.execute('SELECT id FROM execucoes WHERE julianday(inicio)>julianday(?)',(anterior['ts'],)).fetchall()
        contagens={t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('videos','execucoes','falas','frames','eventos')}
    finally:
        c.close()
    arquivos=['app/resumo.py','app/servidor.py','app/web/app.js','app/web/style.css','app/web/index.html',
              'testes/test_resumo.py','testes/test_estado_painel.py','logs/testes_design_v320.txt']
    resultado={'data':datetime.now().astimezone().isoformat(), 'versao':painel['versao'],
        'escopo':'Design e contagens; nenhum novo teste real de vídeo',
        'sem_nova_execucao_desde_auditoria_anterior':not novas,
        'novas_execucoes':[r[0] for r in novas], 'contagens':contagens,
        'estado':{'vivo':painel['vivo'],'fila':painel['espera'],'fila_pausada':painel['fila_pausada'],
                  'prontos_ia':painel['aguardando_ia'],'pacotes_invalidos':painel['pacotes_invalidos'],
                  'execucao':painel['execucao']['id'] if painel['execucao'] else None},
        'resumo_hoje':api('resumo?periodo=hoje'), 'falhas':api('falhas')['resumo_atual'],
        'testes_automatizados':{'aprovados':18,'registro':'logs/testes_design_v320.txt'},
        'qa_navegador_observado':{'abas_sem_erro_js_observado':5,'filtros_dia_mes':True,
            'detalhes_abertos_e_rascunho_preservados':True,'fila_zero_oculta':True,
            'barra_oculta_ao_encerrar':True,'larguras_conferidas':[1440,390],
            'interface_ativa_simulada':True,'upload_e_duplo_clique_interceptados':True,
            'postagens_reais_de_video_nestes_testes':0},
        'nao_testado':['Novo vídeo real de ponta a ponta nesta etapa','Precisão semântica da transcrição',
                       'Nova interpretação real de IA','Novas redes de origem'],
        'tokens_conversa':None,'custo_conversa':None,
        'hashes_codigo_e_testes':{n:hashlib.sha256((BASE/n).read_bytes()).hexdigest() for n in arquivos}}
    (BASE/'relatorios/design_v320.json').write_text(json.dumps(resultado,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:resultado[k] for k in ('versao','sem_nova_execucao_desde_auditoria_anterior','estado','contagens')},ensure_ascii=False))


if __name__=='__main__':main()
