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

GRAFANA_URL = os.getenv("GRAFANA_URL")
ELASTIC_URL = os.getenv("ELASTIC_URL")


def _external_url(port: int, path: str = "") -> str:
    scheme = request.headers.get("X-Forwarded-Proto", request.scheme or "http")
    host_only = (request.headers.get("X-Forwarded-Host") or request.host).split(":")[0]
    return f"{scheme}://{host_only}:{port}{path}"


# --- helper to render safely ---
def safe_render(name):
    try:
        return render_template(name)
    except TemplateNotFound:
        logger.error("Template not found", extra={"template": name})
        return Response(f"<h1>Missing template: {name}</h1>", status=200, mimetype="text/html")


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


# ------------- health/metrics -------------
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


# ----------- logging ----------
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
            "headers": dict(request.headers),
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
            "status": getattr(response, "status_code", None),
        },
    )
    return response


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug_mode, host="0.0.0.0")
