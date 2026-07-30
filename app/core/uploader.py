import os
import threading

from app.services.drive_service import listar_archivos, descargar_archivo, limpiar_nombre_archivo
from app.services.youtube_service import subir_video, YoutubeAuthRequired
from app.services.db_service import (
    ya_subido, registrar_subida, listar_carpetas,
    set_estado_proceso, actualizar_progreso_actual,
)
from app.services.mailer_service import enviar_notificacion_si_nuevo
from app.utils.logger_utils import configurar_logger

logger = configurar_logger()

# Lock global: solo un procesamiento a la vez
proceso_lock = threading.Lock()


def hay_proceso_corriendo():
    return proceso_lock.locked()


def _emit(evento, data):
    try:
        from app import socketio
        socketio.emit(evento, data)
    except Exception:
        pass


def _procesar_un_archivo(nombre_carpeta, drive_id, nombre_drive, download_path, usuario=None, titulo=None):
    """Descarga un video de Drive, lo sube a YouTube, lo registra y notifica.
    - nombre_drive: nombre tal cual viene de Drive (se usa para armar el nombre
      de archivo local, siempre saneado).
    - titulo: titulo elegido a mano por el usuario (opcional). Si no se pasa,
      se usa el nombre saneado como titulo.
    Devuelve True si se proceso, False si ya estaba subido.
    Lanza YoutubeAuthRequired si hay que re-autorizar el canal."""

    if ya_subido(drive_id):
        logger.info(f"Ya subido: {nombre_drive}")
        return False

    # El nombre que da Drive puede traer "/" (formato de fecha) y otros
    # caracteres invalidos para un nombre de archivo del sistema. Se sanea
    # siempre para la ruta local, independientemente del titulo elegido.
    nombre_local = limpiar_nombre_archivo(nombre_drive) or f"video-{drive_id}"
    titulo_final = (titulo or "").strip()[:100] or nombre_local

    ruta_local = os.path.join(download_path, nombre_local)
    actualizar_progreso_actual(carpeta_actual=nombre_carpeta, archivo_actual=titulo_final)

    try:
        # 1. Descargar
        def _on_descarga(pct):
            _emit("progreso", {"carpeta": nombre_carpeta, "archivo": titulo_final,
                                "etapa": "descargando", "porcentaje": pct})

        _emit("progreso", {"carpeta": nombre_carpeta, "archivo": titulo_final,
                            "etapa": "descargando", "porcentaje": 0})
        descargar_archivo(drive_id, ruta_local, on_progress=_on_descarga)

        # 2. Subir a YouTube
        def _on_subida(pct):
            _emit("progreso", {"carpeta": nombre_carpeta, "archivo": titulo_final,
                                "etapa": "subiendo", "porcentaje": pct})

        _emit("progreso", {"carpeta": nombre_carpeta, "archivo": titulo_final,
                            "etapa": "subiendo", "porcentaje": 0})
        youtube_id = subir_video(ruta_local, on_progress=_on_subida, titulo=titulo_final)

        # 3. Registrar en DB
        registrar_subida(drive_id, youtube_id, titulo_final, nombre_carpeta, usuario)

        # 4. Notificar por mail (no bloquea el proceso si falla)
        try:
            enviar_notificacion_si_nuevo(
                titulo_final, f"https://www.youtube.com/watch?v={youtube_id}"
            )
        except Exception as e:
            logger.error(f"Error enviando notificacion: {e}")

        _emit("subido", {
            "carpeta": nombre_carpeta, "archivo": titulo_final,
            "youtube_id": youtube_id, "usuario": usuario,
        })

        logger.info(f"Proceso completo OK: {titulo_final}")
        return True

    except YoutubeAuthRequired:
        raise

    except Exception as e:
        logger.error(f"Error procesando {titulo_final}: {e}")
        _emit("error", {"carpeta": nombre_carpeta, "archivo": titulo_final, "mensaje": str(e)})
        return False

    finally:
        if os.path.exists(ruta_local):
            os.remove(ruta_local)


def procesar_videos(config, usuario=None):
    """Recorre todas las carpetas activas configuradas en la DB, descarga
    los videos nuevos y los sube a YouTube. Solo puede haber una ejecucion
    a la vez (controlado por proceso_lock)."""

    if not proceso_lock.acquire(blocking=False):
        logger.warning("Ya hay un procesamiento en curso, se ignora el pedido.")
        return False

    download_path = config["DOWNLOAD_PATH"]
    os.makedirs(download_path, exist_ok=True)

    try:
        set_estado_proceso(True)
        _emit("proceso_estado", {"corriendo": True})

        carpetas = listar_carpetas(solo_activas=True)

        if not carpetas:
            logger.warning("No hay carpetas activas configuradas.")
            return True

        for carpeta in carpetas:
            nombre_carpeta = carpeta["nombre"]
            carpeta_drive_id = carpeta["drive_folder_id"]

            logger.info(f"Procesando carpeta: {nombre_carpeta}")
            actualizar_progreso_actual(carpeta_actual=nombre_carpeta)
            _emit("progreso", {"carpeta": nombre_carpeta, "archivo": None,
                                "etapa": "listando", "porcentaje": 0})

            try:
                videos = listar_archivos(carpeta_drive_id)
            except Exception as e:
                logger.error(f"Error listando '{nombre_carpeta}': {e}")
                _emit("error", {"carpeta": nombre_carpeta, "mensaje": str(e)})
                continue

            if not videos:
                logger.warning(f"No hay videos en {nombre_carpeta}")
                continue

            for video in videos:
                try:
                    _procesar_un_archivo(nombre_carpeta, video["id"], video["name"], download_path, usuario)
                except YoutubeAuthRequired as e:
                    logger.error(f"{e}")
                    _emit("error", {"carpeta": nombre_carpeta, "mensaje": str(e)})
                    return False

        return True

    finally:
        set_estado_proceso(False)
        _emit("proceso_estado", {"corriendo": False})
        proceso_lock.release()


def procesar_seleccionados(config, items, usuario=None):
    """Procesa solo los videos elegidos manualmente por el usuario.
    items: lista de dicts {"carpeta": nombre_carpeta, "drive_id": ..., "nombre": ..., "titulo": ...}
    Solo puede haber una ejecucion a la vez (controlado por proceso_lock)."""

    if not proceso_lock.acquire(blocking=False):
        logger.warning("Ya hay un procesamiento en curso, se ignora el pedido.")
        return False

    download_path = config["DOWNLOAD_PATH"]
    os.makedirs(download_path, exist_ok=True)

    try:
        set_estado_proceso(True)
        _emit("proceso_estado", {"corriendo": True})

        if not items:
            logger.warning("No se selecciono ningun video para procesar.")
            return True

        logger.info(f"Procesando {len(items)} video(s) seleccionado(s) manualmente.")

        for item in items:
            try:
                _procesar_un_archivo(
                    item["carpeta"], item["drive_id"], item["nombre"], download_path,
                    usuario, item.get("titulo"),
                )
            except YoutubeAuthRequired as e:
                logger.error(f"{e}")
                _emit("error", {"carpeta": item["carpeta"], "mensaje": str(e)})
                return False

        return True

    finally:
        set_estado_proceso(False)
        _emit("proceso_estado", {"corriendo": False})
        proceso_lock.release()
