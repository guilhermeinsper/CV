"""Regressões do estado/fila com banco temporário; não alteram o material real."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from app import config as C,db,estado,servidor,fila

class EstadoTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.patches=[]
        for key,val in {'BASE':self.base,'DADOS':self.base/'dados','VIDEOS':self.base/'dados/videos','DB_PATH':self.base/'dados/cv.db','LOGS':self.base/'logs','EVENTOS_JSONL':self.base/'logs/eventos.jsonl'}.items():
            p=patch.object(C,key,val);p.start();self.patches.append(p)
        C.DADOS.mkdir();C.VIDEOS.mkdir();C.LOGS.mkdir()
        self.c=db.conectar();self.urls=[f'https://www.tiktok.com/@p/video/{i+100}' for i in range(21)]
        self.c.execute('INSERT INTO execucoes(id,inicio,status,pulso,parametros,total_entradas,disparada_por) VALUES(?,?,?,?,?,?,?)',('ativa',db.agora(),'rodando',db.agora(),db.j({'entradas':self.urls}),21,'painel'))
        for i in range(21):
            vid=str(100+i);folder=C.VIDEOS/vid;folder.mkdir()
            self.c.execute('INSERT INTO videos(video_id,pasta,url,titulo) VALUES(?,?,?,?)',(vid,C.rel(folder),self.urls[i],f'Vídeo {i+1}'))
        self.c.execute('INSERT INTO etapas(video_id,etapa,status,execucao_id) VALUES(?,?,?,?)',('100','baixar','ok','ativa'))
        self.c.execute('INSERT INTO eventos(execucao_id,video_id,status,tipo) VALUES(?,?,?,?)',('ativa','100','video_inicio','info'));self.c.commit()
    def tearDown(self):
        self.c.close()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def painel(self):return servidor.executar_api(servidor.api_painel,{})
    def pacote(self,text='Fala original'):
        folder=C.VIDEOS/'100';(folder/'ia').mkdir(exist_ok=True)
        segment={'inicio_s':0.0,'fim_s':2.0,'texto':text}
        (folder/'transcricao.json').write_text(json.dumps({'segmentos':[segment]}),encoding='utf-8')
        (folder/'frame.jpg').write_bytes(b'fake-test-only')
        self.c.execute('INSERT INTO frames(video_id,n,arquivo,unico) VALUES(?,?,?,1)',('100',0,C.rel(folder/'frame.jpg')))
        pedido={'trechos':1,'transcricao_enviada':f'[0.0s–2.0s] {text}','imagens_enviadas':[{'n':0,'arquivo':C.rel(folder/'frame.jpg')} ]}
        (folder/'ia/pedido_chat.json').write_text(json.dumps(pedido),encoding='utf-8')
        self.c.execute('INSERT INTO falas(video_id,n,inicio_s,fim_s,texto) VALUES(?,?,?,?,?)',('100',0,0,2,text))
        for name in ['transcrever','imagens','integridade','interpretar']:
            self.c.execute('INSERT OR REPLACE INTO etapas(video_id,etapa,status,execucao_id) VALUES(?,?,?,?)',('100',name,'aguardando_ia' if name=='interpretar' else 'ok','ativa'))
        self.c.commit();return folder
    def test_total_includes_unstarted_videos(self):
        d=self.painel();self.assertEqual(len(d['fila']),21);self.assertEqual(d['progresso_lote']['aceitos'],21);self.assertEqual(d['progresso_lote']['a_iniciar'],20)
    def test_downloads_and_rejections_have_separate_denominators(self):
        entradas=self.urls+[f'https://www.tiktok.com/@p/photo/{i}' for i in range(3)]
        self.c.execute('UPDATE execucoes SET total_entradas=24,parametros=?',(db.j({'entradas':entradas}),))
        for i in range(3):self.c.execute('INSERT INTO eventos(execucao_id,tipo,mensagem) VALUES(?,?,?)',('ativa','erro',f'Entrada {i+22} ignorada: foto'))
        self.c.commit();d=self.painel();self.assertEqual(d['progresso_lote']['enviados'],24);self.assertEqual(d['progresso_lote']['aceitos'],21);self.assertEqual(len(d['recusadas']),3)
    def test_invalid_pending_not_counted(self):
        self.c.execute("INSERT INTO etapas(video_id,etapa,status) VALUES('100','interpretar','aguardando_ia')");self.c.commit()
        d=self.painel();self.assertEqual(d['aguardando_ia'],0);self.assertEqual(d['pacotes_invalidos'],1);self.assertEqual(d['fila'][0]['etapas']['interpretar'],'bloqueada')
    def test_pending_matches_full_transcript_not_only_count(self):
        folder=self.pacote();self.assertTrue(estado.pacote_valido(self.c,'100')[0])
        self.c.execute("UPDATE falas SET texto='Fala diferente'");self.c.commit();self.assertFalse(estado.pacote_valido(self.c,'100')[0])
    def test_missing_package_image_blocks_pending(self):
        folder=self.pacote();(folder/'frame.jpg').unlink();self.assertFalse(estado.pacote_valido(self.c,'100')[0])
    def test_three_duplicate_queued_batches_archived(self):
        fila.gravar([{'links':self.urls,'arquivos':[],'pedido_em':db.agora()} for _ in range(3)])
        self.assertEqual(fila.normalizar(),[]);self.assertEqual(len((C.DADOS/'fila_historico.jsonl').read_text().splitlines()),3)
    def test_duplicate_click_does_not_enqueue_again(self):
        d=fila.adicionar(self.urls,[]);self.assertTrue(d['ja_agendado']);self.assertEqual(fila.ler(),[])
    def test_canonical_video_ignores_query_and_profile_variants(self):
        self.assertEqual(estado.identidade(self.urls[0]+'?q=abc'),estado.identidade('https://www.tiktok.com/@outro/video/100'))
    def test_cancel_preserves_payload_and_pause_persists(self):
        fila.adicionar(['https://www.tiktok.com/@p/video/999'],[]);row=fila.ler()[0]
        self.assertEqual(fila.controlar({'acao':'cancelar','id':row['id']})['cancelados'],1)
        self.assertIn('999',(C.DADOS/'fila_historico.jsonl').read_text());fila.controlar({'acao':'pausar'});self.assertTrue(fila.pausada())
    def test_get_does_not_write_orphan_status(self):
        self.c.execute("UPDATE execucoes SET pulso='2000-01-01T00:00:00+00:00'");self.c.commit()
        d=self.painel();self.assertFalse(d['vivo']);self.assertEqual(d['execucao']['status'],'sem_sinal');self.assertEqual(self.c.execute('SELECT status FROM execucoes').fetchone()[0],'rodando')
    def test_analytical_and_workflow_use_same_ready_count(self):
        self.pacote();self.c.execute("INSERT INTO etapas(video_id,etapa,status) VALUES('101','interpretar','aguardando_ia')");self.c.commit()
        p=self.painel();a=servidor.executar_api(servidor.api_analitico,{})
        self.assertEqual(p['aguardando_ia'],1);self.assertEqual(a['kpis']['aguardando_ia'],1)
        self.assertEqual(a['resultado_etapa']['interpretar']['bloqueada'],1)

if __name__=='__main__':unittest.main()
