# Playground Feature - PR Specification

**Status:** SHIPPED.
**Branch target:** `master`
**Estimated scope:** ~9 files created, ~8 files modified

---

## Purpose

The playground is an interactive demo page at `/playground` that allows recruiters to log in with a time-limited passphrase and observe the observability stack responding to real events in real time. It closes the "alertmanager goes nowhere" gap by making the full alerting loop visible and tangible: stop a container, watch the alert fire, restart the container, watch it resolve.

---

## Background Required

Before implementing, read:

- `CLAUDE.md` - architecture, conventions, gotchas
- `DESIGN.md` and `PRODUCT.md` - design system and brand strategy
- `weather-app/docker-src/main.py` - how routes are structured, how blueprints register
- `weather-app/docker-src/templates/about_me.html` - canonical template structure including navbar
- `weather-app/docker-src/static/styles.css` - full token set and dark mode implementation
- `weather-app/docker-final/docker-compose.yml` - current service definitions
- `weather-app/docker-final/prometheus/rules/alerts.yml` - existing alert rules
- `weather-app/docker-final/nginx/nginx.conf` - existing routing

---

## Architecture

```
Browser → /playground          → weather-app (playground.py, renders playground.html)
Browser → /playground/login    → weather-app (playground.py, renders playground_login.html)
Browser → /playground/passphrase → weather-app (admin endpoint, Bearer auth)
Browser → /api/playground/*    → weather-app (JSON API endpoints, session required)

weather-app → docker.sock (rw)                  → start/stop demo-container
weather-app → http://demo-container:8080/stress → trigger CPU spike
browser     → /prometheus/api/v1/alerts          → poll alert feed (every 10s, via JS)
```

`demo-container` is a disposable Flask app that exists solely as a toggle target and stress receiver. It runs no real work. Stopping and starting it during a demo does not affect any real service.

---

## Rolling Passphrase Design

The passphrase rotates every 4 hours automatically. No passphrase is ever stored in a database, log file, or environment variable - it is derived on demand from a secret seed. Cliff retrieves the current passphrase from a protected admin endpoint before sharing the playground link with a recruiter.

### How it works

```
PLAYGROUND_SECRET  (env var, 32+ char random string)
         │
         └─► HMAC-SHA256(secret, str(floor(unix_time / 14400)))
                    │
                    └─► base64url(digest)[0:14]  →  current passphrase
```

The time window ID (`floor(unix_time / 14400)`) changes every 4 hours. Anyone who knows the window ID and the secret can reproduce the passphrase - that is only the server.

### Grace period

A 5-minute overlap accepts both the current and previous window. A recruiter handed the passphrase at 3:58 PM is not locked out at 4:00 PM.

### Implementation

```python
import hmac
import hashlib
import base64
import os
import time

WINDOW_SECONDS = 4 * 3600   # 4 hours
GRACE_SECONDS  = 300         # 5-minute overlap

def _derive(secret: bytes, window_id: int) -> str:
    digest = hmac.new(secret, str(window_id).encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest)[:14].decode()

def valid_passphrases() -> list[str]:
    secret = os.environ["PLAYGROUND_SECRET"].encode()
    now    = time.time()
    cur    = int(now // WINDOW_SECONDS)
    passes = [_derive(secret, cur)]
    if (now - cur * WINDOW_SECONDS) < GRACE_SECONDS:
        passes.append(_derive(secret, cur - 1))
    return passes

def passphrase_info() -> dict:
    secret        = os.environ["PLAYGROUND_SECRET"].encode()
    now           = time.time()
    cur           = int(now // WINDOW_SECONDS)
    window_start  = cur * WINDOW_SECONDS
    next_rotation = window_start + WINDOW_SECONDS
    return {
        "current":               _derive(secret, cur),
        "seconds_until_rotation": int(next_rotation - now),
        "next":                  _derive(secret, cur + 1),
    }
```

### Admin endpoint

`GET /playground/passphrase`

