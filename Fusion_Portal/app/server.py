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

    # Redirect /module/Core (no slash) -> /module/Core/
    @server.get("/module/Core")
    def core_redirect():
        return redirect("/module/Core/")

    @server.before_request
    def require_login():
        path = request.path or ""

        # Public endpoints
        allow_prefixes = ("/login", "/logout", "/healthz", "/assets", "/favicon.ico")
        if path.startswith(allow_prefixes):
            return None

        # Protect home + modules + dash internal endpoints anywhere
        needs_auth = (
            path == "/" or
            path.startswith("/module/") or
            "/_dash" in path or
            "/_favicon" in path or
            "/_reload-hash" in path
        )

        if needs_auth and not current_user.is_authenticated:
            return redirect("/login")

        return None

    return server
