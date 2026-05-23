# End-to-End Testing Checklist

Use this checklist before any significant merge or deployment. Work through it top to bottom — each section assumes the previous sections passed.

Mark each item: `[x]` pass, `[-]` skip with reason, `[!]` fail (note the failure).

---

## Prerequisites

```bash
cd weather-app/docker-final
cp .env.example .env        # if .env doesn't exist
# Verify .env has real values for:
#   GRAFANA_ADMIN_USER, GRAFANA_ADMIN_PASSWORD
#   FLASK_SECRET_KEY, PLAYGROUND_SECRET, PLAYGROUND_ADMIN_KEY
docker compose down -v      # clean slate
docker compose pull         # pull latest images
```

---

## 1. Stack Startup and Health Checks

### 1.1 All services come up

```bash
docker compose up -d
sleep 30
docker compose ps
```

- [ ] `reverse-proxy` — status Up, no restart loops
- [ ] `weather-app` — status Up, no restart loops
- [ ] `prometheus` — status Up (healthy)
- [ ] `grafana` — status Up (healthy)
- [ ] `loki` — status Up, no restart loops (distroless — no healthcheck)
- [ ] `promtail` — status Up, no restart loops
- [ ] `statporter` — status Up (healthy)
- [ ] `alertmanager` — status Up (healthy)
- [ ] `demo-container` — status Up (healthy)

### 1.2 Healthchecks pass

```bash
docker inspect --format='{{.Name}} {{.State.Health.Status}}' $(docker compose ps -q)
```

- [ ] prometheus — `healthy`
- [ ] grafana — `healthy`
- [ ] statporter — `healthy`
- [ ] alertmanager — `healthy`
- [ ] demo-container — `healthy`

Loki, Promtail, and reverse-proxy have no Docker healthcheck. Verify Loki is serving:

```bash
docker exec prometheus wget -q -O- http://loki:3100/ready
```

- [ ] Returns `ready`

### 1.3 No container has restarted unexpectedly

```bash
docker compose ps --format "table {{.Name}}\t{{.Status}}"
```

- [ ] No `Restarting` status on any container
- [ ] Restart count is 0 for all containers (`docker inspect <name> | grep RestartCount`)

### 1.4 Logs are clean on startup

```bash
docker compose logs --no-color 2>&1 | grep -iE "error|fatal|panic|exception" | grep -v "level=info"
```

- [ ] No unexpected ERROR or FATAL log lines across all containers

---

## 2. Weather App — All Pages

### 2.1 Page loads

For each URL, verify: HTTP 200, page renders, navbar is present with all links:

- [ ] `http://localhost` — Blog index page loads, at least 2 blog posts visible
- [ ] `http://localhost/about_me` — About Me loads, all sections visible, tooltips render
- [ ] `http://localhost/resume` — Resume page loads, all sections visible (Summary, Skills, Experience, Projects, Education), bullet points have markers, download buttons present
- [ ] `http://localhost/weather_app` — Weather form loads, all form fields present

### 2.2 Navbar

On every page:

- [ ] All navbar links are present: About Me, Homelab Blog, Resume, Weather App, Playground, Grafana
- [ ] Navbar links are functional — clicking each navigates correctly

### 2.3 Weather lookup

- [ ] Enter a valid city name (e.g. "Atlanta") and a valid OpenWeatherMap API key, submit
- [ ] Weather data appears: city name, temperature, feels like, condition, humidity, wind speed
- [ ] No `innerHTML` injection — weather data renders as plain text
- [ ] Enter an invalid city name — error message appears in the error div (not an unhandled exception)
- [ ] Enter no location — browser-level required field validation fires before submission

### 2.4 Error states

- [ ] Weather API returns error — `#error` div shows user-friendly message, not raw JSON
- [ ] Submit button shows "Fetching..." while request is in flight
- [ ] Submit button re-enables after response (success or error)
- [ ] Clicking submit rapidly multiple times — only one request fires at a time (button disables on click)

### 2.5 Resume downloads _(requires files in static/)_

- [ ] "Download PDF" button — browser triggers download of `Cliff_Edwards_Resume.pdf`
- [ ] "Download DOCX" button — browser triggers download of `Cliff_Edwards_Resume.docx`

### 2.6 Dark mode

- [ ] Set OS to dark mode — all pages switch to dark theme automatically
- [ ] No light-mode colors bleed through in dark mode (check nav, cards, text, error states)
- [ ] Return OS to light mode — pages return to light theme

### 2.7 Mobile responsiveness

Resize browser to 375px width or use DevTools mobile emulation:

