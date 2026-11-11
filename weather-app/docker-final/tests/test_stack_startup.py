"""
Integration tests : Section 1: Stack Startup and Health Checks.

Mirrors TESTING_CHECKLIST.md sections 1.1 through 1.4.

Prerequisites:
    cd weather-app/docker-final
    docker compose up -d
    sleep 30   # allow health checks to settle
    pip install -r requirements-dev.txt
    pytest tests/test_stack_startup.py -v
"""

import json
import re
import time
from datetime import datetime

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
    "tempo",
    "otel-collector",
    "docker-socket-proxy",
]

HEALTHCHECK_SERVICES = [
    "prometheus",
    "grafana",
    "statporter",
    "alertmanager",
    "demo-container",
]

# Only lines a service itself tagged as error-level or worse count. A bare word
# match on "error" flagged info lines whose message merely mentioned an error.
_ERROR_LEVELS = {
    "error",
    "err",
    "eror",
    "crit",
    "critical",
    "fatal",
    "panic",
    "dpanic",
    "alert",
    "emerg",
}
_LEVEL_ALT = "|".join(sorted(_ERROR_LEVELS))
_ERROR_LEVEL_PATTERNS = [
    # logfmt: Prometheus, Alertmanager, Loki, Tempo, Promtail, Grafana
    re.compile(rf"\b(?:level|lvl)=\"?(?:{_LEVEL_ALT})\b", re.IGNORECASE),
    # bracketed: nginx [error], gunicorn and statporter [ERROR], haproxy [ALERT]
    re.compile(rf"\[(?:{_LEVEL_ALT})\]", re.IGNORECASE),
    # zap console encoder (otel-collector): "<timestamp>\terror\t<caller>"
    re.compile(rf"\t(?:{_LEVEL_ALT})\t", re.IGNORECASE),
]
# Crash output that carries no level tag at all.
_CRASH_PATTERNS = [
    re.compile(r"^panic: "),
    re.compile(r"^fatal error: "),
    re.compile(r"Traceback \(most recent call last\)"),
]
_JSON_LEVEL_KEYS = ("level", "levelname", "severity")

# Startup is judged on this window after the container started, cut short at
# the moment the test session began. Long-running local stacks would otherwise
# be judged on weeks of runtime logs, and CI runs on errors the suite provoked.
_STARTUP_WINDOW_S = 120


def _is_error_line(line: str) -> bool:
    stripped = line.strip()
    if stripped.startswith("{"):
        try:
            record = json.loads(stripped)
        except ValueError:
            record = None
        if isinstance(record, dict):
            for key in _JSON_LEVEL_KEYS:
                value = record.get(key)
                if isinstance(value, str):
                    return value.lower() in _ERROR_LEVELS
    if any(p.search(line) for p in _ERROR_LEVEL_PATTERNS):
        return True
    return any(p.search(stripped) for p in _CRASH_PATTERNS)


def _started_at(container) -> float:
    """Container start time as a Unix timestamp. Docker reports nanoseconds,
    which datetime cannot parse, so the fraction is trimmed to microseconds."""
    raw = container.attrs["State"]["StartedAt"]
    trimmed = re.sub(r"(\.\d{6})\d*", r"\1", raw).replace("Z", "+00:00")
    return datetime.fromisoformat(trimmed).timestamp()