Requires `Authorization: Bearer <PLAYGROUND_ADMIN_KEY>` header. Returns 401 if missing or wrong. Returns 200 with:

```json
{
  "current": "aB3xK9mQ2z7w4R",
  "seconds_until_rotation": 8134,
  "next": "zQ7mK2xB3w9aR4j"
}
```

Cliff bookmarks this URL and checks it before sending the playground link. He tells the recruiter: "Here is the passphrase - it is valid for up to 4 hours. Reach out if you need more time."

---

## Session Design

Sessions expire after **30 minutes of inactivity**, not 30 minutes from login. Every authenticated request updates a `last_active` timestamp. Any request where `time.time() - session['last_active'] > 1800` is treated as expired: clear the session, return 403 (for API endpoints) or redirect to login (for page routes).

```python
import time
from functools import wraps
from flask import session, abort, redirect, url_for

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("playground_auth"):
            abort(403)
        if time.time() - session.get("last_active", 0) > 1800:
            session.clear()
            abort(403)
        session["last_active"] = time.time()
        return f(*args, **kwargs)
    return decorated

def require_auth_redirect(f):
    """For page routes - redirects instead of 403."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("playground_auth"):
            return redirect(url_for("playground.login"))
        if time.time() - session.get("last_active", 0) > 1800:
            session.clear()
            return redirect(url_for("playground.login"))
        session["last_active"] = time.time()
        return f(*args, **kwargs)
    return decorated
```

---

## Files to Create

### 1. `weather-app/demo-container/Dockerfile`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir flask gunicorn
COPY app.py .
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "2", "app:app"]
```

### 2. `weather-app/demo-container/app.py`

A minimal Flask app with three endpoints.

**CRITICAL implementation constraint:** Use `threading.Event` to signal stop, not `threading.Lock`. A Lock blocks `stop_stress()` from acquiring the lock while the stress loop holds it - meaning a stop request while stress is running will hang. An Event can be cleared from any thread at any time without blocking.

**Event semantics:** `_stop_event.is_set()` means "stress is currently running." `set()` starts it, `clear()` stops it. The burn loop condition is `while stop_event.is_set()` - runs while set, exits when cleared. Do NOT invert this to `while not stop_event.is_set()` - that would cause `_burn()` to exit immediately on start.

```python
import threading
import time
from flask import Flask, jsonify

app = Flask(__name__)
_stop_event = threading.Event()

def _burn(stop_event: threading.Event) -> None:
    deadline = time.time() + 30
    while stop_event.is_set() and time.time() < deadline:
        pass  # busy loop - intentional CPU burn
    stop_event.clear()

@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"}), 200

@app.route("/stress", methods=["POST"])
def stress():
    if _stop_event.is_set():
        return jsonify({"status": "already running"}), 200
    _stop_event.set()
    threading.Thread(target=_burn, args=(_stop_event,), daemon=True).start()
    return jsonify({"status": "stress started"}), 200

@app.route("/stop_stress", methods=["POST"])
def stop_stress():
    _stop_event.clear()
    return jsonify({"status": "stopped"}), 200