- [ ] Navbar wraps without horizontal scroll
- [ ] Container padding reduces (no content clipping)
- [ ] Skills grid on resume collapses to single column
- [ ] No horizontal scrollbar on any page

### 2.8 Health check

```bash
curl http://localhost/healthz
```

- [ ] Returns `{"status": "ok"}` with HTTP 200

---

## 3. Observability Stack

### 3.1 Prometheus targets

Open `http://localhost/prometheus/targets`:

- [ ] `prometheus` — UP
- [ ] `weather_app` — UP
- [ ] `grafana` — UP
- [ ] `loki` — UP
- [ ] `promtail` — UP
- [ ] `statporter` — UP
- [ ] No target is in `DOWN` state

### 3.2 Alert rules loaded

Open `http://localhost/prometheus/rules`:

- [ ] `container_alerts` group is present with 3 rules: ContainerDown, ContainerHighMemory, ContainerHighCPU
- [ ] `stack_alerts` group is present with 2 rules: LokiIngestStopped, WeatherAppHighErrorRate
- [ ] `playground_alerts` group is present with 2 rules: DemoContainerDown, DemoContainerHighCPU
- [ ] All rules show state `inactive` (no false alerts at rest)

### 3.3 AlertManager reachable

```bash
curl http://localhost:9093/-/healthy
```

Or open `http://localhost/prometheus/config` and verify alertmanager target is listed.

- [ ] AlertManager is reachable from Prometheus (`alertmanager:9093`)

### 3.4 Grafana dashboards

Open `http://localhost/grafana`:

- [ ] Grafana loads without login (anonymous viewer access)
- [ ] At least one dashboard is listed in the dashboards panel
- [ ] Container metrics dashboard renders — CPU, memory, network panels show data
- [ ] No datasource errors (red exclamation marks on panels)
- [ ] Loki logs panel shows recent log lines from at least one container

### 3.5 Prometheus metrics from Flask

```bash
curl http://localhost/metrics | grep flask_http
```

- [ ] `flask_http_request_total` metric is present with label dimensions
- [ ] `flask_http_request_duration_seconds` metric is present
- [ ] At least one `status="200"` label combination shows a count > 0

### 3.6 Loki receiving logs

In Grafana Explore, query: `{container_name=~".+"}` with last 5 minutes:

- [ ] Log lines are present from `weather-app`
- [ ] Log lines include structured JSON fields (not raw strings)
- [ ] Log lines include `request_id` field from Flask logging middleware

---

## 4. Alerting

### 4.1 ContainerDown alert fires and resolves

```bash
docker stop loki
```

Wait 2 minutes (alert has `for: 2m`), then check `http://localhost/prometheus/alerts`:

- [ ] `ContainerDown` alert appears in FIRING state with `job="loki"`
- [ ] AlertManager receives the alert (check `http://localhost:9093/#/alerts`)

```bash
docker start loki
```

Wait 2 minutes, recheck:

- [ ] `ContainerDown` alert resolves (disappears from FIRING)

Restore:

```bash
# Verify loki is ready before continuing (distroless — no Docker healthcheck)
docker exec prometheus wget -q -O- http://loki:3100/ready
```

### 4.2 ContainerHighMemory alert (manual verify — skip in standard runs)

- [ ] Alert rule expression is syntactically valid (check Prometheus rules page, no error on the rule)

### 4.3 DemoContainerDown fires and resolves

```bash
# Via playground UI or directly:
docker stop demo-container
```

Wait 60 seconds (alert has `for: 60s`), then check `/prometheus/alerts`:

- [ ] `DemoContainerDown` alert appears in FIRING state
- [ ] Alert annotation text is correct: "demo-container is not running"

```bash
docker start demo-container
```

Wait 60 seconds, recheck:

- [ ] `DemoContainerDown` alert resolves

### 4.4 DemoContainerHighCPU fires and resolves

Trigger via the playground UI "Spike CPU" button. To trigger directly, exec into a
container on the `monitoring` network — `demo-container:8080` is not reachable from the
host:

```bash
docker exec weather-app curl -s -X POST http://demo-container:8080/stress
```

Wait ~30 seconds (alert has `for: 10s`; allow time for the scrape cycle to register
CPU above 80%), check `/prometheus/alerts`:

- [ ] `DemoContainerHighCPU` alert appears in FIRING state
- [ ] `container_cpu_percent{name="demo_container"}` metric is above 80 in Prometheus

Wait for stress to end (60s timeout), wait another 30s:

- [ ] `DemoContainerHighCPU` alert resolves

---

## 5. CI/CD Pipeline

### 5.1 Format and lint workflow

Push a trivial change (add a comment, remove it) to a Python or HTML file in `weather-app/docker-src/`:

