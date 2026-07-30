# PALTA — Drive → YouTube

Descarga videos desde carpetas configurables de Google Drive y los sube automáticamente
a un canal de YouTube, con panel web para monitorear progreso, historial y credenciales.

## Qué cambió respecto a la versión original

- **Interfaz web nueva**: panel con estado del proceso, progreso en vivo (WebSocket),
  historial de subidas, gestión de carpetas y gestión de credenciales.
- **Carpetas configurables** desde la web (antes estaban hardcodeadas en `routes.py`), guardadas en SQLite.
- **OAuth de YouTube migrado a flujo web**: la versión original usaba `flow.run_local_server()`,
  que abre un navegador local y **no funciona dentro de un contenedor**. Ahora se autoriza
  el canal desde `/credenciales`, con redirect + callback manejados por Flask.
- **Un solo proceso a la vez**: un lock en memoria evita ejecuciones simultáneas; el botón
  "Procesar ahora" se deshabilita mientras hay un proceso corriendo.
- **Bugs corregidos**:
  - `listar_archivos()` tenía una firma inconsistente entre `uploader.py` y `drive_service.py`.
  - `mailer_service.py` no enviaba contraseña al hacer login SMTP.
  - `db_service.py` usaba una ruta de base de datos fija en vez de la de `config.py`.

## Estructura

```
palta/
  app/
    core/uploader.py        → orquesta descarga + subida + progreso
    services/                → drive, youtube, db, mailer
    templates/, static/      → interfaz web
    routes.py, config.py, __init__.py
  main.py
  requirements.txt
  Dockerfile
  docker-compose.yml
  .env.example
```

## Credenciales necesarias

Se cargan **desde la web**, en `/credenciales` (no hace falta acceso al servidor):

1. **Cuenta de servicio de Google Drive** (JSON) — con permiso de lectura sobre las
   carpetas que vas a monitorear (compartí cada carpeta con el `client_email` de esa cuenta).
2. **Client secret de YouTube (OAuth, tipo "Aplicación web")** — descargado desde
   [Google Cloud Console](https://console.cloud.google.com/apis/credentials).
   En **Authorized redirect URIs** agregá: `http://<host-del-servidor>:5000/credenciales/youtube/callback`
3. Con el client secret cargado, hacé clic en **"Autorizar canal de YouTube"** e iniciá
   sesión con la cuenta dueña del canal destino.

Todo se guarda en `instance/`, que está montado como volumen persistente.

## Variables de entorno

Copiá `.env.example` a `.env` y completá al menos `SECRET_KEY` y, si querés notificaciones
por mail, `EMAIL_PASSWORD` (contraseña de aplicación de Gmail, no la contraseña normal).

```bash
cp .env.example .env
```

## Levantar con Docker

```bash
docker compose up -d --build
```

La app queda disponible en `http://<ip-del-servidor>:5000`.

Para ver logs del contenedor:
```bash
docker compose logs -f palta
```

## Primer uso

1. Entrá a `http://<servidor>:5000/credenciales` y cargá las 3 credenciales.
2. Andá a `/carpetas` y agregá las carpetas de Drive a monitorear (nombre + ID de carpeta,
   el ID es la parte de la URL de Drive después de `/folders/`).
3. Volvé al panel principal y usá **"Procesar ahora"** para disparar el proceso manualmente.
   El progreso de descarga/subida se ve en vivo, y el archivo local se borra automáticamente
   después de subirse a YouTube.

## Notas para producción interna

- El servidor de desarrollo de Flask/SocketIO alcanza para uso interno de una organización
  con pocos usuarios simultáneos. Si en el futuro necesitás más carga o TLS, se puede poner
  detrás de un reverse proxy (nginx/traefik) sin cambiar el código.
- No hay autenticación de usuarios en esta versión (decisión explícita: la app queda
  accesible solo dentro de la red interna). Si más adelante hace falta login, la estructura
  ya está lista para agregar Flask-Login sin reescribir el resto.
- El procesamiento es secuencial (una carpeta y un archivo a la vez) para evitar saturar
  la cuota de subida de YouTube y simplificar el manejo de errores.
