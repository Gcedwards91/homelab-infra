# CLAUDE.md — Homelab Infrastructure Project

Persistent context for Claude Code sessions. Read this before doing any work in this repo.

---

## Project Overview

A self-deployed DevOps portfolio and homelab showcase. A Flask web app serves as both the application and the portfolio surface — About Me, Blog, Resume, Weather App, and a Grafana observability dashboard, all running as a containerized stack behind nginx.

The site is simultaneously the artifact being presented and the proof of capability behind it. Design quality is evaluated as part of the engineering demonstration.

**Owner:** George "Cliff" Edwards (`gcedwards91@gmail.com`)
**DockerHub:** `burningstar4`
**GitHub:** `Gcedwards91/homelab-infra`

---

## Repository Layout

```
homelab-infra/
├── weather-app/
│   ├── docker-src/          # Flask app source — built into burningstar4/weather-app
│   │   ├── main.py          # Flask routes, PrometheusMetrics, request/response logging
│   │   ├── weather.py       # OpenWeatherMap API client
│   │   ├── logger.py        # JSON structured logger (python-json-logger)
│   │   ├── requirements.txt # Flask, Gunicorn, prometheus-flask-exporter
│   │   ├── templates/       # Jinja2 HTML templates
│   │   └── static/          # styles.css, favicon, icons/
│   └── docker-final/        # Production stack — docker compose up from here
│       ├── docker-compose.yml
│       ├── .env.example     # Copy to .env before running
│       ├── nginx/           # nginx.conf + empty.conf
│       ├── prometheus/      # prometheus.yml + rules/alerts.yml
│       ├── grafana/         # provisioning/, dashboards/, grafana.ini
│       ├── loki/            # loki-config.yaml
│       ├── promtail/        # promtail-config.yaml
│       └── alertmanager/    # alertmanager.yml
├── terraform/               # VM provisioning (Proxmox, Telmate provider)
├── lamp-ansible/            # Ansible LAMP stack playbooks
├── scripts/                 # Bash VM template prep scripts
├── PRODUCT.md               # Brand/design strategy (Impeccable teach output)
├── DESIGN.md                # Visual design system (Impeccable document output)
├── .impeccable/design.json  # Impeccable live panel sidecar
├── PLAYGROUND_RFC.md        # RFC for the playground feature (SHIPPED)
├── TESTING_CHECKLIST_RFC.md # End-to-end test checklist
├── CI_LOOP_RFC.md           # RFC for CI self-healing loop (SHIPPED)
├── TRACE_LOGS_RFC.md        # RFC for distributed tracing (planned)
├── Makefile                 # build-weather, build-statporter, push-*, all, scan
└── .pre-commit-config.yaml  # black, flake8, yamllint, prettier, end-of-file-fixer
```

---

## Stack Architecture

```
Browser → :80 → nginx (reverse-proxy)
                  ├── /           → weather-app:5000  (Flask/Gunicorn)
                  ├── /grafana/   → grafana:3000
                  └── /prometheus/ → prometheus:9090

prometheus ← weather-app:5000/metrics  (prometheus-flask-exporter)
prometheus ← grafana:3000/grafana/metrics
prometheus ← loki:3100/metrics
prometheus ← promtail:9080/metrics
prometheus ← statporter:9800/metrics   (custom Docker stats exporter)
prometheus → alertmanager:9093

loki ← promtail (Docker socket autodiscovery)
grafana → prometheus (datasource)
grafana → loki (datasource)
```

All services on a single `monitoring` bridge network. Nothing exposes ports except nginx on `:80`.

---

## Services

| Service        | Image                              | Purpose                                 |
| -------------- | ---------------------------------- | --------------------------------------- |
| reverse-proxy  | nginx:stable-alpine3.23            | Reverse proxy, sub-path routing         |
| weather-app    | burningstar4/weather-app:latest    | Flask portfolio app                     |
| demo-container | burningstar4/demo-container:latest | Disposable dummy — playground target    |
| prometheus     | prom/prometheus:v3.11.3            | Metrics collection and alerting         |
| grafana        | grafana/grafana:13.0.1-security-01 | Dashboard visualization                 |
| loki           | grafana/loki:3.7.2                 | Log aggregation                         |
| promtail       | grafana/promtail:3.6.11            | Log shipping from Docker socket         |
| statporter     | burningstar4/statporter:latest     | Custom Docker stats Prometheus exporter |
| alertmanager   | prom/alertmanager:v0.32.1          | Alert routing (null receiver)           |

