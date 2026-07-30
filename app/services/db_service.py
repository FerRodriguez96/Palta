import sqlite3
from datetime import datetime
from flask import current_app


def _conn():
    db_path = current_app.config["DATABASE_PATH"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drive_id TEXT UNIQUE,
            youtube_id TEXT,
            nombre_archivo TEXT,
            carpeta TEXT,
            fecha_subida TEXT,
            subido_por TEXT
        )
    """)

    # Migracion: si la DB ya existia sin la columna subido_por, se agrega.
    cursor.execute("PRAGMA table_info(uploads)")
    columnas = [fila[1] for fila in cursor.fetchall()]
    if "subido_por" not in columnas:
        cursor.execute("ALTER TABLE uploads ADD COLUMN subido_por TEXT")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS carpetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            drive_folder_id TEXT NOT NULL UNIQUE,
            activo INTEGER NOT NULL DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS estado_proceso (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            corriendo INTEGER NOT NULL DEFAULT 0,
            iniciado_en TEXT,
            carpeta_actual TEXT,
            archivo_actual TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            nombre_completo TEXT,
            password_hash TEXT NOT NULL,
            creado_en TEXT
        )
    """)

    cursor.execute("SELECT COUNT(*) FROM estado_proceso WHERE id = 1")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO estado_proceso (id, corriendo) VALUES (1, 0)"
        )

    conn.commit()
    conn.close()


# ---------- Subidas ----------

def registrar_subida(drive_id, youtube_id, nombre_archivo, carpeta, usuario=None):
    conn = _conn()
    conn.execute(
        """INSERT OR IGNORE INTO uploads (drive_id, youtube_id, nombre_archivo, carpeta, fecha_subida, subido_por)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (drive_id, youtube_id, nombre_archivo, carpeta,
         datetime.now().strftime("%d-%m-%Y %H:%M:%S"), usuario),
    )
    conn.commit()
    conn.close()


def ya_subido(drive_id):
    conn = _conn()
    row = conn.execute(
        "SELECT 1 FROM uploads WHERE drive_id = ?", (drive_id,)
    ).fetchone()
    conn.close()
    return row is not None


def listar_subidas(limit=200):
    conn = _conn()
    rows = conn.execute(
        """SELECT id, drive_id, youtube_id, nombre_archivo, carpeta, fecha_subida, subido_por
           FROM uploads ORDER BY id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------- Carpetas ----------

def listar_carpetas(solo_activas=False):
    conn = _conn()
    query = "SELECT * FROM carpetas"
    if solo_activas:
        query += " WHERE activo = 1"
    query += " ORDER BY nombre"
    rows = conn.execute(query).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def agregar_carpeta(nombre, drive_folder_id):
    conn = _conn()
    conn.execute(
        "INSERT INTO carpetas (nombre, drive_folder_id, activo) VALUES (?, ?, 1)",
        (nombre, drive_folder_id),
    )
    conn.commit()
    conn.close()


def eliminar_carpeta(carpeta_id):
    conn = _conn()
    conn.execute("DELETE FROM carpetas WHERE id = ?", (carpeta_id,))
    conn.commit()
    conn.close()


def alternar_carpeta(carpeta_id, activo):
    conn = _conn()
    conn.execute(
        "UPDATE carpetas SET activo = ? WHERE id = ?", (1 if activo else 0, carpeta_id)
    )
    conn.commit()
    conn.close()


# ---------- Estado del proceso ----------

def get_estado_proceso():
    conn = _conn()
    row = conn.execute("SELECT * FROM estado_proceso WHERE id = 1").fetchone()
    conn.close()
    return dict(row) if row else None


def set_estado_proceso(corriendo, carpeta_actual=None, archivo_actual=None):
    conn = _conn()
    if corriendo:
        conn.execute(
            """UPDATE estado_proceso
               SET corriendo = 1, iniciado_en = ?, carpeta_actual = ?, archivo_actual = ?
               WHERE id = 1""",
            (datetime.now().strftime("%d-%m-%Y %H:%M:%S"), carpeta_actual, archivo_actual),
        )
    else:
        conn.execute(
            """UPDATE estado_proceso
               SET corriendo = 0, carpeta_actual = NULL, archivo_actual = NULL
               WHERE id = 1"""
        )
    conn.commit()
    conn.close()


def actualizar_progreso_actual(carpeta_actual=None, archivo_actual=None):
    conn = _conn()
    conn.execute(
        "UPDATE estado_proceso SET carpeta_actual = ?, archivo_actual = ? WHERE id = 1",
        (carpeta_actual, archivo_actual),
    )
    conn.commit()
    conn.close()


# ---------- Usuarios ----------

def hay_usuarios():
    conn = _conn()
    n = conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
    conn.close()
    return n > 0


def crear_usuario(username, password_hash, nombre_completo=""):
    conn = _conn()
    conn.execute(
        """INSERT INTO usuarios (username, nombre_completo, password_hash, creado_en)
           VALUES (?, ?, ?, ?)""",
        (username, nombre_completo, password_hash, datetime.now().strftime("%d-%m-%Y %H:%M:%S")),
    )
    conn.commit()
    conn.close()


def obtener_usuario_por_username(username):
    conn = _conn()
    row = conn.execute("SELECT * FROM usuarios WHERE username = ?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def obtener_usuario_por_id(user_id):
    conn = _conn()
    row = conn.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def listar_usuarios():
    conn = _conn()
    rows = conn.execute("SELECT id, username, nombre_completo, creado_en FROM usuarios ORDER BY username").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def eliminar_usuario(user_id):
    conn = _conn()
    conn.execute("DELETE FROM usuarios WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
