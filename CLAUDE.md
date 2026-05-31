# CLAUDE.md : Homelab Infrastructure Project

Persistent context for Claude Code sessions. Read this before doing any work in this repo.

---

## Project Overview

A self-deployed DevOps portfolio and homelab showcase. A Flask web app serves as both the application and the portfolio surface : About Me, Blog, Resume, Weather App, and a Grafana observability dashboard, all running as a containerized stack behind nginx.

The site is simultaneously the artifact being presented and the proof of capability behind it. Design quality is evaluated as part of the engineering demonstration.

**Owner:** George "Cliff" Edwards (`gcedwards91@gmail.com`)
**DockerHub:** `burningstar4`
**GitHub:** `Gcedwards91/homelab-infra`

---

## Repository Layout

```
homelab-infra/
├── weather-app/
│   ├── docker-src/          # Flask app source : built into burningstar4/weather-app
│   │   ├── main.py          # Flask routes, PrometheusMetrics, request/response logging
│   │   ├── weather.py       # OpenWeatherMap API client
│   │   ├── logger.py        # JSON structured logger (python-json-logger)
│   │   ├── requirements.txt # Flask, Gunicorn, prometheus-flask-exporter
│   │   ├── templates/       # Jinja2 HTML templates
│   │   └── static/          # styles.css, favicon, icons/
│   └── docker-final/        # Production stack : docker compose up from here
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
├── PLAYGROUND_DESIGN.md     # Design doc for the playground feature (SHIPPED)
├── TESTING_CHECKLIST.md     # End-to-end test checklist
├── CI_LOOP_DESIGN.md        # Design doc for CI self-healing loop (SHIPPED)
├── TRACE_LOGS_DESIGN.md     # Design doc for distributed tracing (SHIPPED)
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
grafana → tempo (datasource)

weather-app → otel-collector:4317 (OTLP gRPC spans)
statporter  → otel-collector:4317 (OTLP gRPC spans)
otel-collector → tempo:4317 (batched spans)
```

All services on a single `monitoring` bridge network. Nothing exposes ports except nginx on `:80`.

---

## Services

| Service        | Image                                        | Purpose                                 |
| -------------- | -------------------------------------------- | --------------------------------------- |
| reverse-proxy  | nginx:stable-alpine3.23                      | Reverse proxy, sub-path routing         |
| weather-app    | burningstar4/weather-app:latest              | Flask portfolio app                     |
| demo-container | burningstar4/demo-container:latest           | Disposable dummy : playground target    |
| prometheus     | prom/prometheus:v3.11.3                      | Metrics collection and alerting         |
| grafana        | grafana/grafana:13.0.1-security-01           | Dashboard visualization                 |
| loki           | grafana/loki:3.7.2                           | Log aggregation                         |
| promtail       | grafana/promtail:3.6.11                      | Log shipping from Docker socket         |
| statporter     | burningstar4/statporter:latest               | Custom Docker stats Prometheus exporter |
| alertmanager   | prom/alertmanager:v0.32.1                    | Alert routing (null receiver)           |
| tempo          | grafana/tempo:2.10.5                         | Trace storage backend                   |
| otel-collector | otel/opentelemetry-collector-contrib:0.152.0 | OTLP span receiver, batches to Tempo    |

All services have resource limits, restart policies, and `logging=true` labels for Promtail autodiscovery. Healthchecks are configured on all services except Loki, Tempo (both distroless : no shell), Promtail, and reverse-proxy.

---

## Flask Application (weather-app/docker-src/)

**Conventions:**

- All template renders go through `safe_render()` : catches `TemplateNotFound` and returns 404
- Every request gets a UUID in `g.request_id`, logged on both request and response
- Structured JSON logging via `python-json-logger`; logger setup in `logger.py`
- Prometheus metrics are auto-instrumented via `PrometheusMetrics(app)` at app init

---

## Design System

UI built with `/impeccable`. PRODUCT.md and DESIGN.md are the authoritative source. Single stylesheet: `weather-app/docker-src/static/styles.css`. All values via CSS custom properties on `:root` : no hard-coded colors or radii.