# Known benign startup messages excluded per container.
# Each entry is a substring that identifies a safe log line.
_KNOWN_SAFE: dict[str, list[str]] = {
    "reverse-proxy": [
        # Long-polling SSE connection nginx kills after timeout : browser reconnects immediately.
        "notifications/live",
    ],
    "grafana": [
        # Optional provisioning dirs (plugins, alerting) are not configured : expected.
        "no such file or directory",
        # Grafana checks for Amazon Prometheus plugin daily : not installed, not needed.
        "amazonprometheus",
        # Transient SQLite lock during initialization : resolves immediately.
        "database is locked",
        # Grafana 13's background installer tries to refresh bundled plugins
        # (e.g. elasticsearch) at startup and cannot unlink files in the read-only
        # plugins-bundled dir. The bundled copy keeps working and no dashboard here
        # uses those plugins. Scoped to the installer's logger so any other
        # plugin error still fails the test.
        "logger=plugin.backgroundinstaller",
    ],
    "loki": [
        # After a host restart, Promtail backfills container logs it had not
        # shipped; anything older than Loki's 7-day ingest limit is rejected.
        # Expected after more than a week of downtime; a fresh stack never sees it.
        "timestamp too old",
        # Ring hasn't formed yet on single-node startup : transient.
        "empty ring",
        # Known Loki 3.x quirk with fake tenant on first ingest : benign.
        "negative structured metadata bytes received",
        # boltdb-shipper files remaining in the compactor dir after the v11→v13 schema
        # migration fail tsdb path validation. Local volumes only : CI starts clean.
        # Clears automatically once 168h retention expires the old boltdb tables.
        "invalid tsdb path",
    ],
    "promtail": [
        # Promtail's side of the same backfill rejection (see the loki entry).
        "timestamp too old",
    ],
    "tempo": [
        # WAL block directory exists but meta.json was not written (unclean shutdown).
        # Tempo removes the incomplete block and continues : benign recovery path.
        "failed to replay block",
        # Frontend processor drains in-flight requests on shutdown : always fires on stop.
        "queue is stopped",
    ],
    "otel-collector": [
        # gRPC warn on initial connection attempt before Tempo accepts connections.
        "addrConn.createTransport failed",
        # retry_sender logs at info level but the JSON payload contains "error" : caught
        # by our regex. These are expected retries while Tempo comes up on any restart.
        "Exporting failed. Will retry",
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
        assert (
            containers[name] is not None
        ), f"'{name}' not found : run 'docker compose up -d' and retry"

    @pytest.mark.parametrize("name", ALL_SERVICES)
    def test_container_is_running(self, containers, name):
        c = containers[name]
        if c is None:
            pytest.skip(f"'{name}' not found")
        c.reload()
        assert (
            c.status == "running"
        ), f"'{name}' status is '{c.status}', expected 'running'"


class TestHealthChecks:

    @pytest.mark.parametrize("name", HEALTHCHECK_SERVICES)
    def test_container_is_healthy(self, containers, name):
        c = containers[name]
        if c is None:
            pytest.skip(f"'{name}' not found")
        c.reload()
        status = c.attrs.get("State", {}).get("Health", {}).get("Status")
        assert status == "healthy", (
            f"'{name}' health status is '{status}', expected 'healthy' : "
            f"check 'docker inspect {name}' for failing health check output"
        )


class TestNoUnexpectedRestarts:

    @pytest.mark.parametrize("name", ALL_SERVICES)
    def test_not_in_restarting_state(self, containers, name):
        c = containers[name]
        if c is None:
            pytest.skip(f"'{name}' not found")
        c.reload()
        assert (
            c.status != "restarting"
        ), f"'{name}' is stuck in 'restarting' state : check 'docker compose logs {name}'"

    @pytest.mark.parametrize("name", ALL_SERVICES)
    def test_restart_count_is_zero(self, containers, name):
        c = containers[name]
        if c is None:
            pytest.skip(f"'{name}' not found")
        c.reload()
        count = c.attrs["RestartCount"]
        assert count == 0, (
            f"'{name}' has restarted {count} time(s) : "
            f"check 'docker compose logs {name}' for crash output"
        )


class TestCleanStartupLogs:

    @pytest.mark.parametrize("name", ALL_SERVICES)
    def test_no_error_log_lines(self, containers, session_start, name):
        c = containers[name]
        if c is None:
            pytest.skip(f"'{name}' not found")
        c.reload()
        started = _started_at(c)
        until = min(started + _STARTUP_WINDOW_S, session_start)
        if until <= started:
            pytest.skip(f"'{name}' started after the test session began")
        raw = c.logs(stdout=True, stderr=True, since=started, until=until).decode(
            "utf-8", errors="replace"
        )
        safe_substrings = _KNOWN_SAFE.get(name, [])
        error_lines = [
            line
            for line in raw.splitlines()
            if _is_error_line(line) and not any(s in line for s in safe_substrings)
        ]
        if error_lines:
            sample = "\n".join(f"  {ln}" for ln in error_lines[:10])
            tail = "\n  ..." if len(error_lines) > 10 else ""
            pytest.fail(
                f"'{name}' has {len(error_lines)} unexpected error-level log line(s) "
                f"in its first {_STARTUP_WINDOW_S}s:\n{sample}{tail}"
            )


class TestDistrolessReadiness:
    """Loki and Tempo are distroless: no Docker healthcheck.
    Verify they are serving by polling /ready via prometheus (Alpine, has wget).
    Retries for up to 60 seconds to allow for slow cold starts."""

    _TIMEOUT = 60
    _INTERVAL = 5

    @pytest.mark.parametrize(
        "url",
        [
            "http://loki:3100/ready",
            "http://tempo:3200/ready",
        ],
    )
    def test_ready_endpoint(self, containers, url):
        prom = containers["prometheus"]
        if prom is None:
            pytest.skip("prometheus not found: cannot poll distroless readiness")
        deadline = time.monotonic() + self._TIMEOUT
        while True:
            result = prom.exec_run(f"wget -q -O- {url}", demux=False)
            if result.exit_code == 0:
                body = result.output.decode("utf-8", errors="replace").strip()
                assert (
                    "ready" in body.lower()
                ), f"{url} response did not contain 'ready': {body!r}"
                return
            if time.monotonic() >= deadline:
                pytest.fail(
                    f"{url} did not become ready within {self._TIMEOUT}s "
                    f"(last exit code: {result.exit_code})"
                )
            time.sleep(self._INTERVAL)


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
            f"statporter /metrics took {elapsed:.2f}s : "
            f"background collector may not be running (old on-demand scrape was ~37s)"
        )

    def test_metrics_contains_container_data(self, containers):
        c = containers["statporter"]
        if c is None:
            pytest.skip("statporter not found")
        result = c.exec_run("curl -s http://localhost:9800/metrics")
        assert result.exit_code == 0, "curl to statporter /metrics failed"
        output = result.output.decode("utf-8", errors="replace")
        assert (
            "container_cpu_percent" in output
        ), "container_cpu_percent metric missing : collector may not have run yet"
        entries = [
            ln for ln in output.splitlines() if ln.startswith("container_cpu_percent{")
        ]
        assert len(entries) >= 2, (
            f"Expected metrics for at least 2 containers, got {len(entries)} : "
            f"collector may not have completed its first round (wait 15s and retry)"
        )
