# test: unit test suite - weather client, playground auth, statporter collector

**STATUS: PLANNED**
**Branch target:** `master`
**Estimated scope:** ~3 test files created, ~2 `__init__.py` created, 1 workflow created, `requirements-dev.txt` referenced

---

## Background Required

Before implementing, read:

- `CLAUDE.md` - architecture, conventions, the "Still needed" unit-test list under the Tests section
- `CI_LOOP_DESIGN.md` Part 4 - the file/class/function naming convention that drives per-service labels on CI failure
- `TESTING_CHECKLIST.md` - the end-to-end scope; these unit tests sit underneath it, not inside it
- `weather-app/docker-src/weather.py` - `get_weather()` and its error branches
- `weather-app/docker-src/playground.py` - `_derive()`, `_valid_passphrases()`, `_passphrase_info()`, `_session_valid()`, the login route
- `weather-app/docker-final/statporter/statporter.py` - `_cpu_percent()`, `_blkio_bytes()`, `_scrape_one()`, `collect_metrics()` stale-label cleanup
- `weather-app/docker-final/tests/test_weather_app.py` - the existing integration test for playground auth; the unit tests are the isolated, stack-free complement to it

---

## Summary

Adds a fast, stack-free unit test layer for the three modules that currently have only integration coverage (or none). Unit tests run with no Docker daemon and no running stack: every external dependency (the OpenWeatherMap HTTP call, the system clock, the Docker SDK, Prometheus gauges) is mocked. This is the complement to the integration suite, which exercises the same code through the live stack but cannot cheaply drive error branches, clock boundaries, or stale-label cleanup.

Three target modules, mapped to the "Still needed" list in `CLAUDE.md`:

1. **`weather.py`** - assert every error path returns a user-friendly message and never leaks the API key or raw exception detail
2. **`playground.py`** - passphrase derivation, rotation window boundary and grace period, session idle expiry
3. **`statporter.py`** - `_cpu_percent()`, `_blkio_bytes()`, and the stale-label cleanup that lets `absent()` fire

```
push to weather-app/docker-src/**     → unit-tests.yml → pytest (no stack)  → fast pass/fail
push to .../statporter/**             → unit-tests.yml → pytest (no stack)  → fast pass/fail
push to weather-app/docker-final/**   → integration-tests.yml → full stack  → pytest (unchanged)
```

The two layers stay separate: integration tests require the stack and live under `docker-final/tests/`; unit tests require nothing and live next to the code they test.

---

## Architecture

### Layout

Unit tests are co-located with the module under test so imports are direct and the tests are never swept into the stack-requiring integration run:

```
weather-app/
├── docker-src/
│   └── tests/                        # NEW - Flask app unit tests (no stack)
│       ├── __init__.py
│       ├── conftest.py               # sys.path + shared fixtures
│       ├── test_weather.py           # weather.py
│       └── test_playground.py        # playground.py auth helpers + login route
└── docker-final/
    ├── tests/                        # EXISTING - integration tests (stack required)
    └── statporter/
        └── tests/                    # NEW - statporter unit tests (no stack)
            ├── __init__.py
            ├── conftest.py
            └── test_statporter.py
```

### Why not under `docker-final/tests/`

The existing `docker-final/tests/` tree is run by `integration-tests.yml`, which spins up the full stack first. Putting unit tests there would either (a) couple a fast, dependency-free check to a multi-minute stack startup, or (b) require marker gymnastics to split them back out. Co-locating with the source keeps each layer's CI trigger and runtime clean.

### Mocking strategy

Use the standard library `unittest.mock` (`patch`, `MagicMock`) and pytest's `monkeypatch`. No new runtime dependency. The Flask app modules import `flask`, `requests`, and `docker`; statporter imports `prometheus_client` and `docker`. Those are already in each component's `requirements.txt`, so the unit-test job installs the component requirements plus `pytest`.

---

## Part 1 - `weather.py`

### File to create: `weather-app/docker-src/tests/test_weather.py`

`get_weather(location, api_key, mode)` makes exactly one `requests.get` and returns either a `WeatherData` dict or a `WeatherError` dict. Patch `weather.requests.get`; never make a real network call.

**Class:** `TestWeatherAppWeatherClient`. Each test function name embeds the `weather_app` token (with underscore) so the CI loop labels failures `svc:weather-app` (CI_LOOP_DESIGN.md Part 4).