```

### 3. `weather-app/docker-src/playground.py`

A Flask Blueprint. Register in `main.py` as `playground_bp`.

**Endpoints:**

`GET /playground` - requires auth (redirect to login if not). Queries Docker for current demo-container state. Renders `playground.html` with `container_state` ("running", "stopped", or "not_found").

`GET /playground/login` - renders `playground_login.html`. If already authenticated, redirect to `/playground`.

`POST /playground/login` - checks `request.form["password"]` against `valid_passphrases()` using `hmac.compare_digest` for constant-time comparison. On match: sets `session["playground_auth"] = True`, `session["last_active"] = time.time()`, redirects to `/playground`. On mismatch: re-renders login with `error=True`, status 401.

`POST /playground/logout` - clears session entirely, redirects to `/playground/login`.

`GET /playground/passphrase` - admin endpoint. Checks `Authorization` header for `Bearer <PLAYGROUND_ADMIN_KEY>`. Returns 401 if missing or wrong. Returns `passphrase_info()` as JSON. This endpoint must not update `session["last_active"]` - it is not a recruiter-facing endpoint.

`POST /api/playground/toggle` - requires auth (`require_auth`). Hardcodes container name to `"demo-container"` - ignores any request body. Gets container via `docker.from_env().containers.get("demo-container")`. If running: stops it. If stopped/exited: starts it. Returns `{"status": "stopped"|"started"}`, 200. Returns `{"error": "not_found"}`, 404 if container doesn't exist.

`POST /api/playground/stress` - requires auth. Makes `requests.post("http://demo-container:8080/stress", timeout=5)`. Returns `{"status": "stress started"}`, 200. Returns `{"error": "unreachable"}`, 502 on connection failure. Never uses `exec_run`.

`GET /api/playground/status` - requires auth. Returns:

```json
{
  "container": "running" | "stopped" | "not_found",
  "stress_active": true | false
}
```

Determine `stress_active` by calling `requests.get("http://demo-container:8080/stress_status", timeout=2)` if the container is running - or add a `GET /stress_status` endpoint to `demo-container/app.py` that returns `{"active": _stop_event.is_set()}`.

**Security guardrails - non-negotiable:**

- Toggle endpoint ignores any container name in the request. `"demo-container"` is hardcoded in the server.
- Stress endpoint calls `http://demo-container:8080` only. The URL is not configurable via any input.
- All `/api/playground/*` routes return 403 immediately if session is invalid or expired.
- `PLAYGROUND_SECRET` and `PLAYGROUND_ADMIN_KEY` must never appear in any log output.
- Login route must not log `request.form` or `request.data`.
- Use `hmac.compare_digest` for all passphrase comparisons - never `==`.

### 4. `weather-app/docker-src/templates/playground_login.html`

Follows the exact template structure of `weather_app.html`. Narrow `.container` (not `--wide`).

**Structure:**

- Navbar with all links including `/playground` (`aria-current="page"`)
- `<h1>Playground</h1>`
- `<p>Log in to interact with the observability stack in real time.</p>`
- If `error` is truthy: a `.note` callout - "Incorrect passphrase. Try again." Do not create a new error style; reuse `.note`.
- Form: `method="POST"`, `action="/playground/login"`
  - One `<label>` + `<input type="password" id="password" name="password" required autocomplete="current-password">`
  - Submit button: "Enter"
- Footer icons with `aria-label`

**Design requirements:** All colors via CSS custom properties. Dark mode works automatically. No hard-coded hex values.

### 5. `weather-app/docker-src/templates/playground.html`

Uses `.container--wide`. Navbar with `/playground` active.

**Page structure:**

```
<h1>Observability Playground</h1>

<p class="note">
  This container is a purpose-built dummy - stopping it triggers a real alert
  in Prometheus. Restarting it resolves the alert. The CPU spike drives the
  DemoContainerHighCPU rule above 80% for 30 seconds.
</p>

[Container Control section]
[Alert Feed section]
[Logout form]
```

**Container Control section:**

`<h2>demo-container</h2>`

Status badge: `<span id="status-badge">` - shows "Running" or "Stopped". Use CSS classes that stay within the token system:

```css
.badge {
  display: inline-block;
  font-size: 0.8rem;
  font-weight: 700;
  padding: 0.15rem 0.55rem;
  border-radius: 4px;
  letter-spacing: 0.05em;
}
.badge--running {
  background: var(--brand-blue-tint);
  color: var(--brand-blue-link);
  border: 1px solid var(--brand-blue-light);
}
.badge--stopped {
  background: var(--error-bg);
  color: var(--error-color);
  border: 1px solid var(--error-border);
}
```

Do not use raw green/red colors.

Two buttons:

- `<button id="btn-toggle">` - label is "Stop Container" when running, "Start Container" when stopped
- `<button id="btn-stress">` - "Spike CPU (30s)". Disabled when container is stopped. Shows "Stress Active" when stress is running.

**Alert Feed section:**