- [ ] `format_and_lint-test.yml` triggers on GitHub Actions
- [ ] Black step passes
- [ ] Flake8 step passes
- [ ] Prettier step passes
- [ ] Hadolint step passes on both Dockerfiles
- [ ] yamllint step passes

### 5.2 Security lint workflow

- [ ] `security_lint.yml` triggers on push to master
- [ ] Bandit passes (no high-severity findings in `weather-app/docker-src/` or `statporter/`)
- [ ] Trivy config scan passes (no critical misconfigurations)
- [ ] ShellCheck passes on all `.sh` files
- [ ] Gitleaks passes (no secrets detected)

### 5.3 Docker build workflow triggers correctly

Make a change to `weather-app/docker-src/main.py` (e.g. add/remove a comment):

- [ ] `docker-build-weather-app.yml` triggers
- [ ] Build succeeds and image pushes to `burningstar4/weather-app:latest`

Make a change outside `weather-app/docker-src/` (e.g. update README):

- [ ] `docker-build-weather-app.yml` does NOT trigger

### 5.4 ShellCheck

```bash
find . -name "*.sh" -not -path "*/node_modules/*" | xargs shellcheck -x -e SC1091
```

- [ ] No ShellCheck errors on any `.sh` file

### 5.5 Demo container build workflow

Make a change to `weather-app/demo-container/app.py`:

- [ ] `docker-build-demo-container.yml` triggers
- [ ] Build succeeds and image pushes to `burningstar4/demo-container:latest`

---

## 6. Nginx Routing

```bash
# Test each location block directly
curl -I http://localhost/                       # → Flask app (200)
curl -I http://localhost/about_me               # → Flask app (200)
curl -I http://localhost/resume                 # → Flask app (200)
curl -I http://localhost/weather_app            # → Flask app (200)
curl -I http://localhost/healthz                # → Flask app (200, {"status":"ok"})
curl -I http://localhost/grafana/               # → Grafana (200 or 302)
curl -I http://localhost/prometheus/            # → Prometheus (200)
curl -I http://localhost/playground             # → Flask playground (200 or 302 to login)
curl -I http://localhost/api/playground/status  # → 403 if not authenticated
```

- [ ] `/` routes to Flask (check response header `X-Request-ID` is present — set by Flask middleware)
- [ ] `/grafana/` routes to Grafana (check Grafana-specific response headers)
- [ ] `/prometheus/` routes to Prometheus
- [ ] `/playground` routes to Flask
- [ ] `/api/playground/status` returns 403 without a session
- [ ] No location block leaks upstream error pages (502, 504)

---

## 7. Pre-Commit Hooks

### 7.1 Setup check

```bash
pre-commit --version
pre-commit run --all-files
```

- [ ] pre-commit is installed and working
- [ ] All hooks pass on the current state of the repo

### 7.2 Hook behavior on commit

Make a deliberate formatting violation (e.g. add trailing whitespace to a Python file), then try to commit:

- [ ] `end-of-file-fixer` or `trailing-whitespace` fires and blocks the commit
- [ ] After hook auto-fixes the file, re-staging and recommitting succeeds
- [ ] Prettier reformats HTML/CSS correctly (verify indentation and line endings)

### 7.3 Python quality

Make a deliberate Flake8 violation (e.g. unused import) and attempt to commit:

- [ ] Flake8 fires and blocks the commit with a clear error message
- [ ] After removing the violation and re-staging, commit succeeds

---

## 8. Environment

### 8.1 Required env vars present

```bash
# All of these must be set in .env
grep -E "^(GRAFANA_ADMIN_USER|GRAFANA_ADMIN_PASSWORD|GRAFANA_URL|PROMETHEUS_URL)=" weather-app/docker-final/.env
```

- [ ] `GRAFANA_ADMIN_USER` is set (not empty, not "changeme")
- [ ] `GRAFANA_ADMIN_PASSWORD` is set (not empty, not "changeme")
- [ ] `GRAFANA_URL` is set
- [ ] `PROMETHEUS_URL` is set
- [ ] `FLASK_SECRET_KEY` is set to a real secret (not the default placeholder)
- [ ] `PLAYGROUND_SECRET` is set (not the default placeholder)
- [ ] `PLAYGROUND_ADMIN_KEY` is set

### 8.2 .env is not committed

```bash
git ls-files weather-app/docker-final/.env
```

- [ ] Output is empty — `.env` is not tracked by git

### 8.3 No secrets in git history

```bash
git log --all --full-history --oneline | head -50
git grep -i "password\|secret\|api.key\|token" -- "*.yml" "*.yaml" "*.env*" "*.py"
```

