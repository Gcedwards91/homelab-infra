import os
import uuid
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_from_directory,
    redirect,
    g,
)
from weather import get_weather
from logger import get_logger

app = Flask(__name__)
logger = get_logger("flask")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/about_me")
def about_me():
    return render_template("about_me.html")


@app.route("/resume")
def resume():
    return render_template("resume.html")


@app.route("/weather_app")
def weather_app():
    return render_template("weather_app.html")


@app.route("/grafana")
def grafana_redirect():
    return redirect("http://localhost:3000", code=302)


@app.route("/elastic")
def elastic_redirect():
    return redirect("http://localhost:5601", code=302)


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon",
    )


@app.route("/weather", methods=["POST"])
def weather():
    data = request.json
    location = data.get("location")
    api_key = data.get("api_key")
    mode = data.get("mode", "city")

    if not location or not api_key:
        return jsonify({"error": "Location and API key are required."}), 400

    weather_data = get_weather(location, api_key, mode)
    return jsonify(weather_data)


@app.before_request
def log_request():
    g.request_id = str(uuid.uuid4())

    path = request.path
    method = request.method

    if path == "/":
        message = "Homepage requested"
    elif path == "/about_me":
        message = "About Me page requested"
    elif path == "/resume":
        message = "Resume page requested"
    elif path == "/weather_app":
        message = "Weather App page requested"
    elif path == "/grafana":
        message = "Grafana redirect triggered"
    elif path == "/elastic":
        message = "Elastic redirect triggered"
    elif path == "/weather" and method == "POST":
        message = "Weather API request received"
    elif path.startswith("/static/"):
        message = f"Static asset requested: {path}"
    elif path == "/favicon.ico":
        message = "Favicon requested"
    else:
        message = f"Unhandled request path: {path}"

    logger.info(
        message,
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
    path = request.path
    method = request.method

    if path == "/":
        message = "Homepage response sent"
    elif path == "/about_me":
        message = "About Me page response sent"
    elif path == "/resume":
        message = "Resume page response sent"
    elif path == "/weather_app":
        message = "Weather App page response sent"
    elif path == "/grafana":
        message = "Grafana redirect response sent"
    elif path == "/elastic":
        message = "Elastic redirect response sent"
    elif path == "/weather" and method == "POST":
        message = "Weather API response sent"
    elif path.startswith("/static/"):
        message = f"Static asset response sent: {path}"
    elif path == "/favicon.ico":
        message = "Favicon response sent"
    else:
        message = f"Unhandled response path: {path}"

    logger.info(
        message,
        extra={
            "event": "response_sent",
            "request_id": getattr(g, "request_id", None),
            "method": method,
            "path": path,
            "status": response.status_code,
        },
    )

    response.headers["X-Request-ID"] = g.request_id
    return response


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug_mode, host="0.0.0.0")
