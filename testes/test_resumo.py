"""Resumo em memória: fuso, deduplicação e leitura sem mutação."""
import sqlite3
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from app.db import ESQUEMA
from app.resumo import resumir
from app import config as C, servidor


class ResumoTests(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:')
        self.c.row_factory = sqlite3.Row
        self.c.executescript(ESQUEMA)
        self.addCleanup(self.c.close)
        self.c.execute("INSERT INTO videos(video_id,criado_em) VALUES('a','2026-10-16T23:30:00-03:00')")
        for ts, etapa, status in [('2026-10-17T02:59:59+00:00','transcrever','ok'),
                                  ('2026-10-16T19:00:00-03:00','transcrever','ok'),
                                  ('2026-10-17T03:00:00+00:00','imagens','alerta'),
                                  ('2026-10-16T12:00:00-03:00','integridade','falha')]:
            self.c.execute('INSERT INTO eventos(video_id,ts,tipo,etapa,status) VALUES(?,?,?,?,?)',('a',ts,'fim',etapa,status))
        self.c.commit()

    def test_local_day_boundary_and_duplicate(self):
        r=resumir(self.c,'data','2026-10-16')
        self.assertEqual(r['etapas']['transcrever'],1)
        self.assertEqual(r['etapas']['imagens'],0)
        self.assertEqual(r['etapas']['integridade'],0)
        self.assertEqual(r['novos'],1)

    def test_month_and_all_deduplicate(self):
        for periodo in ('mes','tudo'):
            r=resumir(self.c,periodo,'2026-10-16')
            self.assertEqual(r['etapas']['transcrever'],1)
            self.assertEqual(r['etapas']['imagens'],1)
            self.assertEqual(r['videos_com_atividade'],1)

    def test_other_month_empty_and_totals_global(self):
        r=resumir(self.c,'mes','2026-09-01')
        self.assertEqual(r['videos_com_atividade'],0)
        self.assertEqual(r['total_biblioteca'],1)

    def test_no_write(self):
        before=self.c.total_changes
        resumir(self.c,'tudo')
        self.assertEqual(before,self.c.total_changes)

    def test_invalid_filter(self):
        for periodo,data in [('invalido',None),('data','2026-99-99')]:
            with self.assertRaises(ValueError):resumir(self.c,periodo,data)

    def test_legacy_not_promoted_to_success(self):
        self.c.execute("INSERT INTO videos(video_id,origem) VALUES('legado','migrado')")
        r=resumir(self.c,'tudo')
        self.assertEqual(r['total_biblioteca'],2)
        self.assertEqual(r['etapas']['transcrever'],1)

    def test_same_name_uploads_preserve_both_files(self):
        with tempfile.TemporaryDirectory() as pasta, patch.object(C, 'DADOS', Path(pasta)), patch.object(C, 'BASE', Path(pasta)):
            with patch.object(servidor.time, 'strftime', return_value='20261016_190000'):
                a=servidor.salvar_envio('teste.mp4', b'primeiro')
                b=servidor.salvar_envio('teste.mp4', b'segundo')
            self.assertNotEqual(a['arquivo'], b['arquivo'])
            self.assertEqual((Path(pasta)/a['arquivo']).read_bytes(), b'primeiro')
            self.assertEqual((Path(pasta)/b['arquivo']).read_bytes(), b'segundo')


if __name__=='__main__':unittest.main()