| Test function                                          | Setup                                                | Assert                                                                                  |
| ------------------------------------------------------ | ---------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `test_weather_app_success_maps_all_fields`             | mock 200 with a full OpenWeatherMap JSON body        | returned dict has `city/temp/feels_like/description/humidity/wind_speed` mapped exactly |
| `test_weather_app_city_mode_builds_q_param`            | mode="city"                                          | `requests.get` called with `params["q"] == location`, no `zip` key                      |
| `test_weather_app_zip_mode_builds_zip_param`           | mode="zip"                                           | `params["zip"] == f"{location},us"`                                                     |
| `test_weather_app_http_404_returns_location_not_found` | mock response raising `HTTPError`, `status_code=404` | returns `{"error": "Location not found."}`                                              |
| `test_weather_app_http_500_returns_service_error`      | `HTTPError`, `status_code=500`                       | error contains "Weather service error (500)"; does NOT contain the api_key              |
| `test_weather_app_connection_error_returns_generic`    | `requests.get` raises `ConnectionError`              | returns `{"error": "An unexpected error occurred. Please try again."}`                  |
| `test_weather_app_timeout_returns_generic`             | `requests.get` raises `Timeout`                      | same generic message                                                                    |
| `test_weather_app_api_key_never_in_error`              | any error branch, sentinel api_key                   | sentinel api_key string not present in the returned error value                         |
| `test_weather_app_error_has_no_raw_exception_tokens`   | any error branch                                     | error has none of `Traceback`, `raise `, `Exception`, `File "`                          |

### Skeleton

```python
from unittest.mock import patch, MagicMock
import requests
import weather  # resolved via conftest sys.path insert

_OK_BODY = {
    "name": "Atlanta",
    "main": {"temp": 71.0, "feels_like": 70.0, "humidity": 44},
    "weather": [{"description": "clear sky"}],
    "wind": {"speed": 5.0},
}


class TestWeatherAppWeatherClient:
    @patch("weather.requests.get")
    def test_weather_app_success_maps_all_fields(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200)
        mock_get.return_value.json.return_value = _OK_BODY
        mock_get.return_value.raise_for_status.return_value = None
        result = weather.get_weather("Atlanta", "key", "city")
        assert result["city"] == "Atlanta"
        assert result["wind_speed"] == 5.0

    @patch("weather.requests.get")
    def test_weather_app_http_404_returns_location_not_found(self, mock_get):
        resp = MagicMock(status_code=404)
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError()
        mock_get.return_value = resp
        assert weather.get_weather("Nowhere", "key") == {"error": "Location not found."}
```

---

## Part 2 - `playground.py`

### File to create: `weather-app/docker-src/tests/test_playground.py`

Two groups: pure helper logic (deterministic, clock mocked) and the login route (Flask test client). `playground.py` reads `PLAYGROUND_SECRET` and `PLAYGROUND_ADMIN_KEY` from the environment, so `conftest.py` sets fixed values via `monkeypatch.setenv` before import-time reads, and tests patch `playground.time.time` to control the rotation window.

**Class:** `TestWeatherAppPlaygroundAuth` (helpers) and `TestWeatherAppPlaygroundLogin` (route). Both file path and function names carry the `weather_app` token via function names like `test_weather_app_playground_*`.

| Test function                                                   | Target               | Assert                                                                                         |
| --------------------------------------------------------------- | -------------------- | ---------------------------------------------------------------------------------------------- |
| `test_weather_app_playground_derive_is_deterministic`           | `_derive`            | same `(secret, window_id)` yields the same 14-char passphrase across calls                     |
| `test_weather_app_playground_derive_differs_per_window`         | `_derive`            | window N and window N+1 produce different passphrases                                          |
| `test_weather_app_playground_one_passphrase_mid_window`         | `_valid_passphrases` | mid-window (clock far from boundary) returns exactly one passphrase                            |
| `test_weather_app_playground_two_passphrases_in_grace`          | `_valid_passphrases` | clock < `GRACE_SECONDS` past a boundary returns current AND previous-window passphrase         |
| `test_weather_app_playground_grace_boundary_exact`              | `_valid_passphrases` | at exactly `GRACE_SECONDS` past boundary, previous passphrase is no longer offered             |
| `test_weather_app_playground_passphrase_info_math`              | `_passphrase_info`   | `seconds_until_rotation` equals `WINDOW_SECONDS - (now % WINDOW_SECONDS)`; `next` != `current` |
| `test_weather_app_playground_session_valid_when_recent`         | `_session_valid`     | auth flag set + `last_active` within `SESSION_IDLE_LIMIT` returns True                         |
| `test_weather_app_playground_session_expires_after_idle`        | `_session_valid`     | `last_active` older than `SESSION_IDLE_LIMIT` returns False                                    |
| `test_weather_app_playground_session_invalid_without_auth_flag` | `_session_valid`     | no `playground_auth` in session returns False                                                  |
| `test_weather_app_playground_login_accepts_current_passphrase`  | login route (client) | POST with the current passphrase returns 302 and sets `playground_auth` in session             |
| `test_weather_app_playground_login_rejects_wrong_passphrase`    | login route (client) | POST with a wrong value returns 401 and does NOT set the session flag                          |
| `test_weather_app_playground_login_accepts_grace_passphrase`    | login route (client) | inside grace period, the previous-window passphrase is accepted (302)                          |

