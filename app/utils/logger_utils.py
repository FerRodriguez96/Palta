import datetime
import os
from loguru import logger
from app.utils.log_buffer import add_log

_configurado = False


def configurar_logger():
    global _configurado

    log_dir = os.getenv("PALTA_LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)

    if _configurado:
        return logger

    fecha = datetime.datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(log_dir, f"palta-{fecha}.log")

    logger.remove()

    # 📁 Archivo
    logger.add(
        log_file,
        rotation="00:00",
        format="{time:DD-MM-YYYY HH:mm:ss} | {level} | {message}",
        level="INFO"
    )

    # 🖥️ Consola
    logger.add(
        lambda msg: print(msg, end=""),
        level="INFO"
    )

    # 📡 Buffer en memoria + WebSocket
    def _emit(msg):
        texto = msg.strip()
        add_log(texto)
        try:
            from app import socketio
            socketio.emit("log", {"mensaje": texto})
        except Exception:
            pass

    logger.add(_emit, level="INFO")

    _configurado = True
    return logger
