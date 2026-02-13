from flask import Blueprint, redirect, render_template, request, url_for, flash
from flask_login import LoginManager, login_user, logout_user, current_user

from .data_access import fetch_user_by_username_or_email, fetch_user_by_id, update_last_login
from .security import verify_password

auth_bp = Blueprint("auth", __name__)

login_manager = LoginManager()
login_manager.login_view = "auth.login"

@login_manager.user_loader
def load_user(user_id: str):
    try:
        return fetch_user_by_id(int(user_id))
    except Exception:
        return None

@auth_bp.get("/login")
def login():
    if current_user.is_authenticated:
        return redirect("/")
    return render_template("login.html")

@auth_bp.post("/login")
def login_post():
    login_value = request.form.get("login", "").strip()
    password = request.form.get("password", "")

    if not login_value or not password:
        flash("Please enter your username/email and password.", "danger")
        return redirect(url_for("auth.login"))

    try:
        rec = fetch_user_by_username_or_email(login_value)
    except Exception:
        flash("Login service unavailable (database connection failed).", "danger")
        return redirect(url_for("auth.login"))

    if not rec:
        flash("Invalid credentials.", "danger")
        return redirect(url_for("auth.login"))

    if not rec.get("is_active"):
        flash("Account is inactive. Contact an administrator.", "danger")
        return redirect(url_for("auth.login"))

    try:
        ok = verify_password(password, rec["password_hash"])
    except Exception:
        flash("Password verification service unavailable.", "danger")
        return redirect(url_for("auth.login"))

    if not ok:
        flash("Invalid credentials.", "danger")
        return redirect(url_for("auth.login"))

    user = fetch_user_by_id(rec["user_id"])
    login_user(user)
    update_last_login(rec["user_id"])
    return redirect("/")

@auth_bp.get("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
