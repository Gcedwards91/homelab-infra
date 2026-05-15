"""
Integration tests — Section 1: Stack Startup and Health Checks.

Mirrors TESTING_CHECKLIST.md sections 1.1 through 1.4.

Prerequisites:
    cd weather-app/docker-final
    docker compose up -d
    sleep 30   # allow health checks to settle
    pip install -r requirements-dev.txt
    pytest tests/test_stack_startup.py -v
"""

import re
import time

import docker.errors
import pytest

ALL_SERVICES = [
    "reverse-proxy",
    "weather-app",
    "prometheus",
    "grafana",
    "loki",
    "promtail",
    "statporter",
    "alertmanager",
    "demo-container",
]

HEALTHCHECK_SERVICES = [
    "prometheus",
    "grafana",
    "loki",
    "statporter",
    "alertmanager",
    "demo-container",
]

_ERROR_RE = re.compile(r"error|fatal|panic|exception", re.IGNORECASE)
# Prometheus/Grafana/Loki logfmt lines at info level may contain "error" incidentally.
_INFO_LEVEL_RE = re.compile(r"level=info", re.IGNORECASE)

# Known benign startup messages excluded per container.
# Each entry is a substring that identifies a safe log line.
_KNOWN_SAFE: dict[str, list[str]] = {
    "reverse-proxy": [
        # Long-polling SSE connection nginx kills after timeout — browser reconnects immediately.
        "notifications/live",
    ],
    "grafana": [
        # Optional provisioning dirs (plugins, alerting) are not configured — expected.
        "no such file or directory",
        # Grafana checks for Amazon Prometheus plugin daily — not installed, not needed.
        "amazonprometheus",
        # Transient SQLite lock during initialization — resolves immediately.
        "database is locked",
    ],
    "loki": [
        # Ring hasn't formed yet on single-node startup — transient.
        "empty ring",
        # Known Loki 3.x quirk with fake tenant on first ingest — benign.
        "negative structured metadata bytes received",
    ],
}


@pytest.fixture(scope="module")
def containers(docker_client):
    result = {}
    for name in ALL_SERVICES:
        try:
            result[name] = docker_client.containers.get(name)
        except docker.errors.NotFound:
            result[name] = None
    return result


class TestAllServicesUp:

    @pytest.mark.parametrize("name", ALL_SERVICES)
    def test_container_exists(self, containers, name):
        assert containers[name] is not None, (
            f"'{name}' not found — run 'docker compose up -d' and retry"
        )

    @pytest.mark.parametrize("name", ALL_SERVICES)
    def test_container_is_running(self, containers, name):
        c = containers[name]
        if c is None:
            pytest.skip(f"'{name}' not found")
        c.reload()
        assert c.status == "running", (
            f"'{name}' status is '{c.status}', expected 'running'"
        )


class TestHealthChecks:

    @pytest.mark.parametrize("name", HEALTHCHECK_SERVICES)
    def test_container_is_healthy(self, containers, name):
        c = containers[name]
        if c is None:
            pytest.skip(f"'{name}' not found")
        c.reload()
        status = c.attrs.get("State", {}).get("Health", {}).get("Status")
        assert status == "healthy", (
            f"'{name}' health status is '{status}', expected 'healthy' — "
            f"check 'docker inspect {name}' for failing health check output"
        )


class TestNoUnexpectedRestarts:

    @pytest.mark.parametrize("name", ALL_SERVICES)
    def test_not_in_restarting_state(self, containers, name):
        c = containers[name]
        if c is None:
            pytest.skip(f"'{name}' not found")
        c.reload()
        assert c.status != "restarting", (
            f"'{name}' is stuck in 'restarting' state — check 'docker compose logs {name}'"
        )

    @pytest.mark.parametrize("name", ALL_SERVICES)
    def test_restart_count_is_zero(self, containers, name):
        c = containers[name]
        if c is None:
            pytest.skip(f"'{name}' not found")
        c.reload()
        count = c.attrs["RestartCount"]
        assert count == 0, (
            f"'{name}' has restarted {count} time(s) — "
            f"check 'docker compose logs {name}' for crash output"
        )


class TestCleanStartupLogs:

    @pytest.mark.parametrize("name", ALL_SERVICES)
    def test_no_error_log_lines(self, containers, name):
        c = containers[name]
        if c is None:
            pytest.skip(f"'{name}' not found")
        raw = c.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
        safe_substrings = _KNOWN_SAFE.get(name, [])
        error_lines = [
            line
            for line in raw.splitlines()
            if _ERROR_RE.search(line)
            and not _INFO_LEVEL_RE.search(line)
            and not any(s in line for s in safe_substrings)
        ]
        if error_lines:
            sample = "\n".join(f"  {ln}" for ln in error_lines[:10])
            tail = "\n  ..." if len(error_lines) > 10 else ""
            pytest.fail(
                f"'{name}' has {len(error_lines)} unexpected error log line(s):\n"
                f"{sample}{tail}"
            )


class TestStatporterCollector:
    def test_metrics_response_is_fast(self, containers):
        c = containers["statporter"]
        if c is None:
            pytest.skip("statporter not found")
        start = time.monotonic()
        result = c.exec_run("curl -s http://localhost:9800/metrics")
        elapsed = time.monotonic() - start
        assert result.exit_code == 0, "curl to statporter /metrics failed"
        assert elapsed < 2.0, (
            f"statporter /metrics took {elapsed:.2f}s — "
            f"background collector may not be running (old on-demand scrape was ~37s)"
        )

    def test_metrics_contains_container_data(self, containers):
        c = containers["statporter"]
        if c is None:
            pytest.skip("statporter not found")
        result = c.exec_run("curl -s http://localhost:9800/metrics")
        assert result.exit_code == 0, "curl to statporter /metrics failed"
        output = result.output.decode("utf-8", errors="replace")
        assert "container_cpu_percent" in output, (
            "container_cpu_percent metric missing — collector may not have run yet"
        )
        entries = [ln for ln in output.splitlines() if ln.startswith("container_cpu_percent{")]
        assert len(entries) >= 2, (
            f"Expected metrics for at least 2 containers, got {len(entries)} — "
            f"collector may not have completed its first round (wait 15s and retry)"
        )