All services have resource limits, restart policies, and `logging=true` labels for Promtail autodiscovery. Healthchecks are configured on all services except Loki (distroless image — no shell), Promtail, and reverse-proxy.

---

## Running Locally

```bash
cd weather-app/docker-final
cp .env.example .env
# Edit .env — set GRAFANA_ADMIN_PASSWORD at minimum
docker compose pull
docker compose up -d
docker compose ps   # verify all healthy
```

URLs once running:

- `http://localhost` — Portfolio app
- `http://localhost/grafana` — Grafana (read-only without login)
- `http://localhost/prometheus` — Prometheus UI

To build images locally before running:

```bash
make build-weather      # builds burningstar4/weather-app:latest
make build-statporter   # builds burningstar4/statporter:latest
make build-demo         # builds burningstar4/demo-container:latest
make build-all          # builds all three
```

---

## Flask Application (weather-app/docker-src/)

**Routes:**

- `GET /` — Blog index (index.html)
- `GET /about_me` — About Me / live cover letter (about_me.html)
- `GET /resume` — Resume page (resume.html)
- `GET /weather_app` — Weather lookup app (weather_app.html)
- `GET /grafana.html` — Grafana link page (grafana.html)
- `POST /weather` — JSON API, calls OpenWeatherMap
- `GET /healthz` — Health check, returns `{"status": "ok"}`
- `GET /metrics` — Prometheus metrics (prometheus-flask-exporter)
- `GET /favicon.ico` — Favicon

**Conventions:**

- All template renders go through `safe_render()` — catches `TemplateNotFound` and returns 404
- Every request gets a UUID in `g.request_id`, logged on both request and response
- Structured JSON logging via `python-json-logger`; logger setup in `logger.py`
- Prometheus metrics are auto-instrumented via `PrometheusMetrics(app)` at app init

**Blueprint registration pattern (for playground):**

```python
from playground import playground_bp
app.register_blueprint(playground_bp)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-insecure-key")
```

---

## Design System (Impeccable-based)

The UI was built and refined using the `/impeccable` skill. PRODUCT.md and DESIGN.md are the authoritative source. Key conventions:

### CSS Architecture

- Single shared stylesheet: `weather-app/docker-src/static/styles.css`
- CSS custom properties on `:root` for all tokens — no hard-coded values
- Page-specific styles (resume) live in `<style>` blocks within the template
- Prettier formats HTML/CSS on commit — 2-space indent, no trailing whitespace

### Design Tokens (`:root`)

```css
--brand-blue: #0058e6 /* primary accent, nav, buttons */ --brand-blue-dark: #0044b3
  /* hover/pressed states */ --brand-blue-light: #cce0ff /* passive tints */
  --brand-blue-tint: #f0f4ff /* callout backgrounds */ --brand-blue-link: #0058e6
  /* content links (overridden in dark mode) */ --text-primary: #333 /* body text */
  --text-secondary: #555 /* labels, supporting copy */ --text-muted: #717171
  /* timestamps, captions — min 4.5:1 contrast */ --border-light: #eee /* dividers */
  --border-input: #ccc /* input borders at rest */ --background-page: #f4f6f9 /* page background */
  --background-card: #ffffff /* card/container background */ --error-color: #b91c1c /* error text */
  --error-bg: #fef2f2 /* error background */ --error-border: #fecaca /* error border */
  --border-radius-card: 12px /* containers */ --border-radius-input: 8px /* inputs, buttons */
  --shadow-card: 0 0 20px rgba(0, 0, 0, 0.05) --tooltip-bg: #333333 --tooltip-text: #ffffff;
```

### Dark Mode

Implemented via `@media screen and (prefers-color-scheme: dark)` at the bottom of `styles.css`. Token overrides only — no JS. Print styles always use light mode (`@media screen` scoping).

Dark mode overrides page/card backgrounds to charcoal family (`#14161d` / `#1e2029`), text to near-white scale, and `--brand-blue-link` to `#7dafff` (8.13:1 contrast on dark bg). Nav stays Blueprint Blue in both modes.

