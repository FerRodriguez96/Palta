import threading
import json
import re
from flask import Blueprint, render_template, jsonify, current_app, request, redirect, url_for, session, flash
from flask_login import (
    login_user, logout_user, login_required, current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash

from app.core.uploader import procesar_videos, procesar_seleccionados, hay_proceso_corriendo
from app.utils.log_buffer import get_logs
from app.services import db_service
from app.services.drive_service import listar_archivos, limpiar_nombre_archivo
from app.services.youtube_service import (
    iniciar_autorizacion, completar_autorizacion, youtube_esta_autorizado,
)
from app.models import User
import os
import re
import json
from functools import wraps

bp = Blueprint("main", __name__)

TITULO_MAX_LEN = 100


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("No tenés permisos para acceder a esa sección.", "error")
            return redirect(url_for("main.index"))
        return f(*args, **kwargs)
    return wrapper


def _extraer_id_carpeta(valor):
    """Acepta tanto un ID de carpeta de Drive suelto como una URL completa
    (ej: https://drive.google.com/drive/folders/<id>?usp=sharing) y devuelve
    solo el ID."""
    valor = (valor or "").strip()
    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", valor)
    if match:
        return match.group(1)
    match = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", valor)
    if match:
        return match.group(1)
    return valor


# ---------- Autenticacion ----------

@bp.before_app_request
def _requerir_login():
    # Si todavia no hay ningun usuario creado, solo se permite /setup
    if not db_service.hay_usuarios():
        if request.endpoint not in ("main.setup", "static"):
            return redirect(url_for("main.setup"))
        return

    # Rutas publicas que no requieren sesion iniciada
    rutas_publicas = ("main.login", "static")
    if request.endpoint in rutas_publicas:
        return

    if not current_user.is_authenticated:
        return redirect(url_for("main.login", next=request.path))


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    if db_service.hay_usuarios():
        return redirect(url_for("main.login"))

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        nombre_completo = request.form.get("nombre_completo", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Completá usuario y contraseña.", "error")
            return redirect(url_for("main.setup"))

        db_service.crear_usuario(username, generate_password_hash(password), nombre_completo, es_admin=True)
        flash("Cuenta creada. Ya podés iniciar sesión.", "success")
        return redirect(url_for("main.login"))

    return render_template("setup.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if db_service.hay_usuarios() and current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if not db_service.hay_usuarios():
        return redirect(url_for("main.setup"))

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        fila = db_service.obtener_usuario_por_username(username)
        if fila and check_password_hash(fila["password_hash"], password):
            login_user(User(fila))
            destino = request.args.get("next") or url_for("main.index")
            return redirect(destino)

        flash("Usuario o contraseña incorrectos.", "error")

    return render_template("login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.login"))


# ---------- Usuarios ----------

@bp.route("/usuarios")
@login_required
@admin_required
def usuarios():
    return render_template("usuarios.html", usuarios=db_service.listar_usuarios())


@bp.route("/usuarios/agregar", methods=["POST"])
@login_required
@admin_required
def usuarios_agregar():
    username = request.form.get("username", "").strip().lower()
    nombre_completo = request.form.get("nombre_completo", "").strip()
    password = request.form.get("password", "")
    es_admin = request.form.get("es_admin") == "1"

    if not username or not password:
        flash("Completá usuario y contraseña.", "error")
        return redirect(url_for("main.usuarios"))

    if db_service.obtener_usuario_por_username(username):
        flash("Ya existe un usuario con ese nombre.", "error")
        return redirect(url_for("main.usuarios"))

    db_service.crear_usuario(username, generate_password_hash(password), nombre_completo, es_admin=es_admin)
    flash(f"Usuario '{username}' creado.", "success")
    return redirect(url_for("main.usuarios"))


@bp.route("/usuarios/<int:user_id>/eliminar", methods=["POST"])
@login_required
@admin_required
def usuarios_eliminar(user_id):
    if str(user_id) == current_user.id:
        flash("No podés eliminar tu propio usuario mientras estás conectado con él.", "error")
        return redirect(url_for("main.usuarios"))

    db_service.eliminar_usuario(user_id)
    flash("Usuario eliminado.", "success")
    return redirect(url_for("main.usuarios"))


@bp.route("/usuarios/<int:user_id>/alternar-admin", methods=["POST"])
@login_required
@admin_required
def usuarios_alternar_admin(user_id):
    nuevo_valor = request.form.get("es_admin") == "1"

    if str(user_id) == current_user.id and not nuevo_valor:
        flash("No podés quitarte el rol de administrador a vos mismo.", "error")
        return redirect(url_for("main.usuarios"))

    db_service.alternar_admin(user_id, nuevo_valor)
    flash("Permisos actualizados.", "success")
    return redirect(url_for("main.usuarios"))


@bp.route("/usuarios/<int:user_id>/restablecer-password", methods=["POST"])
@login_required
@admin_required
def usuarios_restablecer_password(user_id):
    nueva_password = request.form.get("nueva_password", "")
    if len(nueva_password) < 4:
        flash("La contraseña nueva debe tener al menos 4 caracteres.", "error")
        return redirect(url_for("main.usuarios"))

    db_service.actualizar_password(user_id, generate_password_hash(nueva_password))
    flash("Contraseña restablecida.", "success")
    return redirect(url_for("main.usuarios"))


# ---------- Mi cuenta ----------

@bp.route("/cuenta", methods=["GET", "POST"])
@login_required
def cuenta():
    if request.method == "POST":
        actual = request.form.get("password_actual", "")
        nueva = request.form.get("password_nueva", "")
        confirmar = request.form.get("password_confirmar", "")

        fila = db_service.obtener_usuario_por_id(current_user.id)

        if not fila or not check_password_hash(fila["password_hash"], actual):
            flash("La contraseña actual no es correcta.", "error")
        elif len(nueva) < 4:
            flash("La contraseña nueva debe tener al menos 4 caracteres.", "error")
        elif nueva != confirmar:
            flash("La confirmación no coincide con la contraseña nueva.", "error")
        else:
            db_service.actualizar_password(current_user.id, generate_password_hash(nueva))
            flash("Contraseña actualizada.", "success")
            return redirect(url_for("main.cuenta"))

    return render_template("cuenta.html")


# ---------- Dashboard ----------

@bp.route("/")
def index():
    carpetas = db_service.listar_carpetas()
    estado = db_service.get_estado_proceso()
    return render_template(
        "index.html", carpetas=carpetas, estado=estado,
        youtube_ok=youtube_esta_autorizado(),
        drive_ok=os.path.exists(current_app.config["SERVICE_ACCOUNT_FILE"]),
    )


@bp.route("/procesar", methods=["POST"])
def procesar():
    if hay_proceso_corriendo():
        return {"status": "Ya hay un procesamiento en curso"}, 409

    app = current_app._get_current_object()
    config = dict(app.config)
    usuario = current_user.username

    def run():
        with app.app_context():
            procesar_videos(config, usuario)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    return {"status": "Procesamiento iniciado"}, 202


@bp.route("/procesar/seleccion", methods=["POST"])
def procesar_seleccion():
    if hay_proceso_corriendo():
        return {"status": "Ya hay un procesamiento en curso"}, 409

    import json as _json

    items_raw = request.form.get("items")
    if not items_raw:
        return {"status": "No se seleccionó ningún video"}, 400

    try:
        items_entrantes = _json.loads(items_raw)
    except Exception:
        return {"status": "Formato de selección inválido"}, 400

    carpetas = {c["id"]: c for c in db_service.listar_carpetas()}
    download_path = current_app.config["DOWNLOAD_PATH"]
    os.makedirs(download_path, exist_ok=True)

    items = []
    for it in items_entrantes:
        carpeta = carpetas.get(it.get("carpeta_id"))
        if not carpeta or not it.get("drive_id") or not it.get("nombre"):
            continue

        titulo = (it.get("titulo") or "").strip()[:TITULO_MAX_LEN] or None
        descripcion = (it.get("descripcion") or "").strip()[:5000] or None
        privacidad = it.get("privacidad") if it.get("privacidad") in ("private", "unlisted", "public") else "private"

        miniatura_path = None
        archivo = request.files.get(f"thumbnail_{it['drive_id']}")
        if archivo and archivo.filename:
            extension = os.path.splitext(archivo.filename)[1] or ".jpg"
            nombre_seguro = f"thumb-{abs(hash(it['drive_id']))}{extension}"
            miniatura_path = os.path.join(download_path, nombre_seguro)
            archivo.save(miniatura_path)

        items.append({
            "carpeta": carpeta["nombre"],
            "drive_id": it["drive_id"],
            "nombre": it["nombre"],
            "titulo": titulo,
            "descripcion": descripcion,
            "privacidad": privacidad,
            "miniatura_path": miniatura_path,
        })

    if not items:
        return {"status": "La selección no es válida"}, 400

    app = current_app._get_current_object()
    config = dict(app.config)
    usuario = current_user.username

    def run():
        with app.app_context():
            procesar_seleccionados(config, items, usuario)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    return {"status": f"Procesando {len(items)} video(s) seleccionado(s)"}, 202


@bp.route("/estado")
def estado():
    return jsonify({
        "corriendo": hay_proceso_corriendo(),
        **(db_service.get_estado_proceso() or {}),
    })


@bp.route("/api/subidas")
def api_subidas():
    q = request.args.get("q", "").strip()
    try:
        page = max(int(request.args.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    per_page = 10

    items, total = db_service.listar_subidas(q=q or None, page=page, per_page=per_page)
    pages = max((total + per_page - 1) // per_page, 1)

    return jsonify({
        "items": items, "total": total, "page": page, "per_page": per_page, "pages": pages,
    })


@bp.route("/api/cuota")
def api_cuota():
    return jsonify({
        "usados": db_service.contar_subidas_hoy(),
        "limite": current_app.config["YOUTUBE_DAILY_UPLOAD_LIMIT"],
    })


@bp.route("/api/logs")
def api_logs():
    return jsonify(get_logs())


@bp.route("/logs")
def logs():
    return render_template("logs.html")


@bp.route("/api/pendientes/<int:carpeta_id>")
def pendientes(carpeta_id):
    carpetas = {c["id"]: c for c in db_service.listar_carpetas()}
    carpeta = carpetas.get(carpeta_id)
    if not carpeta:
        return jsonify({"error": "Carpeta no encontrada"}), 404

    try:
        archivos = listar_archivos(carpeta["drive_folder_id"])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    pendientes = []
    for a in archivos:
        if db_service.ya_subido(a["id"]):
            continue
        sugerido = limpiar_nombre_archivo(a["name"]) or a["name"]
        pendientes.append({
            **a,
            "titulo_sugerido": sugerido[:TITULO_MAX_LEN],
        })

    return jsonify({"pendientes": pendientes, "titulo_max_len": TITULO_MAX_LEN})


# ---------- Carpetas ----------

@bp.route("/carpetas")
def carpetas():
    return render_template("carpetas.html", carpetas=db_service.listar_carpetas())


@bp.route("/carpetas/agregar", methods=["POST"])
def carpetas_agregar():
    nombre = request.form.get("nombre", "").strip()
    drive_folder_id = _extraer_id_carpeta(request.form.get("drive_folder_id", ""))

    if not nombre or not drive_folder_id:
        flash("Completá el nombre y el ID o URL de la carpeta de Drive.", "error")
        return redirect(url_for("main.carpetas"))

    try:
        db_service.agregar_carpeta(nombre, drive_folder_id)
        flash(f"Carpeta '{nombre}' agregada.", "success")
    except Exception as e:
        flash(f"No se pudo agregar la carpeta: {e}", "error")

    return redirect(url_for("main.carpetas"))


@bp.route("/carpetas/<int:carpeta_id>/eliminar", methods=["POST"])
def carpetas_eliminar(carpeta_id):
    db_service.eliminar_carpeta(carpeta_id)
    flash("Carpeta eliminada.", "success")
    return redirect(url_for("main.carpetas"))


@bp.route("/carpetas/<int:carpeta_id>/alternar", methods=["POST"])
def carpetas_alternar(carpeta_id):
    activo = request.form.get("activo") == "1"
    db_service.alternar_carpeta(carpeta_id, activo)
    return redirect(url_for("main.carpetas"))


# ---------- Credenciales ----------

@bp.route("/credenciales")
@login_required
@admin_required
def credenciales():
    drive_ok = os.path.exists(current_app.config["SERVICE_ACCOUNT_FILE"])
    client_secret_ok = os.path.exists(current_app.config["GOOGLE_CLIENT_SECRET"])
    return render_template(
        "credenciales.html",
        drive_ok=drive_ok,
        client_secret_ok=client_secret_ok,
        youtube_ok=youtube_esta_autorizado(),
    )


@bp.route("/credenciales/drive", methods=["POST"])
@login_required
@admin_required
def credenciales_drive():
    archivo = request.files.get("archivo")
    if not archivo or not archivo.filename.endswith(".json"):
        flash("Subí un archivo .json válido de la cuenta de servicio.", "error")
        return redirect(url_for("main.credenciales"))

    contenido = archivo.read()
    try:
        datos = json.loads(contenido)
    except Exception:
        flash("Ese archivo no es un JSON válido.", "error")
        return redirect(url_for("main.credenciales"))

    if datos.get("type") != "service_account" or not datos.get("client_email"):
        flash(
            "Ese JSON no parece ser una cuenta de servicio de Google (falta "
            "'type: service_account' o 'client_email'). Revisá que sea el archivo correcto.",
            "error",
        )
        return redirect(url_for("main.credenciales"))

    with open(current_app.config["SERVICE_ACCOUNT_FILE"], "wb") as f:
        f.write(contenido)

    flash(f"Credencial de Google Drive actualizada ({datos['client_email']}).", "success")
    return redirect(url_for("main.credenciales"))


@bp.route("/credenciales/client-secret", methods=["POST"])
@login_required
@admin_required
def credenciales_client_secret():
    archivo = request.files.get("archivo")
    if not archivo or not archivo.filename.endswith(".json"):
        flash("Subí un archivo .json válido de client secret.", "error")
        return redirect(url_for("main.credenciales"))

    contenido = archivo.read()
    try:
        datos = json.loads(contenido)
    except Exception:
        flash("Ese archivo no es un JSON válido.", "error")
        return redirect(url_for("main.credenciales"))

    bloque = datos.get("web") or datos.get("installed")
    if not bloque or not bloque.get("client_id") or not bloque.get("client_secret"):
        flash(
            "Ese JSON no parece ser una credencial OAuth de Google (falta 'client_id' "
            "o 'client_secret' dentro de 'web'/'installed'). Revisá que sea el archivo correcto.",
            "error",
        )
        return redirect(url_for("main.credenciales"))

    with open(current_app.config["GOOGLE_CLIENT_SECRET"], "wb") as f:
        f.write(contenido)

    flash("Client secret de YouTube actualizado. Ahora podés autorizar el canal.", "success")
    return redirect(url_for("main.credenciales"))


@bp.route("/credenciales/youtube/autorizar")
@login_required
@admin_required
def credenciales_youtube_autorizar():
    redirect_uri = url_for("main.credenciales_youtube_callback", _external=True)
    try:
        authorization_url, state = iniciar_autorizacion(redirect_uri)
    except FileNotFoundError as e:
        flash(str(e), "error")
        return redirect(url_for("main.credenciales"))

    session["oauth_state"] = state
    return redirect(authorization_url)


@bp.route("/credenciales/youtube/callback")
@login_required
@admin_required
def credenciales_youtube_callback():
    redirect_uri = url_for("main.credenciales_youtube_callback", _external=True)
    try:
        completar_autorizacion(redirect_uri, request.url)
        flash("Canal de YouTube autorizado correctamente.", "success")
    except Exception as e:
        flash(f"No se pudo autorizar el canal: {e}", "error")

    return redirect(url_for("main.credenciales"))
