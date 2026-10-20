"""Register / login / logout (session cookies via Flask-Login)."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required, login_user, logout_user

from . import db
from .models import User

bp = Blueprint("auth", __name__)

MIN_PASSWORD_LEN = 8


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if "@" not in email:
            flash("Enter a valid email.")
        elif len(password) < MIN_PASSWORD_LEN:
            flash(f"Password must be at least {MIN_PASSWORD_LEN} characters.")
        elif User.query.filter_by(email=email).first():
            flash("That email is already registered.")
        else:
            user = User(email=email)
            user.set_password(password)  # stored hashed, never as plain text
            db.session.add(user)
            db.session.commit()
            login_user(user, remember=True)
            return redirect(url_for("views.index"))

    return render_template("register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            return redirect(url_for("views.index"))
        flash("Wrong email or password.")
    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
