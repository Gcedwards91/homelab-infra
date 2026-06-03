import os
import time
import playground

FIXED_SECRET = os.environ["PLAYGROUND_SECRET"]
WINDOW_SECONDS = playground.WINDOW_SECONDS
GRACE_SECONDS = playground.GRACE_SECONDS
SESSION_IDLE_LIMIT = playground.SESSION_IDLE_LIMIT

_WINDOW_N = 5
_MID_WINDOW = WINDOW_SECONDS * _WINDOW_N + WINDOW_SECONDS // 2
_IN_GRACE = WINDOW_SECONDS * _WINDOW_N + GRACE_SECONDS // 2
_AT_GRACE_BOUNDARY = WINDOW_SECONDS * _WINDOW_N + GRACE_SECONDS


class TestWeatherAppPlaygroundAuth:
    def test_weather_app_playground_derive_is_deterministic(self):
        a = playground._derive(FIXED_SECRET.encode(), _WINDOW_N)
        b = playground._derive(FIXED_SECRET.encode(), _WINDOW_N)
        assert a == b
        assert len(a) == 14

    def test_weather_app_playground_derive_differs_per_window(self):
        a = playground._derive(FIXED_SECRET.encode(), _WINDOW_N)
        b = playground._derive(FIXED_SECRET.encode(), _WINDOW_N + 1)
        assert a != b

    def test_weather_app_playground_one_passphrase_mid_window(self, monkeypatch):
        monkeypatch.setattr(playground.time, "time", lambda: _MID_WINDOW)
        result = playground._valid_passphrases()
        assert len(result) == 1
        assert result[0] == playground._derive(FIXED_SECRET.encode(), _WINDOW_N)

    def test_weather_app_playground_two_passphrases_in_grace(self, monkeypatch):
        monkeypatch.setattr(playground.time, "time", lambda: _IN_GRACE)
        result = playground._valid_passphrases()
        assert len(result) == 2
        assert playground._derive(FIXED_SECRET.encode(), _WINDOW_N) in result
        assert playground._derive(FIXED_SECRET.encode(), _WINDOW_N - 1) in result

    def test_weather_app_playground_grace_boundary_exact(self, monkeypatch):
        monkeypatch.setattr(playground.time, "time", lambda: _AT_GRACE_BOUNDARY)
        result = playground._valid_passphrases()
        assert len(result) == 1

    def test_weather_app_playground_passphrase_info_math(self, monkeypatch):
        monkeypatch.setattr(playground.time, "time", lambda: _MID_WINDOW)
        info = playground._passphrase_info()
        expected_seconds = WINDOW_SECONDS - (int(_MID_WINDOW) % WINDOW_SECONDS)
        assert info["seconds_until_rotation"] == expected_seconds
        assert info["next"] != info["current"]
        assert info["current"] == playground._derive(FIXED_SECRET.encode(), _WINDOW_N)

    def test_weather_app_playground_session_valid_when_recent(self, flask_app):
        with flask_app.test_request_context():
            from flask import session

            session["playground_auth"] = True
            session["last_active"] = time.time() - 100
            assert playground._session_valid() is True

    def test_weather_app_playground_session_expires_after_idle(self, flask_app):
        with flask_app.test_request_context():
            from flask import session

            session["playground_auth"] = True
            session["last_active"] = time.time() - (SESSION_IDLE_LIMIT + 1)
            assert playground._session_valid() is False

    def test_weather_app_playground_session_invalid_without_auth_flag(self, flask_app):
        with flask_app.test_request_context():
            from flask import session

            session["last_active"] = time.time() - 100
            assert playground._session_valid() is False


class TestWeatherAppPlaygroundLogin:
    def test_weather_app_playground_login_accepts_current_passphrase(
        self, flask_client, monkeypatch
    ):
        monkeypatch.setattr(playground.time, "time", lambda: _MID_WINDOW)
        passphrase = playground._derive(FIXED_SECRET.encode(), _WINDOW_N)
        resp = flask_client.post("/playground/login", data={"password": passphrase})
        assert resp.status_code == 302
        with flask_client.session_transaction() as sess:
            assert sess.get("playground_auth") is True

    def test_weather_app_playground_login_rejects_wrong_passphrase(
        self, flask_client, monkeypatch
    ):
        monkeypatch.setattr(playground.time, "time", lambda: _MID_WINDOW)
        wrong = "definitely-wrong-passphrase"
        resp = flask_client.post("/playground/login", data={"password": wrong})
        assert resp.status_code == 401
        assert wrong not in resp.get_data(as_text=True)
        with flask_client.session_transaction() as sess:
            assert not sess.get("playground_auth")

    def test_weather_app_playground_login_accepts_grace_passphrase(
        self, flask_client, monkeypatch
    ):
        monkeypatch.setattr(playground.time, "time", lambda: _IN_GRACE)
        prev_passphrase = playground._derive(FIXED_SECRET.encode(), _WINDOW_N - 1)
        resp = flask_client.post(
            "/playground/login", data={"password": prev_passphrase}
        )
        assert resp.status_code == 302
        with flask_client.session_transaction() as sess:
            assert sess.get("playground_auth") is True
