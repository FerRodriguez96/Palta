from flask_login import UserMixin
from app.services import db_service


class User(UserMixin):
    def __init__(self, row):
        self.id = str(row["id"])
        self.username = row["username"]
        self.nombre_completo = row["nombre_completo"] or row["username"]
        self.is_admin = bool(row["es_admin"])

    @staticmethod
    def get(user_id):
        row = db_service.obtener_usuario_por_id(user_id)
        return User(row) if row else None

    @staticmethod
    def get_by_username(username):
        row = db_service.obtener_usuario_por_username(username)
        return User(row) if row else None
