"""
Integration tests - Section 4: Alerting (plus playground 9.5 / 9.6 lifecycle).

Mirrors TESTING_CHECKLIST.md sections 4.1, 4.3, 4.4 and playground sections 9.5,
9.6. Every test here is DESTRUCTIVE: it stops a container or spikes CPU and waits
out the alert window, then restores the stack in a finally block.

These are excluded from the default suite by the 'destructive' marker
(pytest.ini sets `addopts = -m "not destructive"`). Run them deliberately:

    cd weather-app/docker-final
    docker compose up -d && sleep 30
    pip install -r requirements-dev.txt
    pytest tests/test_alerting.py -v -m destructive

In CI they run only via the manual 'destructive-alerting-tests' workflow_dispatch
job, never on push.

Service tokens for CI labelling (CI_LOOP_DESIGN.md Part 4): the loki test class
name contains 'loki' (svc:loki); the demo-container test function names contain
'demo_container' (svc:demo-container).
"""

import os
import time

import docker.errors
import pytest
import requests as http

pytestmark = pytest.mark.destructive

BASE_URL = os.environ.get("BASE_URL", "http://localhost")
PROM = f"{BASE_URL}/prometheus"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _poll(fn, timeout, interval):
    """Call fn() until it returns truthy or timeout elapses. Returns the value
    or None on timeout. AssertionErrors raised by fn are swallowed between
    attempts so transient failures (e.g. Prometheus mid-scrape) do not abort."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            result = fn()
            if result:
                return result
        except AssertionError:
            pass
        if time.monotonic() >= deadline:
            return None
        time.sleep(interval)


def _active_alerts():
    resp = http.get(f"{PROM}/api/v1/alerts", timeout=10)
    assert (
        resp.status_code == 200
    ), f"/prometheus/api/v1/alerts returned HTTP {resp.status_code}"
    return resp.json()["data"]["alerts"]


def _find_alert(name):
    """Return the active alert dict for `name` (pending or firing), or None."""
    for alert in _active_alerts():
        if alert["labels"].get("alertname") == name:
            return alert
    return None


def _alert_is_firing(name):
    alert = _find_alert(name)
    return bool(alert) and alert.get("state") == "firing"


def _alert_absent(name):
    return _find_alert(name) is None


def _prom_scalar(expr):
    """Return the float value of an instant query's first sample, or None."""
    resp = http.get(f"{PROM}/api/v1/query", params={"query": expr}, timeout=10)
    assert (
        resp.status_code == 200
    ), f"Prometheus query {expr!r} returned HTTP {resp.status_code}"
    result = resp.json()["data"]["result"]
    if not result:
        return None
    return float(result[0]["value"][1])


def _wait_loki_ready(docker_client):
    """Poll loki /ready via the prometheus container (Alpine, has wget)."""
    try:
        prom = docker_client.containers.get("prometheus")
    except docker.errors.NotFound:
        return
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        result = prom.exec_run("wget -q -O- http://loki:3100/ready", demux=False)
        if result.exit_code == 0 and b"ready" in result.output.lower():
            return
        time.sleep(5)


# ---------------------------------------------------------------------------
# 4.1  ContainerDown fires and resolves (loki)
# ---------------------------------------------------------------------------


class TestContainerDownAlertLoki:
    """ContainerDown has `for: 2m`, so firing takes just over two minutes after
    loki goes down. Resolution is fast once loki is back up (no `for` on clear)."""

    def test_loki_down_fires_and_resolves(self, docker_client):
        try:
            loki = docker_client.containers.get("loki")
        except docker.errors.NotFound:
            pytest.skip("loki container not found")

        try:
            loki.stop()
            fired = _poll(
                lambda: _alert_is_firing("ContainerDown"),
                timeout=200,
                interval=10,
            )
            assert fired, (
                "ContainerDown did not reach 'firing' within 200s of stopping loki "
                "(rule has for: 2m)"
            )
        finally:
            loki.start()
            _wait_loki_ready(docker_client)

        resolved = _poll(
            lambda: _alert_absent("ContainerDown"), timeout=120, interval=10
        )
        assert (
            resolved
        ), "ContainerDown did not clear within 120s of loki coming back up"


# ---------------------------------------------------------------------------
# 4.3 / 9.5  DemoContainerDown fires and resolves
# ---------------------------------------------------------------------------


class TestDemoContainerDownAlert:

    def test_demo_container_down_fires_and_resolves(self, docker_client):
        try:
            demo = docker_client.containers.get("demo-container")
        except docker.errors.NotFound:
            pytest.skip("demo-container not found")

        try:
            demo.stop()
            # Rule has for: 10s, but statporter must first scrape (10s interval)
            # and drop the stale label so absent() returns 1. Allow ~90s.
            alert = _poll(
                lambda: (
                    _find_alert("DemoContainerDown")
                    if _alert_is_firing("DemoContainerDown")
                    else None
                ),
                timeout=90,
                interval=5,
            )
            assert alert, (
                "DemoContainerDown did not reach 'firing' within 90s of stopping "
                "demo-container"
            )
            summary = alert.get("annotations", {}).get("summary", "")
            assert "demo-container is not running" in summary, (
                f"DemoContainerDown summary annotation is {summary!r}, expected "
                f"'demo-container is not running'"
            )
        finally:
            demo.start()

        resolved = _poll(
            lambda: _alert_absent("DemoContainerDown"), timeout=120, interval=5
        )
        assert resolved, (
            "DemoContainerDown did not clear within 120s of restarting "
            "demo-container"
        )


# ---------------------------------------------------------------------------
# 4.4 / 9.6  DemoContainerHighCPU fires and resolves
# ---------------------------------------------------------------------------


class TestDemoContainerHighCpuAlert:
    """demo-container:8080 is only reachable from inside the monitoring network,
    so the stress endpoint is hit by exec-ing curl in weather-app (which has curl
    and shares the bridge)."""

    def _stress(self, docker_client, endpoint):
        wa = docker_client.containers.get("weather-app")
        return wa.exec_run(
            f"curl -s -m 5 -X POST http://demo-container:8080/{endpoint}"
        )

    def test_demo_container_high_cpu_fires_and_resolves(self, docker_client):
        try:
            docker_client.containers.get("weather-app")
            docker_client.containers.get("demo-container")
        except docker.errors.NotFound:
            pytest.skip("weather-app or demo-container not found")

        start = self._stress(docker_client, "stress")
        assert start.exit_code == 0, (
            "could not reach demo-container stress endpoint from weather-app "
            f"(curl exit {start.exit_code})"
        )

        try:
            # Rule has for: 10s; allow a scrape cycle to register CPU above 80%.
            fired = _poll(
                lambda: _alert_is_firing("DemoContainerHighCPU"),
                timeout=90,
                interval=5,
            )
            assert fired, (
                "DemoContainerHighCPU did not reach 'firing' within 90s of "
                "starting the CPU stress"
            )
            cpu = _prom_scalar('container_cpu_percent{name="demo_container"}')
            assert cpu is not None and cpu > 80, (
                f"container_cpu_percent for demo_container is {cpu}, expected > 80 "
                f"while stress is active"
            )
        finally:
            # End the burn early (it would self-terminate after 60s anyway).
            self._stress(docker_client, "stop_stress")

        resolved = _poll(
            lambda: _alert_absent("DemoContainerHighCPU"), timeout=90, interval=5
        )
        assert (
            resolved
        ), "DemoContainerHighCPU did not clear within 90s of stopping the stress"
