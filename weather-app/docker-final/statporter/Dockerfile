FROM python:3.11.15-slim

LABEL maintainer="George Edwards gcedwards91@gmail.com"
LABEL description="A custom Prometheus exporter exposing Docker container metrics via Flask/Gunicorn."
LABEL version="1.1.0"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
# apt-get upgrade pulls patched OS packages at build time, so a rebuild is
# what clears base-image CVEs.
# hadolint ignore=DL3008
RUN pip install --no-cache-dir -r requirements.txt && \
    apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY . .

# Run as an unprivileged user: the Docker API is reached over TCP via the
# socket proxy, so no socket group membership (or root) is needed.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 9800

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:9800/healthz || exit 1

# Single worker only: the metrics registry and the background collector thread
# are process-local singletons. Running >1 worker spawns a second collector with
# its own registry, doubling Docker stats load and making Prometheus scrapes
# alternate between two unsynchronised registries, which flaps absent()/stale
# label removal and the DemoContainerDown alert. Concurrency for the trivial
# /metrics and /healthz endpoints is provided by threads instead.
CMD ["gunicorn", "--workers=1", "--threads=4", "--bind=0.0.0.0:9800", "--access-logfile=-", "--error-logfile=-", "statporter:app"]
