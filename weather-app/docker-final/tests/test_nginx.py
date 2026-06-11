"""
Integration tests - Section 6: Nginx Routing.

Mirrors TESTING_CHECKLIST.md section 6.

Prerequisites (automated by CI - or run locally after stack is up):
    cd weather-app/docker-final
    docker compose up -d && sleep 30
    pip install -r requirements-dev.txt
    pytest tests/test_nginx.py -v

Override the target base URL with the BASE_URL env var:
    BASE_URL=http://192.168.1.50 pytest tests/test_nginx.py -v

All assertions go through nginx on :80, so this exercises the reverse-proxy
location blocks rather than the upstreams directly. The class name embeds the
nginx service token (file path 'test_nginx' matches the reverse-proxy 'nginx'
term) so the CI self-healing loop applies the svc:nginx label on failure
(CI_LOOP_DESIGN.md Part 4).
"""

import os

import pytest
import requests as http

BASE_URL = os.environ.get("BASE_URL", "http://localhost")

# Upstream gateway failures nginx would surface if a backend is unreachable.
_GATEWAY_ERRORS = {502, 503, 504}


class TestNginxRouting:

    # --- Flask app routes ---

    def test_root_routes_to_flask(self):
        """/ proxies to the Flask app, which stamps X-Request-ID on every response."""
        resp = http.get(f"{BASE_URL}/", timeout=10)
        assert resp.status_code == 200, f"/ returned HTTP {resp.status_code}"
        assert "X-Request-ID" in resp.headers, (
            "/ response missing X-Request-ID header - root may not be routing to "
            "Flask (header is set by Flask after_request middleware)"
        )

    @pytest.mark.parametrize(
        "path", ["/about_me", "/resume", "/weather_app", "/healthz"]
    )
    def test_flask_page_routes(self, path):
        resp = http.get(f"{BASE_URL}{path}", timeout=10)
        assert resp.status_code == 200, f"{path} returned HTTP {resp.status_code}"
        assert (
            "X-Request-ID" in resp.headers
        ), f"{path} response missing X-Request-ID header - not routing to Flask"

    # --- Grafana and Prometheus sub-path routing ---

    def test_grafana_route(self):
        """/grafana/ proxies to Grafana (200, or 302 to a default dashboard)."""
        resp = http.get(f"{BASE_URL}/grafana/", timeout=10, allow_redirects=False)
        assert resp.status_code in (
            200,
            302,
        ), f"/grafana/ returned HTTP {resp.status_code}, expected 200 or 302"

    def test_prometheus_route(self):
        """/prometheus/ proxies to Prometheus (200, or a redirect to its UI path)."""
        resp = http.get(f"{BASE_URL}/prometheus/", timeout=10, allow_redirects=False)
        assert resp.status_code not in _GATEWAY_ERRORS, (
            f"/prometheus/ returned gateway error HTTP {resp.status_code} - "
            f"prometheus upstream may be down"
        )
        assert (
            resp.status_code < 400
        ), f"/prometheus/ returned HTTP {resp.status_code}, expected 2xx/3xx"

    # --- Playground routing ---

    def test_playground_redirects_to_login_without_session(self):
        """/playground proxies to Flask, which 302s to login when unauthenticated."""
        resp = http.get(f"{BASE_URL}/playground", timeout=10, allow_redirects=False)
        assert (
            resp.status_code == 302
        ), f"/playground returned HTTP {resp.status_code}, expected 302 to login"
        assert "/playground/login" in resp.headers.get("Location", ""), (
            f"/playground redirect target is {resp.headers.get('Location')!r}, "
            f"expected /playground/login"
        )

    def test_playground_api_returns_403_without_session(self):
        resp = http.get(f"{BASE_URL}/api/playground/status", timeout=10)
        assert resp.status_code == 403, (
            f"/api/playground/status returned HTTP {resp.status_code} without a "
            f"session, expected 403"
        )

    # --- Metrics endpoint is blocked to external clients ---

    def test_metrics_endpoint_blocked(self):
        """nginx returns 403 on /metrics to external clients (CLAUDE.md gotcha #3);
        Prometheus scrapes the container directly at :5000."""
        resp = http.get(f"{BASE_URL}/metrics", timeout=10)
        assert resp.status_code == 403, (
            f"/metrics returned HTTP {resp.status_code}, expected 403 "
            f"(external clients must be blocked)"
        )

    # --- No location block leaks an upstream gateway error ---

    @pytest.mark.parametrize(
        "path",
        ["/", "/about_me", "/resume", "/weather_app", "/healthz", "/prometheus/"],
    )
    def test_no_gateway_errors(self, path):
        resp = http.get(f"{BASE_URL}{path}", timeout=10, allow_redirects=False)
        assert resp.status_code not in _GATEWAY_ERRORS, (
            f"{path} returned gateway error HTTP {resp.status_code} - an upstream "
            f"is unreachable through nginx"
        )

    # --- Security headers added by nginx ---

    def test_security_headers_present(self):
        resp = http.get(f"{BASE_URL}/", timeout=10)
        assert (
            resp.headers.get("X-Content-Type-Options") == "nosniff"
        ), "X-Content-Type-Options header missing or not 'nosniff'"
        assert (
            resp.headers.get("X-Frame-Options") == "DENY"
        ), "X-Frame-Options header missing or not 'DENY'"

    def test_csp_allows_unsafe_eval_for_grafana_links(self):
        """The Grafana trace-link table panel uses new Function() internally, so the
        /grafana/ location's CSP must include 'unsafe-eval' in script-src
        (CLAUDE.md gotcha #15). The policy is scoped to that location only."""
        resp = http.get(f"{BASE_URL}/grafana/", timeout=10, allow_redirects=False)
        csp = resp.headers.get("Content-Security-Policy", "")
        assert csp, "Content-Security-Policy header is missing on /grafana/"
        assert "'unsafe-eval'" in csp, (
            "CSP on /grafana/ missing 'unsafe-eval' - Grafana trace-link table "
            "panel will throw EvalError (CLAUDE.md gotcha #15)"
        )

    def test_csp_strict_on_app_surface(self):
        """The Flask app surface must NOT carry 'unsafe-eval' - the loose policy
        is scoped to the /grafana/ and /prometheus/ location blocks only."""
        resp = http.get(f"{BASE_URL}/", timeout=10)
        csp = resp.headers.get("Content-Security-Policy", "")
        assert csp, "Content-Security-Policy header is missing on /"
        assert "'unsafe-eval'" not in csp, (
            "CSP on the Flask app surface contains 'unsafe-eval' - the loose "
            "policy must stay scoped to the Grafana/Prometheus locations"
        )
