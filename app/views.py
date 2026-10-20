"""HTML pages plus the two PWA files that must be served from the site root."""
from flask import Blueprint, current_app, render_template, send_from_directory
from flask_login import login_required

bp = Blueprint("views", __name__)


@bp.get("/")
@login_required
def index():
    return render_template("index.html")


@bp.get("/sw.js")
def service_worker():
    # Served from "/" (not /static) so the service worker can control the whole app.
    resp = send_from_directory(current_app.static_folder, "sw.js", mimetype="application/javascript")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@bp.get("/manifest.webmanifest")
def manifest():
    return send_from_directory(
        current_app.static_folder, "manifest.webmanifest", mimetype="application/manifest+json"
    )


@bp.get("/healthz")
def healthz():
    return {"status": "ok"}