`<h2>Live Alerts</h2>`

`<div id="alert-feed" aria-live="polite" aria-label="Live alert feed">`

Populated and refreshed by JS. Empty state: `<p class="alert-feed__empty">No active alerts.</p>` in muted text.

Per alert:

```html
<div class="alert-item">
  <span class="alert-item__name">DemoContainerDown</span>
  <span class="alert-item__severity badge badge--stopped">warning</span>
  <span class="alert-item__state">firing</span>
  <p class="alert-item__description">...</p>
</div>
```

**Logout:**

```html
<form method="POST" action="/playground/logout">
  <button type="submit" class="btn-logout">Log Out</button>
</form>
```

Style `.btn-logout` as a secondary/ghost button using `--brand-blue-link` for border/text, transparent background.

**JavaScript requirements:**

- On page load: call `/api/playground/status`, set initial badge and button states
- Toggle click: POST `/api/playground/toggle`, update badge and button labels from response, enable/disable stress button
- Stress click: POST `/api/playground/stress`, change button text to "Stress Active", `setTimeout(30000)` to reset label
- Alert feed: `setInterval(() => fetchAlerts(), 10000)` - fetch `/prometheus/api/v1/alerts`, filter where `alert.state === "firing"`, render into `#alert-feed`
- All fetch calls: catch network errors, display inline error text, never throw uncaught exceptions
- Vanilla JS only - no external libraries
- On 403 response from any API call: redirect to `/playground/login` (session expired)

**Design alignment checklist for both templates:**

- All colors via CSS custom properties - no hard-coded hex values
- Dark mode automatic via `prefers-color-scheme` token overrides
- All interactive elements have `:focus-visible` styles (inherited from styles.css)
- `aria-label` on icon links, `aria-current="page"` on active nav link
- No `border-left` stripe patterns, no gradient text, no glassmorphism
- `prefers-reduced-motion` respected - no new animations

### 6. `weather-app/docker-final/logrotate/docker-containers`

Committed default logrotate config. Users copy to `/etc/logrotate.d/docker-containers` on the host. Ansible can override with environment-specific values.

```
/var/lib/docker/containers/*/*.log {
    daily
    size 50M
    rotate 7
    compress
    compresscmd /bin/gzip
    compressoptions -9
    delaycompress
    missingok
    notifempty
    copytruncate
    dateext
    dateformat -%Y%m%d-%H%M%S
}
```

Key decisions:

- `daily` AND `size 50M` - whichever comes first triggers rotation
- `rotate 7` - 7 archives kept (1 week at daily rotation)
- `compress` + `compresscmd gzip` - `.gz` archives (Docker log files are JSON, compress extremely well)
- `copytruncate` - truncates the live file rather than moving it, avoiding the need to signal Docker
- `dateext` + `dateformat` - archive names include timestamp, not just sequence number
- `delaycompress` - the most recent rotated file stays uncompressed for one cycle (useful for debugging)

Note in Ansible: override `daily`, `size`, and `rotate` values for production environments with different retention requirements.

---

## Files to Modify

### 7. `weather-app/docker-src/main.py`

Add after `app = Flask(...)` and `PrometheusMetrics(app)`:

```python
import os
from playground import playground_bp

app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-insecure-key")
if app.secret_key == "dev-only-insecure-key":
    logger.warning("FLASK_SECRET_KEY is not set - using insecure development default")
app.register_blueprint(playground_bp)
```

Add `/playground` and `/playground/login` to the request logging path map in `log_request()`:

```python
if path in ("/", "/about_me", "/resume", "/weather_app", "/playground", "/playground/login"):
    msg = f"{path} requested"
```

Add a guard for the login route so form data is never logged:

```python
elif path == "/playground/login" and method == "POST":
    msg = "Playground login attempt"  # never log request.form here
```

### 8. `weather-app/docker-src/requirements.txt`

Add:

```
docker==7.1.0
```

### 9. `weather-app/docker-final/docker-compose.yml`