### Absolute Bans

- No `border-left` or `border-right` > 1px as colored accent (side-stripe pattern)
- No gradient text (`background-clip: text`)
- No glassmorphism
- No `#000` or `#fff` as raw values — use tokens
- Global `ul { list-style: none }` is a reset — any semantic bullet list must explicitly set `list-style: disc`

### Nav

Blueprint Blue background, white bold text, 12px radius (matches card). Links have `padding: 0.35rem 0.5rem` for touch target size. Focus ring is white (`rgba(255,255,255,0.85)`) not blue-on-blue.

### Callout/Note

`.note` uses `background-color: var(--brand-blue-tint)` + `border: 1px solid var(--brand-blue-light)`. No `border-left` stripe — that pattern was removed.

### Line Length

Narrative prose (About Me sections, blog posts) is capped at `max-width: 68ch`. Resume summary is also capped. The wide container (`.container--wide`) itself stays at `max-width: 900px` — only prose paragraphs get the ch cap.

### Accessibility

- WCAG AA target throughout
- All interactive elements have `:focus-visible` styles
- `prefers-reduced-motion` block suppresses all animations
- `role="alert"` and `aria-live` on dynamic regions in weather app
- Footer icon links use `aria-label` with descriptive text; icons are `aria-hidden="true"`
- Tooltip triggers have `tabindex="0"` and respond to focus/click/tap in addition to hover

---

## Naming Conventions

**Commit messages:** conventional commits — `feat:`, `fix:`, `docs:`, `chore:`, `test:`. Body explains the why. Co-authored with Claude via `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`.

**CSS classes:** BEM-adjacent. Component block (`experience-entry`), element separator `__` (`experience-entry__role`), modifier separator `--` (`container--wide`, `btn-download--primary`).

**Python:** snake_case throughout. Flask routes use snake_case function names matching route segments.

**Docker image tags:** `burningstar4/<name>:latest` — no versioned tags currently.

**Template naming:** flat, underscore-separated (`about_me.html`, `weather_app.html`, `playground_login.html`).

---

## CI/CD Pipeline

All workflows trigger on push to `master` (and PRs where applicable).

| Workflow                          | Trigger                                                                                     | What it does                                                                                                                                      |
| --------------------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `docker-build-weather-app.yml`    | push to `weather-app/docker-src/**`                                                         | Builds and pushes `burningstar4/weather-app:latest`                                                                                               |
| `docker-build-statporter.yml`     | push to `weather-app/docker-final/statporter/**`                                            | Builds and pushes `burningstar4/statporter:latest`                                                                                                |
| `docker-build-demo-container.yml` | push to `weather-app/demo-container/**`                                                     | Builds and pushes `burningstar4/demo-container:latest`                                                                                            |
| `format_and_lint-test.yml`        | all pushes                                                                                  | Black, Flake8, Prettier, Hadolint, yamllint                                                                                                       |
| `security_lint.yml`               | all pushes                                                                                  | Bandit, Trivy, ShellCheck, Gitleaks, npm audit                                                                                                    |
| `shellcheck.yml`                  | all pushes                                                                                  | ShellCheck on `.sh` files                                                                                                                         |
| `integration-tests.yml`           | push to `weather-app/docker-final/**`, `weather-app/demo-container/**`; `workflow_dispatch` | Scans images for CVEs (own-image blocks CI; vendor-image opens issue), spins up full stack, runs pytest, opens structured GitHub issue on failure |
| `targeted-test.yml`               | `workflow_dispatch` only                                                                    | Runs tests for a single service; auto-closes or comments on the linked issue                                                                      |

**Secrets required in GitHub:**

- `DOCKERHUB_TOKEN`
- `GITLEAKS_LICENSE_KEY` (optional — Gitleaks runs without it)

**Variables required in GitHub:**

- `DOCKERHUB_USERNAME`

Pre-commit hooks run locally before commit: `end-of-file-fixer`, `trailing-whitespace`, `check-yaml`, `black`, `flake8`, `yamllint`, `prettier`, `codespell` (commit-msg stage). Prettier reformats HTML/CSS/JSON/Markdown — always re-stage after a failed commit and commit again. The `codespell` hook runs only at commit-msg time and requires `pre-commit install --hook-type commit-msg` on first setup.

