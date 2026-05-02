import os
import uuid

from flask import (
    Flask,
    Response,
    g,
    jsonify,
    render_template,
    request,
    send_from_directory,
)
from jinja2 import TemplateNotFound
from logger import get_logger
from weather import get_weather

# Explicit folders ensure Flask looks in /app/templates and /app/static
app = Flask(__name__, template_folder="templates", static_folder="static")
logger = get_logger("flask")


def safe_render(name: str) -> str | Response:
    """Render a template by name, returning a 200 error page if not found."""
    try:
        return render_template(name)
    except TemplateNotFound:
        logger.error("Template not found", extra={"template": name})
        return Response(
            f"<h1>Missing template: {name}</h1>", status=200, mimetype="text/html"
        )


# ---------------- UI ----------------
@app.route("/")
def index():
    return safe_render("index.html")


@app.route("/about_me")
def about_me():
    return safe_render("about_me.html")


@app.route("/resume")
def resume():
    return safe_render("resume.html")


@app.route("/weather_app")
def weather_app():
    return safe_render("weather_app.html")


# ------------- health / metrics -------------
@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"}), 200


@app.route("/metrics")
def metrics():
    return Response("app_up 1\n", status=200, mimetype="text/plain")


# --------------- API ----------------
@app.route("/weather", methods=["POST"])
def weather():
    data = request.get_json(silent=True) or {}
    location = data.get("location")
    api_key = data.get("api_key")
    mode = data.get("mode", "city")
    if not location or not api_key:
        return jsonify({"error": "Location and API key are required."}), 400
    weather_data = get_weather(location, api_key, mode)
    return jsonify(weather_data), 200


# -------------- static --------------
@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon",
    )


# ----------- request / response logging -----------
@app.before_request
def log_request():
    g.request_id = str(uuid.uuid4())
    path = request.path
    method = request.method

    if path in ("/", "/about_me", "/resume", "/weather_app"):
        msg = f"{path} requested"
    elif path in ("/favicon.ico", "/healthz", "/metrics"):
        msg = f"Utility endpoint requested: {path}"
    elif path.startswith("/static/"):
        msg = f"Static asset requested: {path}"
    elif path == "/weather" and method == "POST":
        msg = "Weather API request received"
    else:
        msg = f"Unhandled request path: {path}"

    logger.info(
        msg,
        extra={
            "event": "request_received",
            "request_id": g.request_id,
            "method": method,
            "path": path,
            "remote_addr": request.remote_addr,
        },
    )


@app.after_request
def log_response(response):
    req_id = getattr(g, "request_id", None) or str(uuid.uuid4())
    response.headers["X-Request-ID"] = req_id
    logger.info(
        "response sent",
        extra={
            "event": "response_sent",
            "request_id": req_id,
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
        },
    )
    return response


# Gunicorn serves this app — see Dockerfile CMD.
# Run locally with: gunicorn --bind 0.0.0.0:5000 main:app
