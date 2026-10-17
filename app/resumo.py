"""Contagens de atividade por data local; somente leitura, sem promover estados."""
from datetime import datetime, timezone, timedelta

FUSO = timezone(timedelta(hours=-3))  # Datas do painel em São Paulo.


def data_local(valor):
    try:
        dt = datetime.fromisoformat(valor.replace('Z', '+00:00'))
        return dt.replace(tzinfo=FUSO).date() if dt.tzinfo is None else dt.astimezone(FUSO).date()
    except (ValueError, TypeError, AttributeError):
        return None


def resumir(c, periodo='hoje', data=None):
    hoje = datetime.now(FUSO).date()
    if periodo not in ('hoje', 'mes', 'data', 'tudo'):
        raise ValueError('Período inválido')
    alvo = hoje
    if data and periodo in ('data', 'mes'):
        try:
            alvo = datetime.strptime(data, '%Y-%m-%d').date()
        except ValueError:
            raise ValueError('Data inválida; use ano-mês-dia') from None
    def dentro(valor):
        dia = data_local(valor)
        return dia is not None and (periodo == 'tudo' or
            ((dia.year, dia.month) == (alvo.year, alvo.month) if periodo == 'mes' else dia == alvo))
    novos = {r['video_id'] for r in c.execute('SELECT video_id,criado_em FROM videos') if dentro(r['criado_em'])}
    etapas = {n: set() for n in ('baixar', 'transcrever', 'imagens', 'integridade', 'interpretar', 'relatorio')}
    # Eventos preservam conclusões anteriores mesmo após reprocessar. Repetir um vídeo
    # não aumenta a contagem da mesma etapa dentro do período selecionado.
    for r in c.execute("SELECT video_id,etapa,ts FROM eventos WHERE tipo='fim' AND status IN ('ok','alerta') AND video_id IS NOT NULL"):
        if r['etapa'] in etapas and dentro(r['ts']):
            etapas[r['etapa']].add(r['video_id'])
    return {'periodo': periodo, 'data': alvo.isoformat(), 'novos': len(novos),
            'etapas': {k: len(v) for k, v in etapas.items()},
            'videos_com_atividade': len(set().union(*etapas.values())),
            'total_biblioteca': c.execute('SELECT COUNT(*) FROM videos').fetchone()[0],
            'criterio': 'Vídeos distintos com conclusão registrada no período, incluindo alertas. Reprocessamentos não duplicam a mesma etapa. Não representa o estado atual nem validação humana.'}