---

## Known Environment Gotchas

1. **Prettier reformats on commit.** When a commit fails due to Prettier, the files are already fixed in the working tree. Re-stage the modified files and commit again — do not amend.

2. **Global `ul { list-style: none }`** in styles.css resets bullets sitewide. Any new template with semantic bullet lists must explicitly set `list-style: disc` on the `ul`.

3. **Prometheus scrapes weather-app at `:5000/metrics`** — the prometheus-flask-exporter auto-mounts this route. Do not add a manual `/metrics` route. The nginx `location = /metrics` block returns 403 to external clients; Prometheus bypasses nginx by scraping the container directly at `:5000`.

4. **alertmanager.yml uses null receiver.** All alerts are collected but go nowhere. This is intentional — the playground demonstrates the alerting loop visually without requiring external notification credentials.

5. **Docker socket access.** statporter mounts `/var/run/docker.sock` read-only. weather-app mounts it read-write for the playground container toggle. These are separate mount declarations — statporter's is `:ro`, weather-app's is default (rw). The RW mount is the highest blast-radius element in the stack; the hardcoded `DEMO_CONTAINER = "demo-container"` constant is the only scope limiter.

6. **Playground service-to-service address.** The stress endpoint in `playground.py` calls `http://demo-container:8080/stress` — that is the internal Docker network address, not localhost. `demo-container` is on the same `monitoring` bridge as `weather-app`. Never use `localhost` or `127.0.0.1` for this call.

7. **Log rotation.** Docker's built-in json-file rotation (`max-size: 50m`, `max-file: 5`) manages per-container log size. A host-level logrotate config at `weather-app/docker-final/logrotate/docker-containers` handles time-based rotation — copy it to `/etc/logrotate.d/` on the host.

8. **`.env` is gitignored.** `.env.example` is the committed template. Never commit `.env`. `GRAFANA_ADMIN_PASSWORD`, `FLASK_SECRET_KEY`, `PLAYGROUND_SECRET`, and `PLAYGROUND_ADMIN_KEY` must all be set before `docker compose up`.

9. **Grafana provisioning.** Dashboards and datasources are provisioned as code from `grafana/provisioning/`. Manual changes in the Grafana UI are not persisted across container restarts unless the provisioning files are updated. Only one dashboard provider file must exist in `grafana/provisioning/dashboards/` — Grafana 13 raises "Cannot change resource manager" and fails to load all dashboards if two providers point at the same path.

10. **statporter scrape interval is 10s, timeout 5s** — the background collector thread makes scrapes return in ~50ms, so the timeout is not a constraint. Do not raise the scrape_interval without also adjusting the collection loop's `SCRAPE_INTERVAL` env var.

11. **statporter uses underscores in label values.** Container names with hyphens are converted: `demo-container` → `name="demo_container"`, `weather-app` → `name="weather_app"`. Use underscores in all PromQL queries and alert expressions that filter by `name=`. The Docker SDK still uses the hyphenated name for `containers.get()`.

12. **`color-scheme: light dark`** is declared on `:root`. This tells browsers to render scrollbars, form controls, and OS-native UI in the appropriate theme.

13. **Loki and Tempo are distroless images.** `grafana/loki:3.7.2+` and `grafana/tempo:2.10.0+` have no shell, no `wget`, no `curl`, no `nc` — nothing to exec into. Docker healthchecks cannot be configured for either. Grafana, Promtail, and otel-collector use `depends_on: condition: service_started` (not `service_healthy`) for both. In CI, Loki readiness is verified by polling `http://loki:3100/ready` via `docker exec prometheus wget`; Tempo readiness via `http://tempo:3200/ready` the same way (Prometheus is Alpine and has wget). The loki-config.yaml sets `join_after: 0s` and `min_ready_duration: 0s` so the ingester ring goes ACTIVE immediately on single-node startup.

---

## Key Deliberate Trade-offs