**Add logging config to ALL services** (currently only weather-app has it). Use consistent values:

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "50m"
    max-file: "5"
```

Apply to: `reverse-proxy`, `weather-app`, `prometheus`, `grafana`, `loki`, `promtail`, `statporter`, `alertmanager`, `demo-container`.

**Add `demo-container` service:**

```yaml
demo-container:
  image: burningstar4/demo-container:latest
  container_name: demo-container
  restart: unless-stopped
  build:
    context: ../../demo-container/
  deploy:
    resources:
      limits:
        cpus: "1.0"
        memory: 128M
      reservations:
        cpus: "0.1"
        memory: 64M
  expose:
    - "8080"
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8080/healthz"]
    interval: 30s
    timeout: 5s
    retries: 3
    start_period: 10s
  logging:
    driver: "json-file"
    options:
      max-size: "50m"
      max-file: "5"
  labels:
    - "logging=true"
  networks:
    - monitoring
```

**Modify `weather-app` service** - add Docker socket mount and new env vars:

```yaml
weather-app:
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock # rw - required for playground container toggle
  environment:
    - FLASK_SECRET_KEY=${FLASK_SECRET_KEY}
    - PLAYGROUND_SECRET=${PLAYGROUND_SECRET}
    - PLAYGROUND_ADMIN_KEY=${PLAYGROUND_ADMIN_KEY}
```

### 10. `weather-app/docker-final/prometheus/rules/alerts.yml`

Add a new group `playground_alerts` after the existing groups:

```yaml
- name: playground_alerts
  rules:
    - alert: DemoContainerDown
      expr: (up{job="statporter"} == 1) and absent(container_cpu_percent{name="demo-container"})
      for: 60s
      labels:
        severity: warning
      annotations:
        summary: "demo-container is not running"
        description: "statporter is healthy but demo-container has been absent from metrics for more than 60 seconds."

    - alert: DemoContainerHighCPU
      expr: container_cpu_percent{name="demo-container"} > 80
      for: 30s
      labels:
        severity: warning
      annotations:
        summary: "demo-container CPU above 80%"
        description: "demo-container CPU has been above 80% for 30 seconds."
```

**Why this DemoContainerDown expression:** `absent(...)` alone fires when statporter goes down, not just when demo-container stops. Adding `(up{job="statporter"} == 1) and` ensures the alert only fires when statporter is actively scraping but sees no demo-container metric - meaning the container itself is down.

**Note on timing:** statporter scrapes every 30s (scrape_interval in prometheus.yml). After demo-container stops, the metric may persist for one scrape cycle before becoming absent. The 60s `for` duration absorbs this lag.

### 11. `weather-app/docker-final/nginx/nginx.conf`

Add two location blocks inside `server {}`, before `location /`:

```nginx
# Playground UI and login
location /playground {
  proxy_pass http://weather_app;
  proxy_set_header Host              $http_host;
  proxy_set_header X-Real-IP         $remote_addr;
  proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;
  proxy_set_header X-Forwarded-Host  $http_host;
  proxy_redirect off;
}

# Playground JSON API
location /api/playground/ {
  proxy_pass http://weather_app;
  proxy_set_header Host              $http_host;
  proxy_set_header X-Real-IP         $remote_addr;
  proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;
  proxy_set_header X-Forwarded-Host  $http_host;
  proxy_redirect off;
}
```

### 12. `weather-app/docker-final/.env.example`

Replace `PLAYGROUND_PASSWORD` with the three new variables:

```bash
# Flask session secret key - generate with:
#   python3 -c "import secrets; print(secrets.token_hex(32))"
FLASK_SECRET_KEY=change-me-generate-a-real-secret

# Playground rolling passphrase seed - generate with:
#   python3 -c "import secrets; print(secrets.token_hex(32))"
# This never changes unless you want to invalidate all existing passphrases.
PLAYGROUND_SECRET=change-me-generate-a-real-secret

