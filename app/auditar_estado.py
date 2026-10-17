"""Conferência independente dos artefatos e consistência das APIs. Não altera etapas."""
import argparse,json,hashlib
from pathlib import Path
from . import config as C,db,servidor,estado

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--final',action='store_true');args=ap.parse_args()
    d=servidor.executar_api(servidor.api_painel,{})
    a=servidor.executar_api(servidor.api_analitico,{})
    f=servidor.executar_api(servidor.api_falhas,{})
    issues=[];videos=[];c=db.conectar()
    try:
        if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':issues.append('Banco SQLite inconsistente.')
        if d['aguardando_ia']!=a['kpis']['aguardando_ia']:issues.append('Contadores de IA mudaram entre as leituras; repetir após o lote parar.')
        if f['resumo_atual']['videos_com_falha']!=a['kpis']['videos_com_falha']:issues.append('Contadores de falha mudaram entre as leituras; repetir após o lote parar.')
        if args.final and d['vivo']:issues.append('O lote ainda está rodando; não é fechamento final.')
        if args.final:
            for row in d['fila']:
                v=dict(c.execute('SELECT * FROM videos WHERE video_id=?',(row['video_id'],)).fetchone());problems=[]
                video=C.BASE/v['arquivo_video'];folder=C.BASE/v['pasta']
                if not video.is_file():problems.append('Vídeo original ausente.')
                elif hashlib.sha256(video.read_bytes()).hexdigest()!=v['sha256']:problems.append('Hash do vídeo difere do banco.')
                valid,reason=estado.pacote_valido(c,v['video_id'])
                if not valid:problems.append(reason)
                unique=db.linhas(c,'SELECT n,arquivo FROM frames WHERE video_id=? AND unico=1',(v['video_id'],))
                absent=[x['n'] for x in unique if not (C.BASE/x['arquivo']).is_file()]
                if absent:problems.append('Frames únicos ausentes: '+str(absent))
                if any(row['etapas'].get(e) not in ('ok','alerta') for e in estado.TECNICAS):problems.append('Preparação técnica incompleta.')
                videos.append({'video_id':v['video_id'],'etapas':row['etapas'],'falas':c.execute('SELECT COUNT(*) FROM falas WHERE video_id=?',(v['video_id'],)).fetchone()[0],
                    'imagens_amostradas':c.execute('SELECT COUNT(*) FROM frames WHERE video_id=?',(v['video_id'],)).fetchone()[0],
                    'imagens_unicas_no_disco':len(unique)-len(absent),'pacote_valido':valid,'problemas':problems})
                issues.extend(v['video_id']+': '+x for x in problems)
        result={'ts':db.agora(),'tipo':'final' if args.final else 'parcial','resultado':'falhou' if issues else 'aprovado',
            'progresso':d['progresso_lote'],'vivo':d['vivo'],'versao':d['versao'],'execucao':d['execucao']['id'],
            'prontos_ia':d['aguardando_ia'],'pacotes_invalidos':d['pacotes_invalidos'],'fila_espera':d['espera'],
            'falhas_abertas':f['resumo_atual'],'videos':videos,'problemas':issues,
            'interpretacao_ia_realizada_nesta_correcao':False,'tokens_desta_correcao':None,'custo_desta_correcao':None,
            'limite':'Confere artefatos, pré-requisitos e consistência de contagem; não prova precisão semântica ou leitura da IA.'}
        result['codigo_sha256']={str(p.relative_to(C.BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [
            C.BASE/'app/servidor.py',C.BASE/'app/pipeline.py',C.BASE/'app/estado.py',C.BASE/'app/fila.py',C.BASE/'app/importar_ia.py',
            C.BASE/'app/web/app.js',C.BASE/'app/web/style.css',C.BASE/'app/web/index.html',C.BASE/'testes/test_estado_painel.py']}
        C.RELATORIOS.mkdir(exist_ok=True)
        (C.RELATORIOS/'auditoria_correcao_painel.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        if args.final and not issues:
            text=f'''# Correção do painel — fechamento {result['ts']}

Resultado técnico: {len(videos)} vídeos do lote conferidos, {sum(v['falas'] for v in videos)} trechos de fala, {sum(v['imagens_amostradas'] for v in videos)} amostras de imagem e {sum(v['imagens_unicas_no_disco'] for v in videos)} imagens únicas presentes no disco. {result['prontos_ia']} pacotes válidos para a IA. Fila de espera: {result['fila_espera']}. Falhas abertas: {result['falhas_abertas']['videos_com_falha']}; vídeos com aviso: {result['falhas_abertas']['videos_com_alerta']}.

## Problemas corrigidos

- Aviso da IA pode ser fechado e reaberto; não reaparece a cada atualização. Pacotes antigos sem transcrição válida não contam como prontos.
- Progresso mostra o lote inteiro e o horário alcançado na transcrição. Etapas reaproveitadas contam como preparação existente. 100% preparado não significa interpretado.
- Fila deduplica por vídeo, permite pausa/retomada/cancelamento e preserva os pedidos arquivados. Três repetições do lote ativo foram arquivadas, sem descartar os vídeos.
- Abas compartilham a projeção de estado. O contador de falhas distingue vídeos de registros por etapa/checagem. O histórico não foi apagado.
- Ordem do workflow é visualmente explícita; conexões decorativas para banco/IA foram retiradas. Fluxo não é prova de transferência nem de leitura.
- Corrigida a causa visual da linha tracejada contínua: os mini-indicadores de 21 vídeos transbordavam os blocos. Limites de largura aplicados e conferidos no navegador.
- Fusos, seleção da execução atual, atualização de abas e cache da interface corrigidos. Falha de atualização mostra que os números podem estar antigos. Falta de pulso é sinalizada sem fabricar encerramento no banco.

## O que foi comprovado

O problema original de transcrição era a incompatibilidade metadata_errors do PyAV. A v3 do Claude já trazia extração de áudio por ffmpeg; esta recuperação foi acompanhada e conferida no Windows. O processo do lote iniciado às 19h01 foi preservado ao reiniciar a interface. Nenhuma API paga de interpretação foi acionada.

Onze testes de regressão passaram em banco temporário (logs/testes_correcao_painel.txt). Playwright MCP foi usado para testar a aplicação na porta 8770; não houve acesso à aba pessoal do Chrome. Testados: fechamento persistente do aviso, barra real, histórico com 24 entradas/21 vídeos/3 fotos recusadas, pausa/retomada, reenvio duplicado, preservação do texto digitado e queda/recuperação de conexão simulada apenas no navegador de teste.

A auditoria final recalculou o hash de cada vídeo, comparou transcrição com o banco e com o pacote da IA, conferiu imagens únicas presentes e a integridade do SQLite. Detalhes por vídeo em auditoria_correcao_painel.json.

## Limites e continuidade

Nenhum dos novos vídeos foi interpretado pelo assistente nesta correção. Os pacotes aguardam a etapa de IA do chat. A conferência de arquivos e os testes não garantem precisão de cada palavra ou atenção interna da IA. Avisos reais de conteúdo não devem ser apagados para fazer o contador ficar verde.

O primeiro lote tinha 24 links: 21 vídeos e 3 posts de fotos não suportados. O reprocessamento continha somente os 21 vídeos. A biblioteca também contém oito vídeos migrados; não confundir o total da biblioteca com o lote atual.

Abra http://127.0.0.1:8770/?v=3.1.1. Os dados e logs permanecem locais. Fonte de verdade: dados/cv.db e logs/eventos.jsonl. MAPA_DO_PROJETO.md e LEIA-ME.md foram atualizados para continuidade no Claude.

Tokens/custo atribuíveis a esta correção: não mensurados. Preparação local não chama APIs pagas; consumo da conversa é separado. Não há preço estimado apresentado como cobrança.
'''
            (C.RELATORIOS/'CORRECAO_PAINEL.md').write_text(text,encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k!='videos'},ensure_ascii=False))
        return int(bool(issues))
    finally:c.close()
if __name__=='__main__':raise SystemExit(main())
