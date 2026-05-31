"""
Integration tests - Section 3: Observability Stack.

Mirrors TESTING_CHECKLIST.md sections 3.1 through 3.6.

Prerequisites (automated by CI - or run locally after stack is up):
    cd weather-app/docker-final
    docker compose up -d && sleep 30
    pip install -r requirements-dev.txt
    pytest tests/test_observability_stack.py -v

Override the target base URL with the BASE_URL env var:
    BASE_URL=http://192.168.1.50 pytest tests/test_observability_stack.py -v

Notes on approach:
- Prometheus and Grafana are reachable through nginx (/prometheus/, /grafana/),
  so those checks use plain HTTP via `requests`.
- nginx returns 403 on /metrics to external clients (CLAUDE.md gotcha #3), so
  Flask metrics are verified *through Prometheus* (the real scrape path) rather
  than by curling /metrics directly.
- Loki is not routed through nginx and not exposed on the host, so it is queried
  by exec-ing wget inside the prometheus container (Alpine, has wget) - the same
  technique test_stack_startup.py uses for distroless readiness.
- Promtail relabels the Docker container name to the `container` label (not
  `container_name`), so Loki queries filter on `container="weather-app"`.

Class and parametrize names embed service tokens (prometheus, grafana, loki,
promtail, statporter, alertmanager, weather_app) so the CI self-healing loop
applies correct per-service labels on failure (CI_LOOP_DESIGN.md Part 4).
"""

import json
import os
import time
import urllib.parse

import pytest
import requests as http

BASE_URL = os.environ.get("BASE_URL", "http://localhost")
PROM = f"{BASE_URL}/prometheus"
GRAFANA = f"{BASE_URL}/grafana"

# Scrape jobs configured in prometheus/prometheus.yml. Parametrizing over these
# puts each service token into the pytest test id (e.g. ...::test_target_is_up[statporter]).
PROM_JOBS = [
    "prometheus",
    "weather_app",
    "grafana",
    "loki",
    "promtail",
    "statporter",
]

# Alert groups and their rules, from prometheus/rules/alerts.yml.
EXPECTED_RULE_GROUPS = {
    "container_alerts": {"ContainerDown", "ContainerHighMemory", "ContainerHighCPU"},
    "stack_alerts": {"LokiIngestStopped", "WeatherAppHighErrorRate"},
    "playground_alerts": {"DemoContainerDown", "DemoContainerHighCPU"},
}

