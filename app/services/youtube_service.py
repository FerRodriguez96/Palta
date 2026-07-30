import os

# Necesario porque el servidor interno se sirve por HTTP (sin TLS). El
# flujo OAuth de Google exige HTTPS por defecto; esta variable lo permite
# explícitamente para este caso de uso interno. Si en el futuro se pone
# HTTPS delante (nginx/traefik), esta línea puede quitarse.
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

import google_auth_oauthlib.flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from flask import current_app
from app.utils.logger_utils import configurar_logger

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

logger = configurar_logger()

tags = [
    "FCE",
    "UNaM",
    "Facultad de Ciencias Economicas",
]


class YoutubeAuthRequired(Exception):
    """Se lanza cuando no hay un token de YouTube válido y hace falta
    autorizar de nuevo desde la sección Credenciales de la web."""
    pass


def _crear_flow(redirect_uri):
    client_secret_path = current_app.config["GOOGLE_CLIENT_SECRET"]
    if not os.path.exists(client_secret_path):
        raise FileNotFoundError(
            "Falta el archivo secret_client.json (credencial OAuth del canal de YouTube)."
        )
    return google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        client_secret_path, scopes=SCOPES, redirect_uri=redirect_uri
    )


def iniciar_autorizacion(redirect_uri):
    """Devuelve (authorization_url, state) para redirigir al usuario a Google."""
    flow = _crear_flow(redirect_uri)
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return authorization_url, state


def completar_autorizacion(redirect_uri, authorization_response):
    """Completa el intercambio de código por token y lo guarda en disco."""
    flow = _crear_flow(redirect_uri)
    flow.fetch_token(authorization_response=authorization_response)
    creds = flow.credentials

    token_path = current_app.config["GOOGLE_TOKEN"]
    with open(token_path, "w") as token:
        token.write(creds.to_json())

    logger.info("✅ Canal de YouTube autorizado correctamente")
    return creds


def youtube_esta_autorizado():
    token_path = current_app.config["GOOGLE_TOKEN"]
    if not os.path.exists(token_path):
        return False
    try:
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        return creds is not None and (creds.valid or creds.refresh_token)
    except Exception:
        return False


def get_youtube_credentials():
    token_path = current_app.config["GOOGLE_TOKEN"]

    if not os.path.exists(token_path):
        raise YoutubeAuthRequired(
            "No hay token de YouTube. Autorizá el canal desde Credenciales."
        )

    creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("🔄 Refrescando token de YouTube")
                creds.refresh(Request())
                with open(token_path, "w") as token:
                    token.write(creds.to_json())
            except Exception as e:
                logger.error(f"❌ Error refrescando token: {e}")
                raise YoutubeAuthRequired(
                    "El token de YouTube venció y no se pudo refrescar. "
                    "Autorizá el canal de nuevo desde Credenciales."
                )
        else:
            raise YoutubeAuthRequired(
                "El token de YouTube no es válido. Autorizá el canal de nuevo desde Credenciales."
            )

    return creds


def get_youtube_service():
    creds = get_youtube_credentials()
    return build("youtube", "v3", credentials=creds)


def subir_video(nombre_archivo, on_progress=None, titulo=None):
    """Sube un video a YouTube. on_progress(porcentaje:int) es opcional.
    titulo: título a mostrar en YouTube; si no se pasa, se usa el nombre de archivo."""
    youtube = get_youtube_service()
    titulo_final = titulo or os.path.basename(nombre_archivo)

    try:
        logger.info(f"Subiendo video: {nombre_archivo}")

        request_body = {
            "snippet": {
                "title": titulo_final,
                "description": "Subido automáticamente desde Google Drive",
                "categoryId": "27",
                "tags": tags,
            },
            "status": {
                "privacyStatus": "private",
                "license": "creativeCommon",
                "madeForKids": False,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(nombre_archivo, mimetype="video/*", resumable=True)

        request = youtube.videos().insert(
            part="snippet,status",
            body=request_body,
            media_body=media,
        )

        response = None

        while response is None:
            status, response = request.next_chunk()
            porcentaje = int(status.progress() * 100) if status else 0
            logger.info(f"Subiendo {nombre_archivo}: {porcentaje}%")
            if on_progress:
                on_progress(porcentaje)

        if on_progress:
            on_progress(100)

        logger.info(
            f"✅ Video subido: https://www.youtube.com/watch?v={response['id']}"
        )

        return response["id"]

    except Exception as e:
        logger.error(f"❌ Error subiendo video: {e}")
        raise e
