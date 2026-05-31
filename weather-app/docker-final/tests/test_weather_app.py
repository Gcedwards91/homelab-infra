"""
Integration tests - Section 9: Playground (server-side, non-destructive).

Mirrors TESTING_CHECKLIST.md sections 9.2, 9.3, and 9.10 server-side items.
The toggle/stress lifecycle items (9.4, 9.5, 9.6) stop containers and wait out
alert windows; those live in test_alerting.py behind the 'destructive' marker.

Prerequisites (automated by CI - or run locally after stack is up):
    cd weather-app/docker-final
    docker compose up -d && sleep 30
    pip install -r requirements-dev.txt
    pytest tests/test_weather_app.py -v

Override the target base URL with the BASE_URL env var:
    BASE_URL=http://192.168.1.50 pytest tests/test_weather_app.py -v

Tests that need the rolling passphrase read PLAYGROUND_ADMIN_KEY from the
generated .env (weather-app/docker-final/.env) and ask the admin endpoint for
the current passphrase rather than re-deriving it. If the key is unavailable or
still the placeholder, those tests skip.

The file name embeds the weather-app service token (path 'test_weather_app'
matches the 'weather_app' term) so the CI self-healing loop applies the
svc:weather-app label on failure (CI_LOOP_DESIGN.md Part 4).
"""

import os
import time
from pathlib import Path

import pytest
import requests as http

BASE_URL = os.environ.get("BASE_URL", "http://localhost")

_PLACEHOLDER = "change-me-generate-a-real-secret"


