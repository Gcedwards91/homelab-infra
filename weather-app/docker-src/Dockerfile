FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DOCKERIZED=1 \
    FLASK_DEBUG=0

WORKDIR /app

# Install curl for healthcheck (no build tools needed — all deps are pure Python)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl=8.14.1-2+deb13u2 \
    && rm -rf /var/lib/apt/lists/*

# Python deps first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source explicitly so templates/static definitely land in image
COPY main.py logger.py weather.py ./
COPY templates/ ./templates/
COPY static/ ./static/

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:5000/healthz || exit 1

# Gunicorn serves the app with 2 workers, logging at warning level
CMD ["gunicorn", "--workers=2", "--bind=0.0.0.0:5000", "--timeout=60", \
     "--log-level=warning", "--access-logfile=-", "--error-logfile=-", \
     "main:app"]
