"""Reinício automático do painel quando o código do programa muda (o usuário não precisa fechar/abrir a janela).
Usa o próprio ABRIR_PAINEL.bat: ele fecha o painel antigo (porta 8770, só se for app.servidor) e abre o novo."""
import os, subprocess, time
from . import config as C

FLAG = C.DADOS / "REINICIAR_SERVIDOR.flag"


def assinatura_codigo():
    return tuple(sorted((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in C.APP.glob("*.py")))


def disparar(motivo):
    if os.name != "nt":
        return False
    bat = C.BASE / "ABRIR_PAINEL.bat"
    if not bat.exists():
        return False
    C.LOGS.mkdir(parents=True, exist_ok=True)
    with open(C.LOGS / "reinicios_painel.txt", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} reinício do painel pedido: {motivo}\n")
    # janela nova (CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP): sobrevive ao fim de quem pediu
    subprocess.Popen(["cmd", "/c", str(bat), "--sem-navegador"], cwd=str(C.BASE), creationflags=0x00000010 | 0x00000200)
    return True


def pedido_por_flag(quem):
    """Se existir dados/REINICIAR_SERVIDOR.flag, consome (renomeia para logs/) e reinicia o painel."""
    if not FLAG.exists():
        return False
    try:
        FLAG.replace(C.LOGS / f"REINICIAR_SERVIDOR_feito_{time.strftime('%Y%m%d_%H%M%S')}.flag")
    except OSError:
        return False
    return disparar(f"pedido por arquivo (lido por {quem})")
