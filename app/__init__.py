"""Application factory."""
import os

from flask import Flask, jsonify, request, redirect, url_for
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

from .config import Config

db = SQLAlchemy()
login_manager = LoginManager()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    if (
        os.environ.get("FLASK_ENV") == "production"
        and app.config["SECRET_KEY"] == "dev-only-change-me"
    ):
        raise RuntimeError("Set the SECRET_KEY environment variable in production.")

    db.init_app(app)
    login_manager.init_app(app)

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        # API callers get JSON; browsers get sent to the login page.
        if request.path.startswith("/api/"):
            return jsonify(error="login required"), 401
        return redirect(url_for("auth.login"))

    from .auth import bp as auth_bp
    from .api import bp as api_bp
    from .views import bp as views_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(views_bp)

    with app.app_context():
        # Fine for a skeleton. Switch to migrations (Flask-Migrate) once the
        # schema starts changing with real data in it.
        db.create_all()

    return app
