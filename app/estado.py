"""Projeção única do estado real. Não grava status nem altera o histórico."""
import json,re,hashlib
from datetime import datetime,timezone
from pathlib import Path
from . import config as C,db

TECNICAS=['baixar','transcrever','imagens','integridade','relatorio']
BOAS=('ok','alerta')

def identidade(valor):
    y=re.search(r'(?:v=|youtu\.be/|/shorts/)([\w-]{11})',str(valor))
    if y:return 'yt:'+y.group(1)
    m=re.search(r'/video/(\d+)',str(valor))
    return 'video:'+m.group(1) if m else str(valor).split('?')[0].rstrip('/').lower()

def pacote_valido(c,vid):
    v=c.execute('SELECT pasta FROM videos WHERE video_id=?',(vid,)).fetchone()
    if not v:return False,'Vídeo ausente no banco.'
    stages={r['etapa']:r['status'] for r in c.execute('SELECT etapa,status FROM etapas WHERE video_id=?',(vid,))}
    if any(stages.get(e) not in BOAS for e in ['transcrever','imagens','integridade']):return False,'Transcrição, imagens ou integridade ainda não aprovadas pelo programa.'
    folder=C.BASE/v['pasta'];request=folder/'ia/pedido_chat.json';transcript=folder/'transcricao.json'
    try:
        p=json.loads(request.read_text(encoding='utf-8'));t=json.loads(transcript.read_text(encoding='utf-8'))
        if p.get('sha256_transcricao') and hashlib.sha256(transcript.read_bytes()).hexdigest()!=p['sha256_transcricao']:return False,'Hash da transcrição mudou desde a preparação do pacote.'
        falas=db.linhas(c,'SELECT inicio_s,fim_s,texto FROM falas WHERE video_id=? ORDER BY n',(vid,))
        texto='\n'.join(f"[{f['inicio_s']:.1f}s–{f['fim_s']:.1f}s] {f['texto']}" for f in falas) or '(nenhuma fala detectada)'
        if p.get('trechos')!=len(falas) or len(t['segmentos'])!=len(falas) or p.get('transcricao_enviada')!=texto:return False,'Pacote antigo ou transcrição divergente.'
        if [(s['inicio_s'],s['fim_s'],s['texto']) for s in t['segmentos']]!=[(s['inicio_s'],s['fim_s'],s['texto']) for s in falas]:return False,'Arquivo da transcrição difere do banco.'
        images=p.get('imagens_enviadas',[])
        if not images and not str(vid).startswith('tx_'):return False,'Pacote sem imagens.'
        known={r['n']:r['arquivo'] for r in c.execute('SELECT n,arquivo FROM frames WHERE video_id=? AND unico=1',(vid,))}
        if any(known.get(i['n'])!=i['arquivo'] for i in images):return False,'Imagem do pacote não coincide com os frames registrados.'
        if any(not (C.BASE/i['arquivo']).is_file() for i in images):return False,'Imagem do pacote ausente.'
        return True,None
    except (OSError,ValueError,KeyError,TypeError):return False,'Pacote ou transcrição ausente/inválido.'

_CACHE_PEND = {}


def assinatura(c):
    """Muda sempre que o programa grava algo (evento, etapa, falas, frames)."""
    return tuple(c.execute("SELECT (SELECT MAX(id) FROM eventos),(SELECT COUNT(*) FROM etapas),(SELECT MAX(fim) FROM etapas),"
                           "(SELECT COUNT(*) FROM falas),(SELECT COUNT(*) FROM frames),(SELECT COUNT(*) FROM videos)").fetchone())


def pendentes(c):
    sig = assinatura(c)
    if _CACHE_PEND.get("sig") == sig:
        return _CACHE_PEND["valor"]
    valor = _pendentes_sem_cache(c)
    _CACHE_PEND.update(sig=sig, valor=valor)
    return valor


def _pendentes_sem_cache(c):
    validos=[];invalidos=[]
    for r in db.linhas(c,"SELECT e.video_id,v.pasta,v.titulo FROM etapas e JOIN videos v USING(video_id) WHERE e.etapa='interpretar' AND e.status='aguardando_ia' ORDER BY e.inicio"):
        ok,reason=pacote_valido(c,r['video_id'])
        (validos if ok else invalidos).append({**r,'motivo':reason})
    return validos,invalidos

def pulso_recente(e):
    try:
        if e.get('status')!='rodando':return False
        return (datetime.now(timezone.utc)-datetime.fromisoformat(e['pulso'])).total_seconds()<25
    except (ValueError,KeyError,TypeError):return False

def situacao(stages):
    s={r['etapa']:r['status'] for r in stages}
    if not s:return 'sem dados'
    for code,label in [('sem_sinal','sem sinal'),('rodando','rodando'),('falha','falha'),('interrompida','falha'),('bloqueada','incompleto'),('aguardando_ia','aguardando IA'),('alerta','alerta'),('pulada','incompleto')]:
        if code in s.values():return label
    return 'ok' if len(s)==6 else 'incompleto'

def etapas_efetivas(c,vid,validos=None):
    rows=db.linhas(c,'SELECT * FROM etapas WHERE video_id=?',(vid,))
    for row in rows:
        if row['status']=='rodando':
            ex=c.execute('SELECT * FROM execucoes WHERE id=?',(row['execucao_id'],)).fetchone()
            if ex and not pulso_recente(dict(ex)):row.update(status_registrado='rodando',status='sem_sinal')
        if row['etapa']=='interpretar' and row['status']=='aguardando_ia':
            ok=vid in validos if validos is not None else pacote_valido(c,vid)[0]
            if not ok:row.update(status_registrado=row['status'],status='bloqueada',mensagem='Pacote antigo bloqueado: aguarde a preparação técnica válida.')
    return rows
