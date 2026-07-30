from app import create_app, socketio

app = create_app()

if __name__ == "__main__":
    # allow_unsafe_werkzeug=True: aceptable para uso interno de baja concurrencia.
    # Si en el futuro hace falta más carga o TLS, poner esto detrás de nginx/traefik
    # y considerar un servidor WSGI/ASGI dedicado (gunicorn+eventlet, uvicorn, etc).
    socketio.run(app, host="0.0.0.0", port=5000, allow_unsafe_werkzeug=True)
