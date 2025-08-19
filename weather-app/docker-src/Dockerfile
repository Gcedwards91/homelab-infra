# Use Python 3.11 slim image
FROM python:3.11-slim

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DOCKERIZED=1 \
    FLASK_DEBUG=0

# Workdir
WORKDIR /app

# System deps (temporary) → pip install → purge to slim image
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

# Python deps first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Copy app explicitly so templates/static definitely land in image ---
# Adjust this list if you have more modules
COPY main.py logger.py weather.py ./
COPY templates/ ./templates/
COPY static/ ./static/

# Optional: prove they exist at build time (helps debug missing templates)
# RUN ls -la /app && ls -la /app/templates && ls -la /app/static

# Expose Flask/Gunicorn port
EXPOSE 5000

# Healthcheck (expects your /healthz route)
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import sys, urllib.request; \
r=0; \
import traceback; \
url='http://127.0.0.1:5000/healthz'; \
try: resp=urllib.request.urlopen(url, timeout=2); r=0 if resp.status==200 else 1 \
except Exception: r=1; \
sys.exit(r)"


# Start the app with gunicorn
CMD ["gunicorn", "--log-level", "debug", "-w", "2", "-t", "60", "-b", "0.0.0.0:5000", "main:app"]
