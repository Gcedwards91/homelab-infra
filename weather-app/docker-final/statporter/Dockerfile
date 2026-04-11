FROM python:3.11-slim

LABEL maintainer="George Edwards gcedwards91@gmail.com"
LABEL description="A custom Prometheus exporter exposing Docker container metrics via Flask/Gunicorn."
LABEL version="1.1.0"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY . .

EXPOSE 9800

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:9800/healthz || exit 1

CMD ["gunicorn", "--workers=2", "--bind=0.0.0.0:9800", "--access-logfile=-", "--error-logfile=-", "statporter:app"]
