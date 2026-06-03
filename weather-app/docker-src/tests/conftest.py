import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("PLAYGROUND_SECRET", "test-secret-unit")
os.environ.setdefault("PLAYGROUND_ADMIN_KEY", "test-admin-key-unit")

import pytest  # noqa: E402


@pytest.fixture
def flask_app():
    from flask import Flask

    import playground

    app = Flask(
        __name__,
        template_folder=str(Path(__file__).resolve().parent.parent / "templates"),
    )
    app.config["SECRET_KEY"] = "test-flask-secret-key"
    app.config["TESTING"] = True
    app.register_blueprint(playground.playground_bp)

    # Stub routes required by shared navbar in templates
    for endpoint in ("about_me", "index", "resume", "weather_app"):
        app.add_url_rule(f"/{endpoint}", endpoint=endpoint, view_func=lambda: ("", 200))

    return app


@pytest.fixture
def flask_client(flask_app):
    with flask_app.test_client() as client:
        yield client