# Playground admin key - protects GET /playground/passphrase
# Generate with: python3 -c "import secrets; print(secrets.token_urlsafe(32))"
PLAYGROUND_ADMIN_KEY=change-me-generate-a-real-secret
```

### 13. `Makefile`

Add:

```makefile
build-demo:
	docker build -t burningstar4/demo-container:latest weather-app/demo-container/

push-demo:
	docker push burningstar4/demo-container:latest

build-all: build-weather build-statporter build-demo

push-all: push-weather push-statporter push-demo
```

### 14. All existing templates - add `/playground` to navbar

Files:

- `weather-app/docker-src/templates/index.html`
- `weather-app/docker-src/templates/about_me.html`
- `weather-app/docker-src/templates/resume.html`
- `weather-app/docker-src/templates/weather_app.html`
- `weather-app/docker-src/templates/grafana.html`

Add `<a href="/playground">Playground</a>` to each `.navbar` div. Final order: About Me, Homelab Blog, Resume, Weather App, Playground, Grafana.

---

## New CI/CD Workflow

Create `.github/workflows/docker-build-demo-container.yml` following the same pattern as `docker-build-weather-app.yml`:

```yaml
name: Docker Build and Push - Demo Container

on:
  push:
    branches:
      - master
    paths:
      - "weather-app/demo-container/**"

jobs:
  build-demo-container:
    name: Build and Push Demo Container
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          username: ${{ vars.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: weather-app/demo-container/
          push: true
          tags: burningstar4/demo-container:latest
```

---

## Security Checklist

Before merging, verify every item:

- [ ] Toggle endpoint hardcodes `"demo-container"` - container name never comes from request input
- [ ] Stress endpoint URL is `http://demo-container:8080` - not configurable via any input
- [ ] All `/api/playground/*` routes return 403 immediately if session is invalid or expired
- [ ] Session inactivity timeout is enforced server-side (not just client-side)
- [ ] `PLAYGROUND_SECRET` does not appear in any log line - confirmed by reading log_request() and playground.py
- [ ] `PLAYGROUND_ADMIN_KEY` does not appear in any log line
- [ ] Login route does not log `request.form` or `request.data`
- [ ] All passphrase comparisons use `hmac.compare_digest` - no `==` operator on secret values
- [ ] `/playground/passphrase` returns 401 with no detail on wrong admin key (do not distinguish "wrong key" from "missing key")
- [ ] Docker socket mount on weather-app is rw and documented in comments in docker-compose.yml
- [ ] Bandit scan passes on `playground.py` - no B105/B106 (hardcoded password) findings
- [ ] `FLASK_SECRET_KEY` fallback logs a warning at startup - visible in `docker compose logs weather-app`

---

## Testing

See `TESTING_CHECKLIST.md` - Section 9 (Playground).

---

## Log Rotation Deployment

After deploying the stack:

```bash
# Copy the default logrotate config to the host
sudo cp weather-app/docker-final/logrotate/docker-containers /etc/logrotate.d/docker-containers
sudo chmod 644 /etc/logrotate.d/docker-containers

# Test the config
sudo logrotate --debug /etc/logrotate.d/docker-containers

# Force a run to verify
sudo logrotate --force /etc/logrotate.d/docker-containers
```

For Ansible-managed hosts, override the `daily` and `size` directives in the playbook vars rather than editing the committed default.

---

## How to Get the Current Passphrase

Before sending the playground link to a recruiter:

```bash
curl -s -H "Authorization: Bearer $PLAYGROUND_ADMIN_KEY" \
  http://your-domain/playground/passphrase | python3 -m json.tool
```

Response:

```json
{
  "current": "aB3xK9mQ2z7w4R",
  "seconds_until_rotation": 8134,
  "next": "zQ7mK2xB3w9aR4j"
}
```

Convert `seconds_until_rotation` to human-readable: `python3 -c "print(8134 // 3600, 'h', (8134 % 3600) // 60, 'm')"`.

Tell the recruiter: _"The passphrase is `aB3xK9mQ2z7w4R` - it is valid for approximately 2 hours 15 minutes. If you need more time, reach back out."_
