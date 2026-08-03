import os
from flask import Flask
from flask_socketio import SocketIO
from flask_login import LoginManager

socketio = SocketIO(cors_allowed_origins="*", async_mode="threading")
login_manager = LoginManager()
login_manager.login_view = "main.login"
login_manager.login_message = "Iniciá sesión para continuar."


def create_app():
    app = Flask(__name__)
    app.config.from_object("app.config.Config")

    os.makedirs(app.config["INSTANCE_PATH"], exist_ok=True)
    os.makedirs(app.config["DOWNLOAD_PATH"], exist_ok=True)
    os.makedirs(app.config["LOG_PATH"], exist_ok=True)

    socketio.init_app(app)
    login_manager.init_app(app)

    from app.services.db_service import init_db, set_estado_proceso
    with app.app_context():
        init_db(app.config["DATABASE_PATH"])
        # Si el contenedor se cerro de forma abrupta a mitad de un proceso
        # (docker restart, corte de luz, OOM kill), la fila estado_proceso
        # puede haber quedado con corriendo=1 para siempre. Al arrancar de
        # cero no hay nada corriendo de verdad, asi que se resetea siempre.
        set_estado_proceso(False)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        with app.app_context():
            return User.get(user_id)

    from app.routes import bp as main_bp
    app.register_blueprint(main_bp)

    return app
