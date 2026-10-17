"""Fila persistente sem duplicação; cancelamentos ficam arquivados e reversíveis."""
import json,threading,uuid
from pathlib import Path
from . import config as C,db,estado

LOCK=threading.RLock()
def ler():
    path=C.DADOS/'fila_espera.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
def gravar(rows):
    path=C.DADOS/'fila_espera.json';tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)
def historico(item,motivo):
    path=C.DADOS/'fila_historico.jsonl'
    with path.open('a',encoding='utf-8') as f:f.write(json.dumps({'ts':db.agora(),'estado':'arquivado','motivo':motivo,'lote':item},ensure_ascii=False)+'\n')
def chaves_ativas():
    c=db.conectar()
    try:
        entries=[]
        for e in db.linhas(c,"SELECT * FROM execucoes WHERE status='rodando' AND disparada_por IN ('painel','terminal')"):
            if estado.pulso_recente(e):entries+=json.loads(e['parametros'] or '{}').get('entradas',[])
        return {estado.identidade(x) for x in entries}
    finally:c.close()
def normalizar():
    with LOCK:
        covered=chaves_ativas();out=[]
        for item in ler():
            original=dict(item);links=[];files=[]
            for source,dest in [(item.get('links',[]),links),(item.get('arquivos',[]),files)]:
                for value in source:
                    key=estado.identidade(value)
                    if key not in covered:dest.append(value);covered.add(key)
            if len(links)+len(files)<len(item.get('links',[]))+len(item.get('arquivos',[])):
                historico(original,'Entradas repetidas já estão no lote ativo ou em outra posição da fila.')
            if links or files:out.append({**item,'id':item.get('id') or uuid.uuid4().hex[:12],'links':links,'arquivos':files})
        gravar(out);return out
def adicionar(links,arquivos):
    with LOCK:
        items=normalizar();covered=chaves_ativas()|{estado.identidade(x) for i in items for x in i.get('links',[])+i.get('arquivos',[])}
        pending_links=[];pending_files=[];duplicates=0
        for source,dest in [(links,pending_links),(arquivos,pending_files)]:
            for x in source:
                key=estado.identidade(x)
                if key in covered:duplicates+=1
                else:dest.append(x);covered.add(key)
        if pending_links or pending_files:
            items.append({'id':uuid.uuid4().hex[:12],'links':pending_links,'arquivos':pending_files,'pedido_em':db.agora()});gravar(items)
        return {'ok':True,'na_espera':bool(pending_links or pending_files),'ja_agendado':not(pending_links or pending_files),
            'duplicados':duplicates,'videos':len(pending_links)+len(pending_files),'lotes_na_espera':len(items)}
def controlar(body):
    with LOCK:
        rows=ler();action=body.get('acao')
        if action=='cancelar':
            removed=[r for r in rows if r.get('id')==body.get('id')]
            for row in removed:historico(row,'Cancelado pelo controle da fila; conteúdo preservado neste histórico.')
            gravar([r for r in rows if r not in removed]);return {'ok':True,'cancelados':len(removed)}
        if action=='normalizar':return {'ok':True,'fila':normalizar()}
        if action in ['pausar','retomar']:
            (C.DADOS/'fila_controle.json').write_text(json.dumps({'pausada':action=='pausar','ts':db.agora()}),encoding='utf-8');return {'ok':True}
        return {'erro':'Ação da fila desconhecida.'}
def pausada():
    path=C.DADOS/'fila_controle.json'
    return json.loads(path.read_text(encoding='utf-8')).get('pausada',False) if path.exists() else False
