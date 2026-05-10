import threading
import time

from flask import Flask, jsonify

app = Flask(__name__)

# Event semantics: is_set() == True means stress is currently running.
# set() to start, clear() to stop (or when the 30s deadline expires).
_stop_event = threading.Event()


def _burn(stop_event: threading.Event) -> None:
    deadline = time.time() + 30
    while stop_event.is_set() and time.time() < deadline:
        pass  # busy loop — intentional CPU burn
    stop_event.clear()


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"}), 200


@app.route("/stress", methods=["POST"])
def stress():
    if _stop_event.is_set():
        return jsonify({"status": "already running"}), 200
    _stop_event.set()
    threading.Thread(target=_burn, args=(_stop_event,), daemon=True).start()
    return jsonify({"status": "stress started"}), 200


@app.route("/stop_stress", methods=["POST"])
def stop_stress():
    _stop_event.clear()
    return jsonify({"status": "stopped"}), 200


@app.route("/stress_status")
def stress_status():
    return jsonify({"active": _stop_event.is_set()}), 200