- [ ] No actual secret values appear in committed files
- [ ] `.env.example` contains only placeholder values
- [ ] No API keys, passwords, or tokens in commit history (Gitleaks CI check is the authoritative scan)

### 8.4 Grafana admin login works

- [ ] Log into Grafana at `http://localhost/grafana` with the credentials from `.env`
- [ ] Admin panel is accessible
- [ ] Datasources (Prometheus, Loki) show green status

---

## 9. Playground Feature

### 9.1 Stack startup with playground

```bash
docker compose up -d
docker compose ps
```

- [ ] `demo-container` starts and reaches `healthy` state
- [ ] `weather-app` mounts `/var/run/docker.sock` (verify: `docker inspect weather-app | grep docker.sock`)
- [ ] `weather-app` has `FLASK_SECRET_KEY`, `PLAYGROUND_SECRET`, and `PLAYGROUND_ADMIN_KEY` in environment

### 9.2 Auth gate and rolling passphrase

Get the current passphrase via the admin endpoint:

```bash
CURRENT_PASS=$(curl -s -H "Authorization: Bearer $PLAYGROUND_ADMIN_KEY" \
  http://localhost/playground/passphrase | python3 -c "import sys,json; print(json.load(sys.stdin)['current'])")
```

- [ ] Admin endpoint returns 401 with wrong or missing `Authorization` header
- [ ] Admin endpoint returns JSON with `current`, `seconds_until_rotation`, and `next` keys

```bash
curl -I http://localhost/playground
```

- [ ] Without a session: response is 302 redirect to `/playground/login`

```bash
curl -c cookies.txt -b cookies.txt -X POST http://localhost/playground/login \
  -d "password=wrongpassword"
```

- [ ] Wrong passphrase: response is 401, login page re-renders with `.note` error callout

```bash
curl -c cookies.txt -b cookies.txt -X POST http://localhost/playground/login \
  -d "password=$CURRENT_PASS"
```

- [ ] Correct passphrase: response is 302 redirect to `/playground`, session cookie is set

**Passphrase rotation (manual — run near a 4-hour window boundary):**

- [ ] At rotation: old passphrase is rejected, new passphrase (from admin endpoint) is accepted
- [ ] Within 5-minute grace period: both old and new passphrases are accepted

**Session inactivity timeout:**

```bash
# Log in, then wait 31 minutes without activity
curl -c cookies.txt -b cookies.txt -X GET http://localhost/api/playground/status
# (wait 31 minutes)
curl -c cookies.txt -b cookies.txt -X GET http://localhost/api/playground/status
```

- [ ] After 30 minutes of inactivity: API returns 403
- [ ] Active use (requests within each 30-minute window) keeps the session alive indefinitely

### 9.3 Unauthenticated API access

```bash
curl -I http://localhost/api/playground/status
curl -I http://localhost/api/playground/toggle
curl -I http://localhost/api/playground/stress
```

- [ ] All three return 403 without a valid session cookie

### 9.4 Container toggle

In the browser, log into the playground:

- [ ] Status badge shows "Running" initially
- [ ] Click "Stop Container" — badge updates to "Stopped", button changes to "Start Container"
- [ ] "Spike CPU" button is disabled/grayed out when container is stopped
- [ ] Click "Start Container" — badge updates to "Running", Spike CPU button re-enables

Verify from the host:

```bash
docker inspect demo-container --format='{{.State.Status}}'
```

- [ ] Container state reflects the toggle action

### 9.5 DemoContainerDown alert lifecycle

After stopping demo-container via the toggle button:

- [ ] Within 60 seconds: `DemoContainerDown` appears in FIRING state at `/prometheus/alerts`
- [ ] Alert feed in the playground UI shows the alert within 10 seconds of it firing (next poll cycle)
- [ ] After restarting the container: alert resolves within 60 seconds
- [ ] Alert feed updates to show no active alerts (or "No active alerts." message)

### 9.6 CPU stress lifecycle

- [ ] Click "Spike CPU (60s)" — button changes to "Stress Active"
- [ ] Within ~30 seconds: `DemoContainerHighCPU` appears in FIRING state at `/prometheus/alerts` (alert has `for: 10s`; allow one scrape cycle to register CPU above 80%)
- [ ] Alert appears in playground alert feed within one poll cycle (10s)
- [ ] After 60 seconds: stress ends automatically, button resets to "Spike CPU (60s)"
- [ ] Alert resolves within 30 seconds of stress ending

### 9.7 Logout

- [ ] Click logout button — session is cleared, browser redirects to `/playground/login`
- [ ] After logout, `/api/playground/status` returns 403