# Provisioned Grafana dashboards (uid -> title), from grafana/dashboards/.
EXPECTED_DASHBOARD_UIDS = {
    "homelab-observability",
    "container-metrics-statporter",
    "all-containers-logs",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _poll(fn, timeout=30.0, interval=3.0):
    """Call fn() until it returns a truthy value or timeout elapses.

    fn should return the value on success or None to keep polling. The last
    AssertionError (if any) is re-raised on timeout so failures are informative.
    """
    deadline = time.monotonic() + timeout
    last_exc = None
    while True:
        try:
            result = fn()
            if result:
                return result
        except AssertionError as exc:
            last_exc = exc
        if time.monotonic() >= deadline:
            if last_exc is not None:
                raise last_exc
            return None
        time.sleep(interval)


def _prom_query(expr):
    """Run an instant PromQL query and return the result list."""
    resp = http.get(f"{PROM}/api/v1/query", params={"query": expr}, timeout=10)
    assert (
        resp.status_code == 200
    ), f"Prometheus query {expr!r} returned HTTP {resp.status_code}"
    payload = resp.json()
    assert (
        payload.get("status") == "success"
    ), f"Prometheus query {expr!r} status: {payload.get('status')!r}"
    return payload["data"]["result"]


def _generate_weather_app_traffic(count=3):
    """Hit /healthz a few times so weather-app emits 200s and request logs.

    Used before metric/log assertions to guarantee there is fresh data to find,
    regardless of test execution order.
    """
    for _ in range(count):
        try:
            http.get(f"{BASE_URL}/healthz", timeout=10)
        except http.RequestException:
            pass


# ---------------------------------------------------------------------------
# 3.1  Prometheus targets
# ---------------------------------------------------------------------------


class TestPrometheusTargets:

    @pytest.fixture(scope="class")
    def targets_by_job(self):
        def fetch():
            resp = http.get(f"{PROM}/api/v1/targets", timeout=10)
            assert (
                resp.status_code == 200
            ), f"/prometheus/api/v1/targets returned HTTP {resp.status_code}"
            active = resp.json()["data"]["activeTargets"]
            return {t["labels"]["job"]: t["health"] for t in active} or None

        result = _poll(fetch, timeout=30, interval=3)
        assert result, "Prometheus returned no active targets"
        return result

    @pytest.mark.parametrize("job", PROM_JOBS)
    def test_target_is_up(self, targets_by_job, job):
        assert job in targets_by_job, (
            f"job {job!r} not found in Prometheus targets "
            f"(present: {sorted(targets_by_job)})"
        )
        health = targets_by_job[job]
        assert health == "up", (
            f"Prometheus target {job!r} health is {health!r}, expected 'up' "
            f"- check /prometheus/targets"
        )

    def test_no_target_is_down(self, targets_by_job):
        down = {job: h for job, h in targets_by_job.items() if h != "up"}
        assert not down, f"One or more Prometheus targets are not up: {down}"


# ---------------------------------------------------------------------------
# 3.2  Alert rules loaded
# ---------------------------------------------------------------------------


class TestPrometheusAlertRules:

    @pytest.fixture(scope="class")
    def rule_groups(self):
        resp = http.get(f"{PROM}/api/v1/rules", timeout=10)
        assert (
            resp.status_code == 200
        ), f"/prometheus/api/v1/rules returned HTTP {resp.status_code}"
        groups = resp.json()["data"]["groups"]
        return {g["name"]: g["rules"] for g in groups}

    @pytest.mark.parametrize("group_name", sorted(EXPECTED_RULE_GROUPS))
    def test_group_present(self, rule_groups, group_name):
        assert group_name in rule_groups, (
            f"alert group {group_name!r} not loaded "
            f"(present: {sorted(rule_groups)})"
        )

    @pytest.mark.parametrize("group_name", sorted(EXPECTED_RULE_GROUPS))
    def test_group_has_expected_rules(self, rule_groups, group_name):
        if group_name not in rule_groups:
            pytest.skip(f"group {group_name!r} not loaded")
        names = {
            r["name"] for r in rule_groups[group_name] if r.get("type") == "alerting"
        }
        expected = EXPECTED_RULE_GROUPS[group_name]
        assert (
            expected <= names
        ), f"group {group_name!r} missing rules: {expected - names}"

    def test_no_alert_rule_is_firing(self, rule_groups):
        """No alert should be firing on a healthy stack at rest (3.2: no false alerts)."""
        firing = []
        for group_name, rules in rule_groups.items():
            for rule in rules:
                if rule.get("type") == "alerting" and rule.get("state") == "firing":
                    firing.append(f"{group_name}/{rule['name']}")
        assert not firing, f"Alert rule(s) unexpectedly firing at rest: {firing}"


# ---------------------------------------------------------------------------
# 3.3  AlertManager reachable
# ---------------------------------------------------------------------------


class TestAlertmanagerReachable:

    def test_prometheus_has_active_alertmanager(self):
        resp = http.get(f"{PROM}/api/v1/alertmanagers", timeout=10)
        assert (
            resp.status_code == 200
        ), f"/prometheus/api/v1/alertmanagers returned HTTP {resp.status_code}"
        active = resp.json()["data"]["activeAlertmanagers"]
        urls = [a.get("url", "") for a in active]
        assert any("alertmanager:9093" in u for u in urls), (
            f"Prometheus has no active alertmanager at alertmanager:9093 "
            f"(active: {urls})"
        )


# ---------------------------------------------------------------------------
# 3.4  Grafana dashboards
# ---------------------------------------------------------------------------


class TestGrafanaDashboards:

    def test_grafana_loads_anonymously(self):
        """Anonymous viewer access is enabled - the root should load without login."""
        resp = http.get(f"{GRAFANA}/", timeout=10)
        assert (
            resp.status_code == 200
        ), f"Grafana root returned HTTP {resp.status_code} (anonymous access expected)"

    def test_grafana_health_ok(self):
        resp = http.get(f"{GRAFANA}/api/health", timeout=10)
        assert (
            resp.status_code == 200
        ), f"/grafana/api/health returned HTTP {resp.status_code}"
        body = resp.json()
        assert (
            body.get("database") == "ok"
        ), f"Grafana health database status is {body.get('database')!r}, expected 'ok'"

    def test_provisioned_dashboards_present(self):
        def fetch():
            resp = http.get(
                f"{GRAFANA}/api/search", params={"type": "dash-db"}, timeout=10
            )
            assert (
                resp.status_code == 200
            ), f"/grafana/api/search returned HTTP {resp.status_code}"
            uids = {d.get("uid") for d in resp.json()}
            return uids if EXPECTED_DASHBOARD_UIDS <= uids else None

        uids = _poll(fetch, timeout=30, interval=3)
        assert uids, (
            "Provisioned dashboards not all present in Grafana within timeout "
            f"(expected {EXPECTED_DASHBOARD_UIDS})"
        )


# ---------------------------------------------------------------------------
# 3.5  Prometheus metrics from Flask (weather_app)
# ---------------------------------------------------------------------------


class TestWeatherAppFlaskMetrics:
    """Verified via Prometheus rather than curling /metrics: nginx returns 403 on
    /metrics to external clients (CLAUDE.md gotcha #3)."""

    def test_weather_app_request_total_metric_present(self):
        _generate_weather_app_traffic()
        result = _poll(
            lambda: _prom_query("flask_http_request_total") or None,
            timeout=30,
            interval=3,
        )
        assert result, "flask_http_request_total not present in Prometheus"

    def test_weather_app_request_total_has_label_dimensions(self):
        result = _poll(
            lambda: _prom_query("flask_http_request_total") or None,
            timeout=30,
            interval=3,
        )
        assert result, "flask_http_request_total not present in Prometheus"
        labels = result[0]["metric"]
        for dim in ("method", "status"):
            assert (
                dim in labels
            ), f"flask_http_request_total missing label dimension {dim!r}: {labels}"

    def test_weather_app_request_duration_metric_present(self):
        result = _poll(
            lambda: _prom_query("flask_http_request_duration_seconds_count") or None,
            timeout=30,
            interval=3,
        )
        assert result, "flask_http_request_duration_seconds not present in Prometheus"

    def test_weather_app_has_200_responses(self):
        _generate_weather_app_traffic()

        def has_200():
            result = _prom_query('flask_http_request_total{status="200"}')
            total = sum(float(s["value"][1]) for s in result)
            return total > 0

        assert _poll(has_200, timeout=40, interval=4), (
            'No flask_http_request_total{status="200"} count > 0 in Prometheus '
            "- weather-app may not have served any successful requests yet"
        )


# ---------------------------------------------------------------------------
# 3.6  Loki receiving logs
# ---------------------------------------------------------------------------


class TestLokiReceivingLogs:
    """Loki is not exposed on the host or via nginx; query it by exec-ing wget
    inside the prometheus container (Alpine, has wget)."""

    def _loki_query_lines(self, prom_container, logql, lookback_s=600, limit=100):
        end_ns = int(time.time() * 1e9)
        start_ns = end_ns - lookback_s * 1_000_000_000
        qs = urllib.parse.urlencode(
            {
                "query": logql,
                "start": start_ns,
                "end": end_ns,
                "limit": limit,
                "direction": "backward",
            }
        )
        url = f"http://loki:3100/loki/api/v1/query_range?{qs}"
        result = prom_container.exec_run(f"wget -q -O- '{url}'", demux=False)
        assert (
            result.exit_code == 0
        ), f"wget to Loki failed (exit {result.exit_code}): {url}"
        payload = json.loads(result.output.decode("utf-8", errors="replace"))
        lines = []
        for stream in payload.get("data", {}).get("result", []):
            for _ts, line in stream.get("values", []):
                lines.append(line)
        return lines

    @pytest.fixture(scope="class")
    def prom_container(self, docker_client):
        import docker.errors

        try:
            return docker_client.containers.get("prometheus")
        except docker.errors.NotFound:
            pytest.skip("prometheus container not found: cannot query Loki via exec")

    def test_loki_has_weather_app_logs(self, prom_container):
        _generate_weather_app_traffic()
        lines = _poll(
            lambda: self._loki_query_lines(prom_container, '{container="weather-app"}')
            or None,
            timeout=40,
            interval=4,
        )
        assert lines, "Loki returned no log lines for container='weather-app'"

    def test_loki_weather_app_logs_are_structured_json(self, prom_container):
        _generate_weather_app_traffic()
        lines = _poll(
            lambda: self._loki_query_lines(prom_container, '{container="weather-app"}')
            or None,
            timeout=40,
            interval=4,
        )
        assert lines, "Loki returned no log lines for container='weather-app'"
        json_lines = [ln for ln in lines if ln.strip().startswith("{")]
        assert json_lines, (
            "No structured JSON log lines found from weather-app "
            f"(sample: {lines[0][:200]!r})"
        )

    def test_loki_weather_app_logs_include_request_id(self, prom_container):
        _generate_weather_app_traffic()

        def find_request_id():
            lines = self._loki_query_lines(prom_container, '{container="weather-app"}')
            return any("request_id" in ln for ln in lines)

        assert _poll(find_request_id, timeout=40, interval=4), (
            "No weather-app log line containing 'request_id' found in Loki "
            "(Flask logging middleware should add it on every request)"
        )
