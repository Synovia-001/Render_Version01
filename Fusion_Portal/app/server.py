from flask import Flask, redirect, request
from pathlib import Path
from flask_login import current_user

from .auth import auth_bp, login_manager
from .config import load_settings


def create_server() -> Flask:
    settings = load_settings()
    assets_dir = Path(__file__).resolve().parents[1] / "assets"

    server = Flask(
        __name__,
        template_folder="templates",
        static_folder=str(assets_dir),
        static_url_path="/assets",
    )

    server.secret_key = settings.secret_key

    login_manager.init_app(server)
    server.register_blueprint(auth_bp)

    @server.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @server.get("/module/Core")
    def core_redirect():
        return redirect("/module/Core/")

    @server.get("/module/EPOS")
    def epos_redirect():
        return redirect("/module/EPOS/")

    @server.get("/module/Fusion_Solas")
    def solas_redirect():
        return redirect("/module/Fusion_Solas/")

    @server.get("/module/Solas")
    @server.get("/module/Solas/")
    def solas_legacy_redirect():
        return redirect("/module/Fusion_Solas/")

    @server.before_request
    def require_login():
        path = request.path or ""

        allow_prefixes = (
            "/login",
            "/logout",
            "/healthz",
            "/assets",
            "/favicon.ico",
        )

        if path.startswith(allow_prefixes):
            return None

        needs_auth = (
            path == "/"
            or path.startswith("/module/")
            or "/_dash" in path
        )

        if needs_auth and not current_user.is_authenticated:
            return redirect("/login")

        return None

    return server
