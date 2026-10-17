"""Banco único do projeto: dados/cv.db (SQLite).

Toda linha guarda `origem`, para separar o que o PROGRAMA mediu, o que a IA interpretou,
o que veio da fase anterior (migrado) e o que você validou.
"""
import json, sqlite3, time
from datetime import datetime, timezone
from . import config as C

ESQUEMA = """
CREATE TABLE IF NOT EXISTS execucoes(
  id TEXT PRIMARY KEY, inicio TEXT, fim TEXT, status TEXT, pulso TEXT,
  parametros TEXT, total_entradas INTEGER, ia_provedor TEXT, ia_modelo TEXT,
  disparada_por TEXT, resumo TEXT);
CREATE TABLE IF NOT EXISTS eventos(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, execucao_id TEXT, video_id TEXT,
  etapa TEXT, tipo TEXT, status TEXT, mensagem TEXT, dados TEXT);
CREATE INDEX IF NOT EXISTS ix_eventos_exec ON eventos(execucao_id, id);
CREATE TABLE IF NOT EXISTS videos(
  video_id TEXT PRIMARY KEY, perfil TEXT, url TEXT, titulo TEXT, descricao TEXT,
  duracao_s REAL, views INTEGER, publicado_em TEXT, pasta TEXT, arquivo_video TEXT,
  sha256 TEXT, tamanho_bytes INTEGER, origem TEXT, criado_em TEXT, atualizado_em TEXT,
  ultima_execucao TEXT);
CREATE TABLE IF NOT EXISTS etapas(
  video_id TEXT, etapa TEXT, status TEXT, execucao_id TEXT, inicio TEXT, fim TEXT,
  metricas TEXT, mensagem TEXT, PRIMARY KEY(video_id, etapa));
CREATE TABLE IF NOT EXISTS falas(
  id INTEGER PRIMARY KEY AUTOINCREMENT, video_id TEXT, n INTEGER, inicio_s REAL, fim_s REAL,
  texto TEXT, confianca REAL, origem TEXT);
CREATE INDEX IF NOT EXISTS ix_falas_video ON falas(video_id, n);
CREATE TABLE IF NOT EXISTS frames(
  id INTEGER PRIMARY KEY AUTOINCREMENT, video_id TEXT, n INTEGER, t_s REAL, arquivo TEXT,
  unico INTEGER, igual_a_n INTEGER, largura INTEGER, altura INTEGER,
  mostra_cv INTEGER, enviado_ia INTEGER DEFAULT 0, origem TEXT);
CREATE INDEX IF NOT EXISTS ix_frames_video ON frames(video_id, n);
CREATE TABLE IF NOT EXISTS checagens(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, video_id TEXT, execucao_id TEXT,
  etapa TEXT, nome TEXT, esperado TEXT, obtido TEXT, status TEXT, explicacao TEXT);
CREATE TABLE IF NOT EXISTS analises_ia(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, video_id TEXT, execucao_id TEXT,
  provedor TEXT, modelo TEXT, status TEXT,
  trechos_enviados INTEGER, trechos_total INTEGER,
  frames_enviados INTEGER, frames_unicos INTEGER, frames_total INTEGER,
  tokens_entrada INTEGER, tokens_saida INTEGER, duracao_s REAL,
  arquivo_pedido TEXT, arquivo_resposta TEXT, resumo TEXT, erro TEXT, origem TEXT);
CREATE TABLE IF NOT EXISTS cv_exemplos(
  id INTEGER PRIMARY KEY AUTOINCREMENT, video_id TEXT, analise_id INTEGER, frame_n INTEGER,
  secao TEXT, texto_lido TEXT, legibilidade TEXT, origem TEXT);
CREATE TABLE IF NOT EXISTS recomendacoes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, video_id TEXT, analise_id INTEGER,
  inicio_s REAL, fim_s REAL, categoria TEXT, tipo TEXT, recomendacao TEXT, citacao TEXT,
  citacao_verificada INTEGER, aplica_a TEXT, frame_n INTEGER, confianca TEXT, origem TEXT,
  validacao TEXT DEFAULT 'pendente', validacao_nota TEXT, validado_em TEXT);
CREATE TABLE IF NOT EXISTS notas(
  id INTEGER PRIMARY KEY AUTOINCREMENT, video_id TEXT, tipo TEXT, inicio_s REAL, fim_s REAL,
  texto TEXT, origem TEXT);
"""

ETAPAS = ["baixar", "transcrever", "imagens", "integridade", "interpretar", "relatorio"]
NOMES_ETAPAS = {
    "baixar": "Baixar vídeo", "transcrever": "Transcrever áudio", "imagens": "Extrair imagens",
    "integridade": "Checar integridade", "interpretar": "Interpretar com IA",
    "relatorio": "Relatório do vídeo",
}


def agora():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def conectar():
    C.DADOS.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(C.DB_PATH, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    import os
    con.execute(f"PRAGMA journal_mode={os.environ.get('CV_JOURNAL', 'WAL')}")
    con.execute("PRAGMA busy_timeout=30000")
    con.executescript(ESQUEMA)
    return con


def j(x):
    return json.dumps(x, ensure_ascii=False) if x is not None else None


def linhas(con, sql, args=()):
    return [dict(r) for r in con.execute(sql, args).fetchall()]


def com_retentativa(fn, tentativas=5):
    for i in range(tentativas):
        try:
            return fn()
        except sqlite3.OperationalError as e:
            if "locked" not in str(e) or i == tentativas - 1:
                raise
            time.sleep(0.5 * (i + 1))