---

## Naming Conventions

**Commit messages:** conventional commits : `feat:`, `fix:`, `docs:`, `chore:`, `test:`. Body explains the why. Co-authored with Claude via `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`.

**CSS classes:** BEM-adjacent. Component block (`experience-entry`), element separator `__` (`experience-entry__role`), modifier separator `--` (`container--wide`, `btn-download--primary`).

**Python:** snake_case throughout. Flask routes use snake_case function names matching route segments.

**Docker image tags:** `burningstar4/<name>:latest` : no versioned tags currently.

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
- `GITLEAKS_LICENSE_KEY` (optional : Gitleaks runs without it)

**Variables required in GitHub:**

- `DOCKERHUB_USERNAME`

Pre-commit hooks run locally before commit: `end-of-file-fixer`, `trailing-whitespace`, `check-yaml`, `black`, `flake8`, `yamllint`, `prettier`, `codespell` (commit-msg stage). Prettier reformats HTML/CSS/JSON/Markdown : always re-stage after a failed commit and commit again. The `codespell` hook runs only at commit-msg time and requires `pre-commit install --hook-type commit-msg` on first setup.

---

## Known Environment Gotchas

1. **Prettier reformats on commit.** When a commit fails due to Prettier, the files are already fixed in the working tree. Re-stage the modified files and commit again : do not amend.

2. **Global `ul { list-style: none }`** in styles.css resets bullets sitewide. Any new template with semantic bullet lists must explicitly set `list-style: disc` on the `ul`.

3. **Prometheus scrapes weather-app at `:5000/metrics`** : the prometheus-flask-exporter auto-mounts this route. Do not add a manual `/metrics` route. The nginx `location = /metrics` block returns 403 to external clients; Prometheus bypasses nginx by scraping the container directly at `:5000`.

4. **alertmanager.yml uses null receiver.** All alerts are collected but go nowhere. This is intentional : the playground demonstrates the alerting loop visually without requiring external notification credentials.

5. **Docker socket access.** statporter mounts `/var/run/docker.sock` read-only. weather-app mounts it read-write for the playground container toggle. These are separate mount declarations : statporter's is `:ro`, weather-app's is default (rw). The RW mount is the highest blast-radius element in the stack; the hardcoded `DEMO_CONTAINER = "demo-container"` constant is the only scope limiter.

6. **Playground service-to-service address.** The stress endpoint in `playground.py` calls `http://demo-container:8080/stress` : that is the internal Docker network address, not localhost. `demo-container` is on the same `monitoring` bridge as `weather-app`. Never use `localhost` or `127.0.0.1` for this call.

7. **Log rotation.** Docker's built-in json-file rotation (`max-size: 50m`, `max-file: 5`) manages per-container log size. A host-level logrotate config at `weather-app/docker-final/logrotate/docker-containers` handles time-based rotation : copy it to `/etc/logrotate.d/` on the host.

8. **`.env` is gitignored.** `.env.example` is the committed template. Never commit `.env`. `GRAFANA_ADMIN_PASSWORD`, `FLASK_SECRET_KEY`, `PLAYGROUND_SECRET`, and `PLAYGROUND_ADMIN_KEY` must all be set before `docker compose up`.

9. **Grafana provisioning.** Dashboards and datasources are provisioned as code from `grafana/provisioning/`. Manual changes in the Grafana UI are not persisted across container restarts unless the provisioning files are updated. Only one dashboard provider file must exist in `grafana/provisioning/dashboards/` : Grafana 13 raises "Cannot change resource manager" and fails to load all dashboards if two providers point at the same path.

10. **statporter scrape interval is 10s, timeout 5s** : the background collector thread makes scrapes return in ~50ms, so the timeout is not a constraint. Do not raise the scrape_interval without also adjusting the collection loop's `SCRAPE_INTERVAL` env var.

11. **statporter uses underscores in label values.** Container names with hyphens are converted: `demo-container` → `name="demo_container"`, `weather-app` → `name="weather_app"`. Use underscores in all PromQL queries and alert expressions that filter by `name=`. The Docker SDK still uses the hyphenated name for `containers.get()`.

