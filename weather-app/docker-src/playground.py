import base64
import hashlib
import hmac
import os
import time
from functools import wraps

import docker
import requests as http
from flask import (
    Blueprint,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from logger import get_logger

playground_bp = Blueprint("playground", __name__)
logger = get_logger("playground")

WINDOW_SECONDS = 4 * 3600  # 4-hour rotation
GRACE_SECONDS = 300  # 5-minute overlap at window boundaries
DEMO_CONTAINER = "demo-container"
DEMO_STRESS_URL = "http://demo-container:8080/stress"
DEMO_STATUS_URL = "http://demo-container:8080/stress_status"
SESSION_IDLE_LIMIT = 1800  # 30 minutes


# ---------------------------------------------------------------------------
# Passphrase helpers
# ---------------------------------------------------------------------------


def _derive(secret: bytes, window_id: int) -> str:
    digest = hmac.new(secret, str(window_id).encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest)[:14].decode()


def _valid_passphrases() -> list:
    secret = os.environ["PLAYGROUND_SECRET"].encode()
    now = time.time()
    cur = int(now // WINDOW_SECONDS)
    passes = [_derive(secret, cur)]
    if (now - cur * WINDOW_SECONDS) < GRACE_SECONDS:
        passes.append(_derive(secret, cur - 1))
    return passes


def _passphrase_info() -> dict:
    secret = os.environ["PLAYGROUND_SECRET"].encode()
    now = time.time()
    cur = int(now // WINDOW_SECONDS)
    next_rotation = (cur + 1) * WINDOW_SECONDS
    return {
        "current": _derive(secret, cur),
        "seconds_until_rotation": int(next_rotation - now),
        "next": _derive(secret, cur + 1),
    }


# ---------------------------------------------------------------------------
# Auth decorators
# ---------------------------------------------------------------------------


def _session_valid() -> bool:
    return bool(session.get("playground_auth")) and (
        time.time() - session.get("last_active", 0) <= SESSION_IDLE_LIMIT
    )


def require_auth(f):
    """For API routes — returns 403 on failure."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if not _session_valid():
            session.clear()
            abort(403)
        session["last_active"] = time.time()
        return f(*args, **kwargs)

    return decorated


def require_auth_redirect(f):
    """For page routes — redirects to login on failure."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if not _session_valid():
            session.clear()
            return redirect(url_for("playground.login"))
        session["last_active"] = time.time()
        return f(*args, **kwargs)

    return decorated


# ---------------------------------------------------------------------------
# Docker helper
# ---------------------------------------------------------------------------


def _container_state() -> str:
    """Returns 'running', 'stopped', or 'not_found'."""
    try:
        client = docker.from_env()
        container = client.containers.get(DEMO_CONTAINER)
        return "running" if container.status == "running" else "stopped"
    except docker.errors.NotFound:
        return "not_found"
    except Exception as exc:
        logger.error("docker state check failed", extra={"error": str(exc)})
        return "stopped"


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------


@playground_bp.route("/playground")
@require_auth_redirect
def index():
    state = _container_state()
    return render_template("playground.html", container_state=state)


@playground_bp.route("/playground/login", methods=["GET", "POST"])
def login():
    if request.method == "GET" and _session_valid():
        return redirect(url_for("playground.index"))

    if request.method == "POST":
        # Never log request.form — passphrase must not appear in logs
        password = request.form.get("password", "")
        try:
            valid = _valid_passphrases()
        except KeyError:
            logger.error("PLAYGROUND_SECRET env var not set")
            abort(503)
        if any(hmac.compare_digest(password, p) for p in valid):
            session.clear()
            session["playground_auth"] = True
            session["last_active"] = time.time()
            return redirect(url_for("playground.index"))
        return render_template("playground_login.html", error=True), 401

    return render_template("playground_login.html", error=False)


@playground_bp.route("/playground/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("playground.login"))


# ---------------------------------------------------------------------------
# Admin endpoint
# ---------------------------------------------------------------------------


@playground_bp.route("/playground/passphrase")
def passphrase():
    admin_key = os.environ.get("PLAYGROUND_ADMIN_KEY")
    if not admin_key:
        abort(503)
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer ") or not hmac.compare_digest(
        auth_header[7:], admin_key
    ):
        abort(401)
    try:
        return jsonify(_passphrase_info())
    except KeyError:
        abort(503)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


@playground_bp.route("/api/playground/status")
@require_auth
def api_status():
    state = _container_state()
    stress_active = False
    if state == "running":
        try:
            resp = http.get(DEMO_STATUS_URL, timeout=2)
            if resp.ok:
                stress_active = resp.json().get("active", False)
        except Exception:
            pass
    return jsonify({"container": state, "stress_active": stress_active})


@playground_bp.route("/api/playground/toggle", methods=["POST"])
@require_auth
def api_toggle():
    try:
        client = docker.from_env()
        container = client.containers.get(DEMO_CONTAINER)
        if container.status == "running":
            container.stop()
            logger.info("demo-container stopped", extra={"event": "playground_toggle"})
            return jsonify({"status": "stopped"})
        else:
            container.start()
            logger.info("demo-container started", extra={"event": "playground_toggle"})
            return jsonify({"status": "started"})
    except docker.errors.NotFound:
        return jsonify({"error": "not_found"}), 404
    except Exception as exc:
        logger.error("toggle failed", extra={"error": str(exc)})
        return jsonify({"error": "toggle_failed"}), 500


@playground_bp.route("/api/playground/stress", methods=["POST"])
@require_auth
def api_stress():
    try:
        resp = http.post(DEMO_STRESS_URL, timeout=5)
        return jsonify({"status": resp.json().get("status", "stress started")}), 200
    except http.exceptions.ConnectionError:
        return jsonify({"error": "unreachable"}), 502
    except Exception as exc:
        logger.error("stress request failed", extra={"error": str(exc)})
        return jsonify({"error": "stress_failed"}), 500


@playground_bp.route("/api/playground/stop_stress", methods=["POST"])
@require_auth
def api_stop_stress():
    try:
        resp = http.post("http://demo-container:8080/stop_stress", timeout=5)
        return jsonify({"status": resp.json().get("status", "stopped")}), 200
    except http.exceptions.ConnectionError:
        return jsonify({"error": "unreachable"}), 502
    except Exception as exc:
        logger.error("stop_stress request failed", extra={"error": str(exc)})
        return jsonify({"error": "stop_stress_failed"}), 500
