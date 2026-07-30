import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from flask import current_app
from app.utils.logger_utils import configurar_logger

logger = configurar_logger()


def _historial_path():
    return Path(current_app.config["INSTANCE_PATH"]) / "videos_enviados.json"


def _cargar_historial():
    path = _historial_path()
    if not path.exists():
        path.write_text(json.dumps([]))
    try:
        return json.loads(path.read_text())
    except Exception:
        return []


def _guardar_historial(historial):
    _historial_path().write_text(json.dumps(historial, indent=2))


def enviar_notificacion_si_nuevo(titulo_video, url_video):
    historial = _cargar_historial()

    if url_video in historial:
        logger.info(f"📭 El video '{titulo_video}' ya fue notificado, no se enviará email.")
        return

    sender = current_app.config["EMAIL_SENDER"]
    password = current_app.config["EMAIL_PASSWORD"]
    recipients = current_app.config["EMAIL_RECIPIENTS"]

    if not password:
        logger.warning(
            "⚠️ No hay EMAIL_PASSWORD configurado, se omite el envío de notificación por mail."
        )
        return

    asunto = f"Nuevo video subido: {titulo_video}"
    cuerpo = f"Se ha subido un nuevo video.\n\nTítulo: {titulo_video}\nURL: {url_video}"

    mensaje = MIMEMultipart()
    mensaje["From"] = sender
    mensaje["To"] = ", ".join(recipients)
    mensaje["Subject"] = asunto
    mensaje.attach(MIMEText(cuerpo, "plain"))

    try:
        with smtplib.SMTP(current_app.config["SMTP_SERVER"], current_app.config["SMTP_PORT"]) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, recipients, mensaje.as_string())

        logger.success(f"📨 Notificación enviada: '{titulo_video}' -> {url_video}")

        historial.append(url_video)
        _guardar_historial(historial)

    except Exception as e:
        logger.error(f"❌ Error enviando email: {e}")
