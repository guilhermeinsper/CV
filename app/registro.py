"""Registro de execução: cada passo vira um evento no banco E numa linha de logs/eventos.jsonl.

O painel lê esses eventos. Se não está no registro, não aconteceu.
"""
import json, threading, uuid
from . import config as C, db


class Execucao:
    def __init__(self, parametros, total, ia_provedor, ia_modelo, disparada_por="terminal"):
        self.id = uuid.uuid4().hex[:12]
        self.con = db.conectar()
        self._lock = threading.Lock()
        C.LOGS.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self.con.execute(
                "INSERT INTO execucoes(id,inicio,status,pulso,parametros,total_entradas,ia_provedor,ia_modelo,disparada_por)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (self.id, db.agora(), "rodando", db.agora(), db.j(parametros), total,
                 ia_provedor, ia_modelo, disparada_por))
            self.con.commit()
        self._parar = threading.Event()
        threading.Thread(target=self._pulso, daemon=True).start()
        self.evento(None, None, "info", "execucao_inicio", f"Execução iniciada com {total} entrada(s)",
                    {"parametros": parametros})

    def _pulso(self):
        con = db.conectar()  # conexão própria da thread
        while not self._parar.wait(3):
            try:
                con.execute("UPDATE execucoes SET pulso=? WHERE id=?", (db.agora(), self.id))
                con.commit()
            except Exception:
                pass

    def evento(self, video_id, etapa, tipo, status, mensagem, dados=None):
        ts = db.agora()
        reg = {"ts": ts, "execucao_id": self.id, "video_id": video_id, "etapa": etapa,
               "tipo": tipo, "status": status, "mensagem": mensagem, "dados": dados}
        with self._lock:
            db.com_retentativa(lambda: (self.con.execute(
                "INSERT INTO eventos(ts,execucao_id,video_id,etapa,tipo,status,mensagem,dados) VALUES(?,?,?,?,?,?,?,?)",
                (ts, self.id, video_id, etapa, tipo, status, mensagem, db.j(dados))), self.con.commit()))
            with open(C.EVENTOS_JSONL, "a", encoding="utf-8") as f:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        prefixo = f"[{etapa or '-'}] " if etapa else ""
        print(f"{ts[11:19]} {prefixo}{mensagem}", flush=True)

    # ---- etapas ----
    def etapa_inicio(self, video_id, etapa):
        with self._lock:
            self.con.execute(
                "INSERT INTO etapas(video_id,etapa,status,execucao_id,inicio,fim,metricas,mensagem) VALUES(?,?,?,?,?,?,?,?)"
                " ON CONFLICT(video_id,etapa) DO UPDATE SET status=excluded.status, execucao_id=excluded.execucao_id,"
                " inicio=excluded.inicio, fim=NULL, metricas=NULL, mensagem=NULL",
                (video_id, etapa, "rodando", self.id, db.agora(), None, None, None))
            self.con.commit()
        self.evento(video_id, etapa, "inicio", "rodando", f"{db.NOMES_ETAPAS[etapa]}: começou")

    def etapa_fim(self, video_id, etapa, status, mensagem, metricas=None):
        with self._lock:
            self.con.execute("UPDATE etapas SET status=?, fim=?, metricas=?, mensagem=? WHERE video_id=? AND etapa=?",
                             (status, db.agora(), db.j(metricas), mensagem, video_id, etapa))
            self.con.commit()
        self.evento(video_id, etapa, "fim", status, f"{db.NOMES_ETAPAS[etapa]}: {mensagem}", metricas)

    def checagem(self, video_id, etapa, nome, esperado, obtido, status, explicacao):
        with self._lock:
            self.con.execute(
                "INSERT INTO checagens(ts,video_id,execucao_id,etapa,nome,esperado,obtido,status,explicacao)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (db.agora(), video_id, self.id, etapa, nome, str(esperado), str(obtido), status, explicacao))
            self.con.commit()
        if status != "ok":
            self.evento(video_id, etapa, "alerta" if status == "alerta" else "erro", status,
                        f"Checagem '{nome}': esperado {esperado}, obtido {obtido}. {explicacao}")

    def encerrar(self, status, resumo):
        self.evento(None, None, "info", "execucao_fim", f"Execução {status}: {resumo}")
        self._parar.set()
        with self._lock:
            self.con.execute("UPDATE execucoes SET status=?, fim=?, resumo=?, pulso=? WHERE id=?",
                             (status, db.agora(), resumo, db.agora(), self.id))
            self.con.commit()
