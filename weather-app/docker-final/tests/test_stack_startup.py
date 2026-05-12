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

# ── Service lists (match container_name values in docker-compose.yml) ─────────

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

# Services with a HEALTHCHECK defined in docker-compose.yml.
# reverse-proxy, weather-app, and promtail have no healthcheck configured.
HEALTHCHECK_SERVICES = [
    "prometheus",
    "grafana",
    "loki",
    "statporter",
    "alertmanager",
    "demo-container",
]

# Mirrors: grep -iE "error|fatal|panic|exception"
_ERROR_RE = re.compile(r"error|fatal|panic|exception", re.IGNORECASE)

# Mirrors: grep -v "level=info"
# Prometheus, Grafana, and Loki use logfmt (level=info msg="..."). Lines at info
# level may contain the word "error" incidentally — exclude them from the check.
_INFO_LEVEL_RE = re.compile(r"level=info", re.IGNORECASE)


# ── Shared fixture ────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def containers(docker_client):
    """Map of container_name → Container for every expected service.

    Resolved once per module. Individual tests call c.reload() when they need
    current state rather than the snapshot taken at fixture setup.
    """
    result = {}
    for name in ALL_SERVICES:
        try:
            result[name] = docker_client.containers.get(name)
        except docker.errors.NotFound:
            result[name] = None
    return result


# ── 1.1  All services come up ─────────────────────────────────────────────────


class TestAllServicesUp:
    """1.1 — Every expected container exists and is running."""

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


# ── 1.2  Healthchecks pass ────────────────────────────────────────────────────


class TestHealthChecks:
    """1.2 — Every container with a HEALTHCHECK reports 'healthy'."""

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


# ── 1.3  No container has restarted unexpectedly ──────────────────────────────


class TestNoUnexpectedRestarts:
    """1.3 — No container is in a restart loop and RestartCount is 0."""

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


# ── 1.4  Logs are clean on startup ────────────────────────────────────────────


class TestCleanStartupLogs:
    """1.4 — No unexpected ERROR/FATAL/PANIC/EXCEPTION lines in container logs.

    Applies the same filter as:
        docker compose logs | grep -iE "error|fatal|panic|exception" | grep -v "level=info"

    The 'level=info' exclusion suppresses Prometheus, Grafana, and Loki logfmt
    lines where the word "error" appears incidentally at info severity
    (e.g. 'level=info msg="registered error handler"').
    """

    @pytest.mark.parametrize("name", ALL_SERVICES)
    def test_no_error_log_lines(self, containers, name):
        c = containers[name]
        if c is None:
            pytest.skip(f"'{name}' not found")
        raw = c.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
        error_lines = [
            line
            for line in raw.splitlines()
            if _ERROR_RE.search(line) and not _INFO_LEVEL_RE.search(line)
        ]
        if error_lines:
            sample = "\n".join(f"  {ln}" for ln in error_lines[:10])
            tail = "\n  ..." if len(error_lines) > 10 else ""
            pytest.fail(
                f"'{name}' has {len(error_lines)} unexpected error log line(s):\n"
                f"{sample}{tail}"
            )


# ── 1.5  Statporter background collector ──────────────────────────────────────


class TestStatporterCollector:
    """Verifies the background collection thread is running correctly.

    The background collector (introduced alongside ThreadPoolExecutor parallelism)
    means /metrics should respond in milliseconds rather than the ~37s sequential
    scrape time of the old on-demand design. These tests guard against a regression
    back to blocking scrapes.
    """

    def test_metrics_response_is_fast(self, containers):
        """Response time must be well under the 5s scrape_timeout in prometheus.yml."""
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
        """Cache must be populated — at least two containers should have CPU metrics."""
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
