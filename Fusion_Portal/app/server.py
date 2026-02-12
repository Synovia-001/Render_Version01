from flask import Flask, redirect, request
from flask_login import current_user

from .auth import auth_bp, login_manager
from .config import load_settings

def create_server() -> Flask:
    settings = load_settings()
    server = Flask(__name__, template_folder="templates")
    server.secret_key = settings.secret_key

    login_manager.init_app(server)
    server.register_blueprint(auth_bp)

    @server.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @server.before_request
    def require_login():
        path = request.path or ""
        allow_prefixes = ("/login", "/logout", "/healthz", "/assets", "/favicon.ico")
        if path.startswith(allow_prefixes):
            return None

        dash_prefixes = ("/_dash", "/_favicon", "/_reload-hash")
        if path.startswith(dash_prefixes) or path == "/":
            if not current_user.is_authenticated:
                return redirect("/login")
        return None

    return server