### Notes

- Build a throwaway Flask app in `conftest.py`, register `playground_bp`, set `SECRET_KEY`, and yield `app.test_client()`. This exercises the real `require_auth` / login flow without the stack.
- Patch `playground.time.time` (not `time.time` globally) so window math is controlled. Helper `_window_start(n) = n * WINDOW_SECONDS`.
- Assert the login route never echoes the submitted password into the response body (mirrors the integration sentinel test, but at unit level).

---

## Part 3 - `statporter.py`

### File to create: `weather-app/docker-final/statporter/tests/test_statporter.py`

Pure functions plus the cleanup branch of `collect_metrics()`. No Docker daemon: patch `statporter.get_client` to return a fake client whose `.containers.list()` returns fake container objects, and assert against the gauges.

**Class:** `TestStatporterCollector`. The `statporter` token is in both the path and the class name, so labeling is automatic.

| Test function                                                | Target            | Assert                                                                                         |
| ------------------------------------------------------------ | ----------------- | ---------------------------------------------------------------------------------------------- |
| `test_statporter_cpu_percent_normal_delta`                   | `_cpu_percent`    | known cpu/system deltas with 2 percpu entries return the expected percentage                   |
| `test_statporter_cpu_percent_zero_when_system_usage_missing` | `_cpu_percent`    | missing `system_cpu_usage` returns `0.0`                                                       |
| `test_statporter_cpu_percent_zero_when_system_delta_nonpos`  | `_cpu_percent`    | `system_delta <= 0` returns `0.0`                                                              |
| `test_statporter_cpu_percent_zero_when_cpu_delta_nonpos`     | `_cpu_percent`    | `cpu_delta <= 0` returns `0.0`                                                                 |
| `test_statporter_cpu_percent_uses_percpu_count`              | `_cpu_percent`    | num_cpus multiplier comes from `len(percpu_usage)` when present                                |
| `test_statporter_blkio_sums_read_and_write`                  | `_blkio_bytes`    | mixed read/write entries sum into the correct `(read, write)` tuple                            |
| `test_statporter_blkio_handles_missing_recursive`            | `_blkio_bytes`    | absent or `None` `io_service_bytes_recursive` returns `(0, 0)`                                 |
| `test_statporter_blkio_op_is_case_insensitive`               | `_blkio_bytes`    | `"Read"` / `"WRITE"` are counted (op lowercased)                                               |
| `test_statporter_scrape_one_converts_hyphen_to_underscore`   | `_scrape_one`     | container named `demo-container` yields name `demo_container`                                  |
| `test_statporter_scrape_one_returns_none_on_error`           | `_scrape_one`     | `container.stats()` raising returns `None` (logged, not raised)                                |
| `test_statporter_stale_label_removed_when_container_gone`    | `collect_metrics` | a name present in a prior round but absent now has `gauge.remove(name)` called for every gauge |
| `test_statporter_seen_names_tracks_current_round`            | `collect_metrics` | module `_seen_names` equals the set of names scraped this round                                |

### Skeleton

```python
import statporter  # resolved via conftest sys.path insert


def _stats(cpu_total, precpu_total, sys_now, sys_prev, ncpu=2):
    return {
        "cpu_stats": {
            "cpu_usage": {"total_usage": cpu_total, "percpu_usage": [0] * ncpu},
            "system_cpu_usage": sys_now,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": precpu_total},
            "system_cpu_usage": sys_prev,
        },
    }


class TestStatporterCollector:
    def test_statporter_cpu_percent_zero_when_system_usage_missing(self):
        s = _stats(100, 0, None, None)
        assert statporter._cpu_percent(s) == 0.0

    def test_statporter_blkio_sums_read_and_write(self):
        s = {"blkio_stats": {"io_service_bytes_recursive": [
            {"op": "Read", "value": 10}, {"op": "Write", "value": 5}]}}
        assert statporter._blkio_bytes(s) == (10, 5)
```

