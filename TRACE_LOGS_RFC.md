# feat: distributed tracing — OpenTelemetry, Tempo, and Grafana observability dashboard

---

## Pre-Implementation Checklist

- [ ] Verify Grafana version is 9.0+ (current stack is 13.0.1-security-01 — satisfied)
- [ ] Confirm `uid: loki` is added to `grafana/provisioning/datasources/loki.yaml` before stack restart
- [ ] Confirm `uid: prometheus` already exists in `grafana/provisioning/datasources/prometheus.yaml`

---

## Summary

Implements end-to-end distributed tracing across the Python stack using the OpenTelemetry standard. Trace context is generated at the edge (weather-app), propagated through outgoing HTTP calls via W3C TraceContext headers, and collected by the OpenTelemetry Collector before being stored in Grafana Tempo. Grafana provides native waterfall visualization of individual request traces and a unified observability dashboard combining metrics, traces, and logs in a single view.

The homelab landing page Grafana hyperlink points to the unified dashboard — one URL, no tab switching.

This establishes a pre-migration baseline on the Python stack. After the Statporter Go rewrite, the same Grafana dashboard will provide a concrete before/after latency comparison per service using identical queries.

The full trace lifecycle:

```
User request enters weather-app
  → FlaskInstrumentor creates root span (trace ID generated)
  → RequestsInstrumentor creates child span for outgoing external weather API call
  → spans exported via OTLP gRPC to otel-collector
  → otel-collector batches and forwards to tempo
  → Grafana queries Tempo for waterfall view

Prometheus scrapes statporter /metrics
  → FlaskInstrumentor creates root span on statporter
  → span exported via OTLP gRPC to otel-collector → tempo
  → Grafana shows statporter traces as isolated root spans (no parent-child relationship with weather-app)
```

Note: weather-app and statporter produce independent trace trees. There is no direct call path between them — statporter is scraped by Prometheus on its own interval, not called by weather-app.

---

## Architecture

### New Services

| Service          | Image                                          | Purpose                                                                |
| ---------------- | ---------------------------------------------- | ---------------------------------------------------------------------- |
| `otel-collector` | `otel/opentelemetry-collector-contrib:0.152.0` | Receives spans from instrumented services, batches and routes to Tempo |
| `tempo`          | `grafana/tempo:2.10.0`                         | Trace storage backend                                                  |

### Existing Services Modified

| Service              | Change                                                                                                   |
| -------------------- | -------------------------------------------------------------------------------------------------------- |
| `weather-app`        | Add OpenTelemetry Python SDK instrumentation, split into TracerProvider setup + instrument_app placement |
| `statporter`         | Add OpenTelemetry Python SDK instrumentation, instrument_app placed after app creation at line 234       |
| `grafana`            | Add Tempo datasource provisioning, add unified observability dashboard JSON, update depends_on           |
| `loki datasource`    | Add `uid: loki` to provisioning file                                                                     |
| `docker-compose.yml` | Add Tempo and OTel Collector services with resource limits, logging labels, expose-only ports            |
| `nginx.conf`         | Pass W3C TraceContext headers to upstream services                                                       |
| `about_me.html`      | Update Grafana hyperlink to point to unified observability dashboard                                     |

---

## Part 1 — docker-compose.yml Changes

### New services