12. **`color-scheme: light dark`** is declared on `:root`. This tells browsers to render scrollbars, form controls, and OS-native UI in the appropriate theme.

13. **Loki and Tempo are distroless images.** `grafana/loki:3.7.2+` and `grafana/tempo:2.10.0+` have no shell, no `wget`, no `curl`, no `nc` : nothing to exec into. Docker healthchecks cannot be configured for either. Grafana, Promtail, and otel-collector use `depends_on: condition: service_started` (not `service_healthy`) for both. In CI, Loki readiness is verified by polling `http://loki:3100/ready` via `docker exec prometheus wget`; Tempo readiness via `http://tempo:3200/ready` the same way (Prometheus is Alpine and has wget). The loki-config.yaml sets `join_after: 0s` and `min_ready_duration: 0s` so the ingester ring goes ACTIVE immediately on single-node startup.

14. **Grafana `traces` panel type does not work with provisioned dashboards.** The `traces` panel uses streaming internally; the standard `/api/ds/query` path returns data but the panel renders "No data." Use `type: "table"` with `queryType: "traceqlSearch"` and a `filters` array instead. The Tempo datasource embeds trace ID deep-link URLs in the response so clicking a row still opens the waterfall view. `queryType: "nativeSearch"` returns HTTP 500 from the Grafana 13 Tempo plugin : do not use it.

15. **nginx CSP requires `'unsafe-eval'` for Grafana trace links.** The table panel's link template engine (`${__value.raw}`) uses `new Function()` internally. Without `'unsafe-eval'` in `script-src`, the panel throws an `EvalError` and shows an error state. This is added to the existing CSP in `nginx.conf` and applies to the full origin.

16. **OTel SDK log field names are `otelTraceID` and `otelSpanID`.** `LoggingInstrumentor(set_logging_format=True)` injects these camelCase fields (not `trace_id`/`span_id`). The `python-json-logger` format string must use `%(otelTraceID)s %(otelSpanID)s` exactly. Using the wrong names produces empty fields in every JSON log line with no error.

17. **Tempo's internal gRPC API runs on port 9095, OTLP receiver on 4317.** `tempo-config.yml` must explicitly set `server.grpc_listen_port: 9095` and `querier.frontend_worker.frontend_address: 127.0.0.1:9095` to silence the "Worker address is empty in single binary mode" startup warning. Without it, Tempo auto-detects but logs a warning on every start.

---

## Key Deliberate Trade-offs

- **No versioned image tags.** `:latest` is intentional for a single-person portfolio project. A versioning scheme adds CI complexity with no operational benefit at this stage.
- **Alertmanager null receiver.** Alerts fire and are visible in Prometheus and the upcoming playground, but no external notification is wired. This avoids requiring external credentials (SMTP, PagerDuty) for local or demo use.
- **No HTTPS in docker-compose.** TLS is deferred to the AWS deployment (ACM + ALB). Local dev runs plain HTTP on `:80`.
- **Single Compose file.** No dev/prod split. The same compose file runs locally and will be adapted for AWS ECS/EKS.
- **Session auth for playground** (not JWT or OAuth). The playground is behind a passphrase, not a full auth system. It is a demo surface, not a multi-user application.
- **100% head-based trace sampling.** All spans are collected and exported. Production stacks would use tail-based sampling to reduce volume. At homelab scale this is not a concern.
- **OTel Collector as middleware, not direct-to-Tempo.** Spans go weather-app → otel-collector → Tempo rather than direct. This adds one hop but decouples the SDK export format from Tempo's ingestion format and allows future pipeline changes (filtering, sampling, fan-out) without touching application code.

---

## In-Progress and Deferred Work

### Playground Feature (SHIPPED)

Interactive demo page at `/playground`. Implementation lives in `playground.py` (Blueprint) and `demo-container/app.py`.

