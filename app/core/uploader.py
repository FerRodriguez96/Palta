import os
import threading

from app.services.drive_service import listar_archivos, descargar_archivo, limpiar_nombre_archivo
from app.services.youtube_service import subir_video, subir_miniatura, YoutubeAuthRequired
from app.services.db_service import (
    ya_subido, registrar_subida, listar_carpetas,
    set_estado_proceso, actualizar_progreso_actual, contar_subidas_hoy,
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


def _cupo_agotado(config):
    limite = config.get("YOUTUBE_DAILY_UPLOAD_LIMIT", 90)
    usados = contar_subidas_hoy()
    if usados >= limite:
        mensaje = (
            f"Se alcanzó el límite diario de subidas a YouTube ({usados}/{limite}). "
            "El resto queda pendiente para cuando se reinicie la cuota (medianoche hora Pacífico)."
        )
        logger.warning(mensaje)
        _emit("error", {"mensaje": mensaje})
        return True
    return False


def _finalizar_subida(ruta_local, nombre_seccion, identificador, nombre_original, usuario,
                       titulo, descripcion, privacidad, miniatura_path):
    """Sube un archivo YA PRESENTE en disco a YouTube, sube su miniatura si
    hay, lo registra en la DB y notifica. Es el tramo final compartido tanto
    por el flujo de Drive (que primero descarga) como por el de archivos
    locales (que ya llegan guardados por la ruta). Siempre limpia del disco
    el video y la miniatura al terminar, haya salido bien o mal.
    - identificador: valor unico que se guarda como "drive_id" en la DB para
      evitar duplicados; para Drive es el ID real del archivo, para locales
      es un identificador generado (no hay forma de detectar duplicados ahi,
      cada subida local es una accion explicita y puntual).
    - nombre_original: nombre tal cual lo tenia el archivo (en Drive o en la
      PC del usuario), guardado como referencia aunque se elija otro titulo.
    Devuelve True si se proceso OK. Lanza YoutubeAuthRequired si hay que
    re-autorizar el canal."""

    titulo_final = (titulo or "").strip()[:100] or os.path.basename(ruta_local)
    actualizar_progreso_actual(carpeta_actual=nombre_seccion, archivo_actual=titulo_final)

    try:
        # 1. Subir a YouTube
        def _on_subida(pct):
            _emit("progreso", {"carpeta": nombre_seccion, "archivo": titulo_final,
                                "etapa": "subiendo", "porcentaje": pct})

        _emit("progreso", {"carpeta": nombre_seccion, "archivo": titulo_final,
                            "etapa": "subiendo", "porcentaje": 0})
        youtube_id = subir_video(
            ruta_local, on_progress=_on_subida,
            titulo=titulo_final, descripcion=descripcion, privacidad=privacidad,
        )

        # 2. Miniatura personalizada (opcional, no debe romper el proceso si falla)
        if miniatura_path and os.path.exists(miniatura_path):
            _emit("progreso", {"carpeta": nombre_seccion, "archivo": titulo_final,
                                "etapa": "miniatura", "porcentaje": 100})
            subir_miniatura(youtube_id, miniatura_path)

        # 3. Registrar en DB (guarda tambien el nombre original de referencia)
        registrar_subida(identificador, youtube_id, titulo_final, nombre_seccion, usuario, nombre_original)

        # 4. Notificar por mail (no bloquea el proceso si falla)
        try:
            enviar_notificacion_si_nuevo(
                titulo_final, f"https://www.youtube.com/watch?v={youtube_id}"
            )
        except Exception as e:
            logger.error(f"Error enviando notificacion: {e}")

        _emit("subido", {
            "carpeta": nombre_seccion, "archivo": titulo_final,
            "youtube_id": youtube_id, "usuario": usuario, "nombre_original": nombre_original,
        })

        logger.info(f"Proceso completo OK: {titulo_final}")
        return True

    except YoutubeAuthRequired:
        raise

    except Exception as e:
        logger.error(f"Error procesando {titulo_final}: {e}")
        _emit("error", {"carpeta": nombre_seccion, "archivo": titulo_final, "mensaje": str(e)})
        return False

    finally:
        if os.path.exists(ruta_local):
            os.remove(ruta_local)
        if miniatura_path and os.path.exists(miniatura_path):
            os.remove(miniatura_path)


def _procesar_un_archivo(nombre_carpeta, drive_id, nombre_drive, download_path, usuario=None,
                          titulo=None, descripcion=None, privacidad=None, miniatura_path=None):
    """Descarga un video de Drive y delega el resto (subida, miniatura,
    registro, notificacion) en _finalizar_subida.
    Devuelve True si se proceso, False si ya estaba subido o fallo la descarga.
    Lanza YoutubeAuthRequired si hay que re-autorizar el canal."""

    if ya_subido(drive_id):
        logger.info(f"Ya subido: {nombre_drive}")
        if miniatura_path and os.path.exists(miniatura_path):
            os.remove(miniatura_path)
        return False

    # El nombre que da Drive puede traer "/" (formato de fecha) y otros
    # caracteres invalidos para un nombre de archivo del sistema. Se sanea
    # siempre para la ruta local, independientemente del titulo elegido.
    nombre_local = limpiar_nombre_archivo(nombre_drive) or f"video-{drive_id}"
    ruta_local = os.path.join(download_path, nombre_local)
    actualizar_progreso_actual(carpeta_actual=nombre_carpeta, archivo_actual=nombre_local)

    try:
        def _on_descarga(pct):
            _emit("progreso", {"carpeta": nombre_carpeta, "archivo": nombre_local,
                                "etapa": "descargando", "porcentaje": pct})

        _emit("progreso", {"carpeta": nombre_carpeta, "archivo": nombre_local,
                            "etapa": "descargando", "porcentaje": 0})
        descargar_archivo(drive_id, ruta_local, on_progress=_on_descarga)
    except Exception as e:
        logger.error(f"Error al descargar {nombre_drive}: {e}")
        _emit("error", {"carpeta": nombre_carpeta, "archivo": nombre_drive, "mensaje": str(e)})
        if os.path.exists(ruta_local):
            os.remove(ruta_local)
        if miniatura_path and os.path.exists(miniatura_path):
            os.remove(miniatura_path)
        return False

    return _finalizar_subida(
        ruta_local, nombre_carpeta, drive_id, nombre_drive, usuario,
        titulo, descripcion, privacidad, miniatura_path,
    )


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
                if _cupo_agotado(config):
                    return True
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
    """Procesa solo los videos de Drive elegidos manualmente por el usuario.
    items: lista de dicts {"carpeta", "drive_id", "nombre", "titulo",
    "descripcion", "privacidad", "miniatura_path"}. Todos menos carpeta,
    drive_id y nombre son opcionales.
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

        logger.info(f"Procesando {len(items)} video(s) de Drive seleccionado(s) manualmente.")

        for item in items:
            if _cupo_agotado(config):
                return True
            try:
                _procesar_un_archivo(
                    item["carpeta"], item["drive_id"], item["nombre"], download_path,
                    usuario,
                    titulo=item.get("titulo"),
                    descripcion=item.get("descripcion"),
                    privacidad=item.get("privacidad"),
                    miniatura_path=item.get("miniatura_path"),
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


def procesar_archivos_locales(config, items, usuario=None):
    """Sube archivos de video que el usuario cargo directamente desde su PC
    (no vienen de Drive). El endpoint que llama a esta funcion ya se encarga
    de guardar cada archivo en disco antes de invocarla.
    items: lista de dicts {"ruta_local", "identificador", "nombre_original",
    "titulo", "descripcion", "privacidad", "miniatura_path"}.
    Solo puede haber una ejecucion a la vez (controlado por proceso_lock)."""

    if not proceso_lock.acquire(blocking=False):
        logger.warning("Ya hay un procesamiento en curso, se ignora el pedido.")
        return False

    try:
        set_estado_proceso(True)
        _emit("proceso_estado", {"corriendo": True})

        if not items:
            logger.warning("No se selecciono ningun archivo local para procesar.")
            return True

        logger.info(f"Procesando {len(items)} archivo(s) local(es).")

        for item in items:
            if _cupo_agotado(config):
                return True
            try:
                _finalizar_subida(
                    item["ruta_local"], "Subida local", item["identificador"], item["nombre_original"],
                    usuario,
                    item.get("titulo"), item.get("descripcion"), item.get("privacidad"),
                    item.get("miniatura_path"),
                )
            except YoutubeAuthRequired as e:
                logger.error(f"{e}")
                _emit("error", {"carpeta": "Subida local", "mensaje": str(e)})
                return False

        return True

    finally:
        set_estado_proceso(False)
        _emit("proceso_estado", {"corriendo": False})
        proceso_lock.release()