```yaml
otel-collector:
  image: otel/opentelemetry-collector-contrib:0.152.0
  container_name: otel-collector
  volumes:
    - ./otel-collector-config.yml:/etc/otelcol-contrib/config.yaml:ro
  expose:
    - "4317" # OTLP gRPC receiver (internal only)
    - "4318" # OTLP HTTP receiver (internal only)
  depends_on:
    - tempo
  restart: unless-stopped
  networks:
    - monitoring
  labels:
    - "logging=true"
  logging:
    driver: "json-file"
    options:
      max-size: "50m"
      max-file: "5"
  deploy:
    resources:
      limits:
        cpus: "0.5"
        memory: 256M
      reservations:
        cpus: "0.1"
        memory: 64M

tempo:
  image: grafana/tempo:2.10.0
  container_name: tempo
  command: ["-config.file=/etc/tempo.yaml"]
  volumes:
    - ./tempo-config.yml:/etc/tempo.yaml:ro
    - tempo_data:/var/tempo
  expose:
    - "3200" # Tempo HTTP API (internal only)
    - "4317" # Tempo OTLP gRPC receiver (internal only)
  restart: unless-stopped
  networks:
    - monitoring
  labels:
    - "logging=true"
  logging:
    driver: "json-file"
    options:
      max-size: "50m"
      max-file: "5"
  deploy:
    resources:
      limits:
        cpus: "1.0"
        memory: 512M
      reservations:
        cpus: "0.25"
        memory: 128M
  healthcheck:
    test: ["CMD", "wget", "--spider", "-q", "http://localhost:3200/ready"]
    interval: 10s
    timeout: 5s
    retries: 5
    start_period: 15s
```

### Named volume to add

```yaml
tempo_data:
```

### Environment variables to add to weather-app service

```yaml
environment:
  - OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
  - OTEL_SERVICE_NAME=weather-app
```

### Environment variables to add to statporter service

```yaml
environment:
  - OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
  - OTEL_SERVICE_NAME=statporter
```

### Update Grafana depends_on

Add to the existing Grafana `depends_on` block:

```yaml
tempo:
  condition: service_healthy
```

---

## Part 2 — New Configuration Files

### `otel-collector-config.yml`

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 1s
    send_batch_size: 1024

exporters:
  otlp:
    endpoint: tempo:4317
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp]
```

### `tempo-config.yml`

```yaml
server:
  http_listen_port: 3200

distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: 0.0.0.0:4317

storage:
  trace:
    backend: local
    local:
      path: /var/tempo/traces
    wal:
      path: /var/tempo/wal

compactor:
  compaction:
    block_retention: 168h # 7 days
```

---

## Part 3 — Existing Datasource Fix

### `grafana/provisioning/datasources/loki.yaml`

Add `uid: loki` to the Loki datasource definition so Tempo's trace-to-log linking resolves correctly:

```yaml
apiVersion: 1

datasources:
  - name: Loki
    type: loki
    uid: loki # ADD THIS LINE
    access: proxy
    url: http://loki:3100
    # ... rest of existing config unchanged
```

Without this, Grafana auto-generates a random UID and the tracesToLogs link in the Tempo datasource silently fails to find correlated logs.

---

## Part 4 — New Tempo Datasource

### `grafana/provisioning/datasources/tempo.yaml`

```yaml
apiVersion: 1

datasources:
  - name: Tempo
    type: tempo
    uid: tempo
    access: proxy
    url: http://tempo:3200
    isDefault: false
    jsonData:
      httpMethod: GET
      serviceMap:
        datasourceUid: prometheus
      nodeGraph:
        enabled: false
      tracesToLogs:
        datasourceUid: loki
        filterByTraceID: true
        filterBySpanID: false
        mapTagNamesEnabled: true
```

Note: `nodeGraph.enabled: false` — the service map node graph requires Tempo's `metrics_generator` component which is not in scope for this PR. Deferred to a follow-up.

---

## Part 5 — Python Instrumentation

### `requirements.txt` additions (both weather-app and statporter)

```
opentelemetry-api
opentelemetry-sdk
opentelemetry-exporter-otlp-proto-grpc
opentelemetry-instrumentation-flask
opentelemetry-instrumentation-requests
opentelemetry-instrumentation-logging
```

Note: `OTEL_TRACES_EXPORTER` env var is intentionally omitted. The spec uses explicit programmatic TracerProvider initialization — the env var is only relevant for auto-instrumentation via `opentelemetry-distro` and is ignored when the provider is configured manually.

---

### weather-app — `main.py` changes

**Step 1 — Add at the top of main.py, before any other app code:**

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor

# TracerProvider setup — must come before app creation
provider = TracerProvider()
otlp_exporter = OTLPSpanExporter()
provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
trace.set_tracer_provider(provider)

# Auto-instrument outgoing HTTP requests globally
# Creates child spans for every requests.get/post call, including external weather API calls
RequestsInstrumentor().instrument()

# Inject trace_id and span_id into log records for Loki correlation
LoggingInstrumentor().instrument(set_logging_format=True)
```