For the cleanup test, patch `statporter.get_client` to return a client whose `.containers.list()` first returns `[fake("demo-container"), fake("weather-app")]`, call `collect_metrics()`, then return only `[fake("weather-app")]`, call again, and assert `CPU_PERCENT.remove("demo_container")` was invoked (spy on the gauge, or read the registry and confirm the series is gone).

---

## Part 4 - CI integration

### File to create: `.github/workflows/unit-tests.yml`

A fast job with no Docker stack. Runs on pushes that touch the source modules and on PRs.

```yaml
---
name: CI - Unit Tests

"on":
  push:
    branches: [master]
    paths:
      - "weather-app/docker-src/**"
      - "weather-app/docker-final/statporter/**"
  pull_request:
    branches: [master]
  workflow_dispatch:

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    permissions:
      issues: write # so the CI self-healing loop can open labeled issues
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Flask app unit tests
        run: |
          pip install -r weather-app/docker-src/requirements.txt pytest
          set -o pipefail
          pytest weather-app/docker-src/tests/ -v --tb=short 2>&1 | tee unit-output.txt

      - name: Statporter unit tests
        run: |
          pip install -r weather-app/docker-final/statporter/requirements.txt pytest
          set -o pipefail
          pytest weather-app/docker-final/statporter/tests/ -v --tb=short 2>&1 | tee -a unit-output.txt
```

The structured-issue / per-service-label steps from `integration-tests.yml` (Pass 2 of the service detector) can be reused here so unit failures open the same labeled tickets. That reuse is optional for a first cut and is the reason `CI_LOOP_DESIGN.md` was implemented before this suite.

### conftest.py per tree

Each new `tests/` dir needs a `conftest.py` that puts the module under test on `sys.path`, since the source files import flat (`import weather`, `import statporter`, `from logger import get_logger`):

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

For the Flask app tree, also set the playground env vars before import and expose the test client fixture here.

---

## Naming Convention (CI self-healing loop)

Per `CI_LOOP_DESIGN.md` Part 4, Pass 2 lowercases each `FAILED` line (full node id: file path + class + function) and matches it against each service's `terms`. The relevant terms are `weather_app`, `statporter`, `demo_container`. To guarantee correct labels:

- **weather.py / playground.py tests:** every test function name contains `weather_app` (with the underscore), e.g. `test_weather_app_playground_session_expires_after_idle`. The file path `weather-app/...` uses a hyphen and will NOT match `weather_app`, so the token must live in the function name.
- **statporter tests:** the path and class already contain `statporter`; no extra work needed.

A test that matches no term still opens a generic `[CI-NNNN]` issue and is never dropped.

---

## Testing Checklist

- [ ] `pytest weather-app/docker-src/tests/ -v` passes with no stack running and no Docker daemon required
- [ ] `pytest weather-app/docker-final/statporter/tests/ -v` passes with no stack running
- [ ] No unit test makes a real network call (all `requests.get` patched) or a real Docker call (all `get_client` patched)
- [ ] `get_weather` returns the friendly message for 404, non-404 HTTP error, connection error, and timeout, and never includes the api_key or raw exception tokens
- [ ] Passphrase grace period is asserted on both sides of the `GRACE_SECONDS` boundary
- [ ] Session expiry is asserted on both sides of `SESSION_IDLE_LIMIT`
- [ ] Stale-label cleanup asserts `gauge.remove` is called for a container that disappears between rounds
- [ ] Each test function name carries the correct service token (`weather_app` / `statporter`) for CI labeling
- [ ] `unit-tests.yml` triggers on `weather-app/docker-src/**` and `.../statporter/**`, and does NOT spin up the stack
- [ ] `pre-commit run --all-files` passes on all new files (black, flake8, prettier)

---

## What This Does Not Cover

- **Coverage thresholds / `pytest-cov` gating** - measuring and enforcing a coverage percentage is a separate enhancement; this suite targets the specific high-value branches, not a number.
- **`main.py` route unit tests** - the Flask routes are already covered server-side by `test_weather_app_pages.py` and `test_nginx.py` through the live stack; pulling them down to unit level is out of scope here.
- **demo-container `app.py`** - the stress/stop_stress threading is exercised by the destructive `test_alerting.py` lifecycle; a unit test of the busy-loop deadline is low value.
- **Reusing the full self-healing issue-creation block in `unit-tests.yml`** - wiring Pass 2 labeling into the unit workflow is noted as optional and can follow once the suite is green.
- **The integration layer** - `integration-tests.yml` and `docker-final/tests/` are unchanged; this is purely additive.