**Auth design:** Passphrase derived via HMAC-SHA256 of `PLAYGROUND_SECRET` + current time window. Never stored. Admin retrieves current passphrase via `GET /playground/passphrase` (Bearer `PLAYGROUND_ADMIN_KEY`). 5-minute grace period at window boundaries. Sessions expire after 30 minutes of inactivity.

**Key implementation constraints:**

- CPU stress uses `threading.Event` : `is_set()` means stress is running, `clear()` stops it. `_burn()` loop: `while stop_event.is_set() and time.time() < deadline`. Do NOT invert this.
- All passphrase comparisons use `hmac.compare_digest` : never `==`
- Login route must never log `request.form`
- Toggle endpoint hardcodes `DEMO_CONTAINER = "demo-container"` : never uses container name from request input

**DemoContainerDown alert expression:**

```promql
(up{job="statporter"} == 1) and on() absent(container_cpu_percent{name="demo_container"})
```

`on()` is required : `absent()` returns `{name="demo_container"}` while the left side returns `{job="statporter", instance=...}`. Without `on()`, the label sets never match and the `and` returns nothing. `demo_container` uses an underscore (statporter naming convention).

**statporter stale gauge fix:** When a container stops, statporter's `collect_metrics()` actively removes label sets for containers no longer in `containers.list()` using `gauge.remove(name)`. This ensures `absent()` fires correctly : without this, Prometheus gauges retain their last value indefinitely and `absent()` never returns 1.

### Distributed Tracing (SHIPPED)

End-to-end OTel tracing across weather-app and statporter. Spans flow via OTLP gRPC → otel-collector → Tempo. Grafana unified observability dashboard (`homelab-observability`) surfaces metrics, traces, and logs in one view with a `$service` dropdown.

**Deferred from this implementation:**

- `about_me.html` Grafana hyperlink not yet updated to point to unified dashboard
- Trace-to-log correlation (click trace → see correlated Loki logs) not verified end-to-end
- Tempo uses no named volume : trace data is ephemeral by design (wiped on `docker compose down`)
- Service map / node graph (requires `metrics_generator` : deferred)

---

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

### Tests (phases 1, 2, and 3 shipped : unit tests still needed)

| File                                | Checklist coverage                                                                                                                                                                                                                                                                                                                                                    |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/test_stack_startup.py`       | Sections 1.1–1.4 (stack startup, healthchecks, restart counts, clean logs) + statporter scrape performance                                                                                                                                                                                                                                                            |
| `tests/test_weather_app_pages.py`   | Section 2 server-side items: page loads (2.1), navbar hrefs + text (2.2), `/weather` input validation and error shape (2.3–2.4), resume download link presence (2.5), `/healthz` + `X-Request-ID` header (2.8). Browser-only items (2.6 dark mode, 2.7 mobile, JS interactions) remain manual.                                                                        |
| `tests/test_observability_stack.py` | Section 3: Prometheus targets up (3.1), alert groups/rules loaded + none firing at rest (3.2), AlertManager linkage via Prometheus API (3.3), Grafana anonymous load + provisioned dashboard UIDs (3.4), Flask metrics via Prometheus (3.5), Loki ingestion via `docker exec` wget (3.6). Browser-only items (panel rendering, datasource error marks) remain manual. |

All three files run in CI via `integration-tests.yml`. `requirements-dev.txt` includes `pytest`, `docker`, and `requests`.

Still needed:

- `weather.py` unit tests : mock `requests.get`, assert all error paths return user-friendly messages without leaking the API key URL or raw exception details
- Playground auth unit tests : passphrase derivation, window boundary/grace period, session expiry
- statporter unit tests : `_cpu_percent()`, `_blkio_bytes()`, stale label cleanup logic

New test files must follow the naming convention in `CI_LOOP_DESIGN.md` Part 4 : file and class names must include the service name for the CI self-healing loop to apply correct labels on failure.

### Security (session cookie hardening : deferred to AWS)

`SESSION_COOKIE_SECURE = True` should be set once the stack is behind ACM/HTTPS. Incorrect to set locally (HTTP). Add to app config at AWS deployment time alongside Secrets Manager migration.