**Step 2 — Immediately after `app = Flask(__name__)` (line ~20):**

```python
# Must come after app creation
FlaskInstrumentor().instrument_app(app)
```

---

### statporter — `statporter.py` changes

**Step 1 — Add at the top of statporter.py, before any other app code:**

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor

# TracerProvider setup — must come before app creation
provider = TracerProvider()
otlp_exporter = OTLPSpanExporter()
provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
trace.set_tracer_provider(provider)

# Inject trace_id and span_id into log records for Loki correlation
LoggingInstrumentor().instrument(set_logging_format=True)
```

**Step 2 — Immediately after `app = Flask(__name__)` (line ~234):**

```python
# Must come after app creation
FlaskInstrumentor().instrument_app(app)
```

**Step 3 — Optional manual span for metric collection timing:**

Wrap the collection logic in a manual span to time the metric collection itself separately from the Flask request overhead:

```python
tracer = trace.get_tracer(__name__)

def collect_metrics():
    with tracer.start_as_current_span("collect_metrics") as span:
        span.set_attribute("collector.service", "statporter")
        # existing collection logic here
```

---

### logger.py changes (weather-app)

`LoggingInstrumentor(set_logging_format=True)` injects `trace_id` and `span_id` into the Python log record. For these fields to appear in the JSON output that Promtail ships to Loki, the existing formatter in `logger.py` must include them.

Update the `python-json-logger` format string to include OTel context fields:

```python
formatter = jsonlogger.JsonFormatter(
    '%(asctime)s %(levelname)s %(name)s %(message)s %(trace_id)s %(span_id)s'
)
```

If the formatter uses a dict-based format instead of a string, add `trace_id` and `span_id` to the field list. The exact change depends on the current logger.py implementation — locate the `JsonFormatter` instantiation and add both fields.

---

## Part 6 — Nginx Trace Header Passthrough

### `nginx.conf` changes

Add to each `location` block that proxies to an upstream service:

```nginx
proxy_set_header traceparent $http_traceparent;
proxy_set_header tracestate  $http_tracestate;
```

- Forwards W3C TraceContext headers to upstream services
- Allows traces initiated outside the stack (e.g. from a browser or curl) to continue into the backend rather than generating a new root span at Nginx
- Nginx access logs can be correlated with Tempo traces by logging `$http_traceparent`

---

## Part 7 — Unified Observability Dashboard

### New file: `grafana/dashboards/homelab-observability.json`

This is the primary dashboard for the homelab. The Grafana hyperlink in `about_me.html` points directly to this dashboard. One URL surfaces metrics, traces, and logs simultaneously — no tab switching required.

### Dashboard structure

**Template variable**

- `service` — dropdown, values: `weather-app`, `statporter`. Drives all three rows simultaneously.

**Top row — Metrics (Prometheus)**

| Panel                      | Query                                                                                                |
| -------------------------- | ---------------------------------------------------------------------------------------------------- |
| Request rate by service    | `rate(flask_http_request_total{service="$service"}[5m])`                                             |
| Error rate by service      | `rate(flask_http_request_total{service="$service",status=~"5.."}[5m])`                               |
| P50 / P95 / P99 latency    | `histogram_quantile(0.99, rate(flask_http_request_duration_seconds_bucket{service="$service"}[5m]))` |
| External API call duration | Tempo TraceQL — spans filtered by `http.url` containing weather API host                             |

**Middle row — Traces (Tempo)**

| Panel        | Notes                                                                                                                                                                                        |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Trace search | Native Tempo panel, filtered by `$service`. Clicking a trace opens the waterfall view. With `tracesToLogs` configured, each trace links directly to correlated Loki log lines by `trace_id`. |

**Bottom row — Logs (Loki)**

| Panel      | Query                                                                                                                                 |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Log stream | `{container="$service"}` — time-synced to dashboard time range. `trace_id` and `span_id` fields present in log lines for correlation. |

### Dashboard JSON requirements

The full JSON file must include:

- `datasource` refs using UIDs `prometheus`, `loki`, and `tempo`
- `$service` template variable with `weather-app` and `statporter` as static options
- Time range defaulting to last 1 hour
- Panel links from the trace search panel to Grafana Explore with the correlated Loki query pre-populated

### about_me.html update

Update the existing Grafana hyperlink to point to the unified dashboard. Once the dashboard is provisioned and its UID is known, the link format is:

```
http://<grafana-host>/d/<dashboard-uid>/homelab-observability
```

The dashboard UID is set explicitly in the JSON under the `uid` field — use `homelab-observability` as the UID so the URL is predictable and does not change if the dashboard is re-imported.

### Dashboard build note

The dashboard JSON should be built against real data after the stack is running with traces flowing. Prometheus metric names emitted by Flask OTel instrumentation should be verified in the Prometheus UI before writing panel queries. The structure and panel layout above are the authoritative spec — the JSON implementation follows from it.

---

## Part 8 — Retention and Storage

- Tempo configured for 7-day local trace retention — sufficient for homelab scale
- Traces stored in named Docker volume `tempo_data` — persists across container restarts
- OTel Collector batch processor set to 1s timeout, 1024 span batch size — appropriate for single-host low-volume stack
- Tempo runs in single binary mode — distributed mode not needed at this scale

---

## Testing Checklist

- [ ] `docker compose up -d` — all services start cleanly including `tempo` and `otel-collector`
- [ ] Verify `tempo` passes healthcheck: `docker inspect --format='{{.State.Health.Status}}' tempo`
- [ ] Verify Tempo datasource appears in Grafana under **Configuration > Data Sources** with status **OK**
- [ ] Make a request to the weather app — verify a trace appears in Grafana Explore under the Tempo datasource
- [ ] Verify the trace contains at minimum two spans: incoming Flask request + outgoing external API call
- [ ] Verify clicking a trace in Grafana opens correlated Loki logs (requires logger.py changes and `uid: loki` fix)
- [ ] Verify statporter trace appears as an isolated root span when Prometheus scrapes `/metrics`
- [ ] Verify Nginx passes `traceparent` header by checking span attributes in Tempo for `http.request.header.traceparent`
- [ ] Verify `tempo_data` volume persists traces after `docker compose restart tempo`
- [ ] Verify OTel Collector and Tempo logs appear in Loki (confirms `logging=true` label is working)
- [ ] Verify resource limits are applied: `docker stats otel-collector tempo`
- [ ] Verify unified dashboard loads at `/d/homelab-observability/homelab-observability` with all three rows populated
- [ ] Verify `$service` template variable filters all panels correctly when switching between `weather-app` and `statporter`
- [ ] Verify Grafana hyperlink in `about_me.html` opens the unified dashboard directly
- [ ] `pre-commit run --all-files` passes on all new and modified files

---

## What This Does Not Cover

- **Service map / node graph** — requires Tempo `metrics_generator` with `service_graphs` processor; non-trivial addition, deferred to follow-up PR
- **Sampling strategy** — all traces collected at 100% head-based sampling; production deployments would configure tail-based sampling to reduce volume; deferred
- **Alerting on trace-derived SLOs** — deferred until after K8s migration
- **Instrumentation of Prometheus, Loki, Alertmanager, Grafana internals** — observability overhead not worth the noise at this scale
- **Tempo distributed mode** — single binary mode is correct for homelab scale

---

## Baseline Capture Note

Once this PR is stable, record P50/P95/P99 latency per service from the unified dashboard before the K8s migration and Statporter Go rewrite. The same dashboard and queries will show post-rewrite numbers, providing a concrete before/after comparison with no additional instrumentation work required.
