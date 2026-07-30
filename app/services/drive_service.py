import io
import os
import re
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload
from flask import current_app
from app.utils.logger_utils import configurar_logger

SCOPES = ['https://www.googleapis.com/auth/drive']

logger = configurar_logger()


def get_drive_service():
    ruta = current_app.config["SERVICE_ACCOUNT_FILE"]

    if not os.path.exists(ruta):
        raise FileNotFoundError(
            "No se encontró la credencial de la cuenta de servicio de Drive. "
            "Subila desde la sección Credenciales."
        )

    creds = service_account.Credentials.from_service_account_file(
        ruta,
        scopes=SCOPES
    )

    service = build('drive', 'v3', credentials=creds)

    return service


def limpiar_nombre_archivo(nombre):
    match = re.search(r'(\d{4})/(\d{2})/(\d{2})', nombre)
    if match:
        anio, mes, dia = match.groups()
        fecha_formateada = f"{dia}/{mes}/{anio}"
        nombre = nombre.replace(match.group(0), fecha_formateada)

    nombre = re.sub(r'\d{2}:\d{2}\sGMT[+-]\d{2}:\d{2}', '', nombre)
    nombre = re.sub(r'(?i)Recording', '', nombre)

    titulo_normalizado = re.sub(r'[<>"&\'\\|\*\?:#\s/]+', "-", nombre)

    return titulo_normalizado.strip("-")[:99]


def listar_archivos(folder_id):
    """Lista los videos de una carpeta de Drive. Recibe solo el folder_id."""
    service = get_drive_service()

    query = f"'{folder_id}' in parents and mimeType contains 'video/' and trashed = false"

    results = service.files().list(
        q=query,
        fields="files(id, name, size, createdTime)",
        pageSize=200,
    ).execute()

    return results.get('files', [])


def descargar_archivo(file_id, file_name, on_progress=None):
    """Descarga un archivo de Drive. on_progress(porcentaje:int) es opcional."""
    service = get_drive_service()

    try:
        request = service.files().get_media(fileId=file_id)
        fh = io.FileIO(file_name, 'wb')
        downloader = MediaIoBaseDownload(fh, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()
            porcentaje = int(status.progress() * 100) if status else 0
            logger.info(f"Descargando {file_name}: {porcentaje}% completado.")
            if on_progress:
                on_progress(porcentaje)

        fh.close()
        logger.info(f"✅ Archivo {file_name} descargado correctamente.")

        if on_progress:
            on_progress(100)

    except Exception as e:
        logger.error(f"❌ Error al descargar el archivo {file_name}: {e}")
        raise e