- **No versioned image tags.** `:latest` is intentional for a single-person portfolio project. A versioning scheme adds CI complexity with no operational benefit at this stage.
- **Alertmanager null receiver.** Alerts fire and are visible in Prometheus and the upcoming playground, but no external notification is wired. This avoids requiring external credentials (SMTP, PagerDuty) for local or demo use.
- **No HTTPS in docker-compose.** TLS is deferred to the AWS deployment (ACM + ALB). Local dev runs plain HTTP on `:80`.
- **Single Compose file.** No dev/prod split. The same compose file runs locally and will be adapted for AWS ECS/EKS.
- **Session auth for playground** (not JWT or OAuth). The playground is behind a passphrase, not a full auth system. It is a demo surface, not a multi-user application.

---

## In-Progress and Deferred Work

### Playground Feature (SHIPPED)

Interactive demo page at `/playground`. Implementation lives in `playground.py` (Blueprint) and `demo-container/app.py`.

- Log in with a rolling time-limited passphrase (4-hour windows, HMAC-derived)
- Stop/start `demo-container` — triggers `DemoContainerDown` alert within ~90 seconds
- Spike CPU for 60 seconds — triggers `DemoContainerHighCPU` alert within ~60 seconds
- Live alert feed polls `/prometheus/api/v1/alerts` every 10 seconds

**Auth design:** Passphrase derived via HMAC-SHA256 of `PLAYGROUND_SECRET` + current time window. Never stored. Admin retrieves current passphrase via `GET /playground/passphrase` (Bearer `PLAYGROUND_ADMIN_KEY`). 5-minute grace period at window boundaries. Sessions expire after 30 minutes of inactivity.

**Key implementation constraints:**

- CPU stress uses `threading.Event` — `is_set()` means stress is running, `clear()` stops it. `_burn()` loop: `while stop_event.is_set() and time.time() < deadline`. Do NOT invert this.
- All passphrase comparisons use `hmac.compare_digest` — never `==`
- Login route must never log `request.form`
- Toggle endpoint hardcodes `DEMO_CONTAINER = "demo-container"` — never uses container name from request input

**DemoContainerDown alert expression:**

```promql
(up{job="statporter"} == 1) and on() absent(container_cpu_percent{name="demo_container"})
```

`on()` is required — `absent()` returns `{name="demo_container"}` while the left side returns `{job="statporter", instance=...}`. Without `on()`, the label sets never match and the `and` returns nothing. `demo_container` uses an underscore (statporter naming convention).

**statporter stale gauge fix:** When a container stops, statporter's `collect_metrics()` actively removes label sets for containers no longer in `containers.list()` using `gauge.remove(name)`. This ensures `absent()` fires correctly — without this, Prometheus gauges retain their last value indefinitely and `absent()` never returns 1.

### AWS Deployment (deferred)

- ECS or EKS
- ALB for load balancing
- ACM for TLS
- Route53 for DNS
- Secrets Manager replacing `.env`
- Terraform-managed end to end

### Certifications (in progress)

- AWS Solutions Architect Associate (Udemy, active)
- CKA (planned)

### Resume Files (deferred)

The resume page is built and styled. The download buttons link to:

- `weather-app/docker-src/static/Cliff_Edwards_Resume.pdf`
- `weather-app/docker-src/static/Cliff_Edwards_Resume.docx`

Neither file is committed. Drop them into `static/` to activate the download buttons.

### Tests (integration tests shipped — unit tests still needed)

Integration tests exist at `weather-app/docker-final/tests/test_stack_startup.py` and run in CI via `integration-tests.yml`. They cover stack startup and health checks (TESTING_CHECKLIST.md sections 1.1–1.4) and statporter scrape performance.

Still needed:

- `pytest` suite for Flask routes (`main.py`) — status codes, healthz, weather error handling
- Playground auth unit tests — passphrase derivation, window boundary/grace period, session expiry
- `weather.py` unit tests — mock `requests.get`, assert error messages don't leak the API key URL
- statporter unit tests — `_cpu_percent()`, `_blkio_bytes()`, stale label cleanup logic

New test files must follow the naming convention in `CI_LOOP_RFC.md` Part 4 — file and class names must include the service name for the CI self-healing loop to apply correct labels on failure.

### Security (session cookie hardening — deferred to AWS)

`SESSION_COOKIE_SECURE = True` should be set once the stack is behind ACM/HTTPS. Incorrect to set locally (HTTP). Add to app config at AWS deployment time alongside Secrets Manager migration.
