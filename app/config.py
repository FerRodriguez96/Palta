import os

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


class Config:
    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-key-cambiar-en-produccion")

    # Instance folder (credenciales + DB, se monta como volumen persistente)
    INSTANCE_PATH = os.path.join(BASE_DIR, "instance")

    # Carpeta temporal de descargas (se limpia después de cada subida)
    DOWNLOAD_PATH = os.path.join(BASE_DIR, "downloads")

    # Google Drive - cuenta de servicio (service account) usada para leer/descargar
    SERVICE_ACCOUNT_FILE = os.path.join(INSTANCE_PATH, "api-admin-correo.json")

    # Base de datos
    DATABASE_PATH = os.path.join(INSTANCE_PATH, "uploads.db")

    # Google YouTube - OAuth de usuario (canal destino)
    GOOGLE_CLIENT_SECRET = os.path.join(INSTANCE_PATH, "secret_client.json")
    GOOGLE_TOKEN = os.path.join(INSTANCE_PATH, "token.json")

    # Logs
    LOG_PATH = os.path.join(BASE_DIR, "logs")

    # Mailer (notificación de video nuevo)
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    EMAIL_SENDER = os.getenv("EMAIL_SENDER", "fce.youtube@fce.unam.edu.ar")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
    EMAIL_RECIPIENTS = [
        r.strip()
        for r in os.getenv("EMAIL_RECIPIENTS", "prensa@fce.unam.edu.ar").split(",")
        if r.strip()
    ]

    # Limite diario de subidas a YouTube. El tope real de Google es de
    # aproximadamente 100 llamadas videos.insert por dia (por proyecto de
    # Google Cloud, compartido entre todos los usuarios de esta app). Se deja
    # un margen de seguridad por defecto (90) para no quedar exactos al limite.
    YOUTUBE_DAILY_UPLOAD_LIMIT = int(os.getenv("YOUTUBE_DAILY_UPLOAD_LIMIT", "90"))

    # Debug
    DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"