def _load_env() -> dict:
    """Parse the generated .env next to docker-compose.yml into a dict.

    Returns an empty dict if the file is absent (tests that depend on values
    will skip rather than fail).
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    values: dict = {}
    if not env_path.is_file():
        return values
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip()
    return values


_ENV = _load_env()
_ADMIN_KEY = _ENV.get("PLAYGROUND_ADMIN_KEY", "")
_admin_key_usable = bool(_ADMIN_KEY) and _ADMIN_KEY != _PLACEHOLDER


def _current_passphrase() -> str:
    """Fetch the current passphrase from the admin endpoint."""
    resp = http.get(
        f"{BASE_URL}/playground/passphrase",
        headers={"Authorization": f"Bearer {_ADMIN_KEY}"},
        timeout=10,
    )
    assert resp.status_code == 200, (
        f"admin passphrase endpoint returned HTTP {resp.status_code} with the "
        f"configured PLAYGROUND_ADMIN_KEY"
    )
    return resp.json()["current"]


class TestWeatherAppPlaygroundAuth:

    # --- 9.2 admin passphrase endpoint ---

    def test_passphrase_endpoint_requires_authorization(self):
        resp = http.get(f"{BASE_URL}/playground/passphrase", timeout=10)
        assert resp.status_code == 401, (
            f"passphrase endpoint returned HTTP {resp.status_code} with no "
            f"Authorization header, expected 401"
        )

    def test_passphrase_endpoint_rejects_wrong_bearer(self):
        resp = http.get(
            f"{BASE_URL}/playground/passphrase",
            headers={"Authorization": "Bearer this-is-not-the-admin-key"},
            timeout=10,
        )
        assert resp.status_code == 401, (
            f"passphrase endpoint returned HTTP {resp.status_code} with a wrong "
            f"bearer token, expected 401"
        )

    def test_passphrase_endpoint_returns_expected_keys(self):
        if not _admin_key_usable:
            pytest.skip("PLAYGROUND_ADMIN_KEY not available from .env")
        resp = http.get(
            f"{BASE_URL}/playground/passphrase",
            headers={"Authorization": f"Bearer {_ADMIN_KEY}"},
            timeout=10,
        )
        assert resp.status_code == 200, (
            f"passphrase endpoint returned HTTP {resp.status_code} with the "
            f"correct bearer token"
        )
        data = resp.json()
        for key in ("current", "seconds_until_rotation", "next"):
            assert key in data, f"passphrase response missing key {key!r}: {data}"

    # --- 9.2 login gate ---

    def test_playground_redirects_to_login_without_session(self):
        resp = http.get(f"{BASE_URL}/playground", timeout=10, allow_redirects=False)
        assert resp.status_code == 302, (
            f"/playground returned HTTP {resp.status_code} without a session, "
            f"expected 302"
        )
        assert "/playground/login" in resp.headers.get(
            "Location", ""
        ), f"/playground redirect target is {resp.headers.get('Location')!r}"

    def test_login_wrong_passphrase_returns_401_with_error_note(self):
        resp = http.post(
            f"{BASE_URL}/playground/login",
            data={"password": "definitely-not-the-passphrase"},
            timeout=10,
            allow_redirects=False,
        )
        assert (
            resp.status_code == 401
        ), f"wrong passphrase returned HTTP {resp.status_code}, expected 401"
        assert "note--error" in resp.text, (
            "login page did not re-render with the .note--error callout on a "
            "failed attempt"
        )

    def test_login_correct_passphrase_sets_session_and_redirects(self):
        if not _admin_key_usable:
            pytest.skip("PLAYGROUND_ADMIN_KEY not available from .env")
        current = _current_passphrase()
        session = http.Session()
        resp = session.post(
            f"{BASE_URL}/playground/login",
            data={"password": current},
            timeout=10,
            allow_redirects=False,
        )
        assert (
            resp.status_code == 302
        ), f"correct passphrase returned HTTP {resp.status_code}, expected 302"
        assert "/playground" in resp.headers.get(
            "Location", ""
        ), f"login redirect target is {resp.headers.get('Location')!r}"
        assert session.cookies, "no session cookie was set after a successful login"
        # The session should now satisfy the API auth gate.
        status = session.get(f"{BASE_URL}/api/playground/status", timeout=10)
        assert status.status_code == 200, (
            f"/api/playground/status returned HTTP {status.status_code} with a "
            f"freshly authenticated session, expected 200"
        )

    # --- 9.3 unauthenticated API access ---

    @pytest.mark.parametrize(
        "method,path",
        [
            ("get", "/api/playground/status"),
            ("post", "/api/playground/toggle"),
            ("post", "/api/playground/stress"),
            ("post", "/api/playground/stop_stress"),
        ],
    )
    def test_api_requires_session(self, method, path):
        resp = http.request(method, f"{BASE_URL}{path}", timeout=10)
        assert resp.status_code == 403, (
            f"{method.upper()} {path} returned HTTP {resp.status_code} without a "
            f"session, expected 403"
        )

    # --- 9.10 security verification ---

    def test_toggle_other_container_rejected_without_session(self):
        """A toggle request naming a different container is rejected at the auth
        gate. With a session the endpoint ignores the body and only ever targets
        the hardcoded demo-container (verified in test_alerting.py)."""
        resp = http.post(
            f"{BASE_URL}/api/playground/toggle",
            json={"container": "prometheus"},
            timeout=10,
        )
        assert resp.status_code == 403, (
            f"toggle naming 'prometheus' returned HTTP {resp.status_code} without "
            f"a session, expected 403"
        )

    def test_login_passphrase_not_written_to_logs(self, docker_client):
        """The login route must never log request.form (CLAUDE.md playground
        constraint). Post a unique sentinel and confirm it never reaches the
        weather-app logs."""
        sentinel = "sentinel-passphrase-must-never-be-logged-9f3a2c"
        http.post(
            f"{BASE_URL}/playground/login",
            data={"password": sentinel},
            timeout=10,
            allow_redirects=False,
        )
        time.sleep(1)  # allow the request/response log lines to flush
        container = docker_client.containers.get("weather-app")
        logs = container.logs(tail=300).decode("utf-8", errors="replace")
        assert sentinel not in logs, (
            "the submitted passphrase appeared in weather-app logs - the login "
            "route must never log request.form"
        )