### 9.8 Navbar

On every existing page:

- [ ] Playground link is present in the navbar: "Playground"
- [ ] Clicking "Playground" navigates to `/playground` (or login if not authenticated)

### 9.9 Design compliance

On the playground and playground login pages:

- [ ] All colors use CSS custom properties (no hard-coded hex values in inline styles)
- [ ] Dark mode works: enable OS dark mode, verify playground renders with dark token set
- [ ] Mobile: at 375px width, no horizontal scroll, buttons are tappable
- [ ] Status badge does not use raw red/green — uses design token classes

### 9.10 Security verification

- [ ] Attempt to toggle a container other than `demo-container` via direct API call:
  ```bash
  curl -c cookies.txt -b cookies.txt -X POST http://localhost/api/playground/toggle \
    -H "Content-Type: application/json" \
    -d '{"container": "prometheus"}'
  ```
  Expected: 403 response
- [ ] `PLAYGROUND_PASSWORD` does not appear in `docker compose logs weather-app`
- [ ] Stress endpoint URL is not configurable — only calls `http://demo-container:8080/stress`

### 9.11 Pre-commit and CI

- [ ] `pre-commit run --all-files` passes on all new and modified files
- [ ] `docker-build-weather-app.yml` triggers after pushing playground.py changes
- [ ] `docker-build-demo-container.yml` triggers after pushing demo-container/ changes
- [ ] Bandit passes on `playground.py` with no high-severity findings

---

## 10. Dependency Management

### 10.1 Dependabot coverage

Dependabot is configured in `.github/dependabot.yml` with weekly scans across five targets:

| Ecosystem        | Directory                              | What it watches                         |
| ---------------- | -------------------------------------- | --------------------------------------- |
| `github-actions` | `/`                                    | Action versions in all workflow files   |
| `docker`         | `/weather-app/docker-final`            | `image:` pins in `docker-compose.yml`   |
| `docker`         | `/weather-app/docker-src`              | `FROM` pin in weather-app Dockerfile    |
| `docker`         | `/weather-app/docker-final/statporter` | `FROM` pin in statporter Dockerfile     |
| `docker`         | `/weather-app/demo-container`          | `FROM` pin in demo-container Dockerfile |

- [ ] Verify Dependabot is enabled in GitHub repo settings: **Settings → Security → Dependabot alerts → Enable**
- [ ] Confirm Dependabot PRs appear weekly in the GitHub pull requests list
- [ ] Review and merge any open Dependabot PRs before a significant deployment

### 10.2 Container image CVE scan (integration tests)

The integration test workflow runs a Trivy image scan against every pulled image **before starting the stack**. This catches CVEs in upstream base images that Dependabot version bumps may not address immediately.

Scan policy: `--ignore-unfixed --severity CRITICAL` — only CRITICAL CVEs with a published fix trigger action.

Two scan paths run in sequence:

| Path                          | Images                                  | On finding                                                             |
| ----------------------------- | --------------------------------------- | ---------------------------------------------------------------------- |
| Own images (`burningstar4/*`) | weather-app, statporter, demo-container | CI fails + opens/updates `[OWN-CVE]` issue with `own-image-cve` label  |
| Vendor images (all others)    | nginx, prometheus, grafana, loki, etc.  | CI passes + opens/updates `[VENDOR-CVE]` issue with `vendor-cve` label |

- [ ] Confirm "Scan own images for critical CVEs" step passes in `integration-tests.yml` run
- [ ] Confirm "Scan vendor images for critical CVEs" step runs and reports cleanly
- [ ] If own-image scan fails: rebuild the affected image with `apt-get upgrade -y` and a newer base tag, then push
- [ ] If vendor scan reports findings: check Docker Hub for a newer tag and bump `docker-compose.yml`
- [ ] Run `make scan` locally before a significant deployment to verify all images clean
- [ ] Note: this scan is distinct from the `security_lint.yml` Trivy `config` scan, which checks Dockerfile/compose misconfigurations — not CVEs in pulled images

---

## Sign-off

| Section                   | Result | Notes |
| ------------------------- | ------ | ----- |
| 1. Stack startup          |        |       |
| 2. Weather app            |        |       |
| 3. Observability          |        |       |
| 4. Alerting               |        |       |
| 5. CI/CD                  |        |       |
| 6. Nginx routing          |        |       |
| 7. Pre-commit             |        |       |
| 8. Environment            |        |       |
| 9. Playground             |        |       |
| 10. Dependency management |        |       |

Date: \***\*\_\_\_\_\*\*** Tester: \***\*\_\_\_\_\*\***
