FROM python:3.11-slim

LABEL maintainer="George Edwards gcedwards91@gmail.com"
LABEL description="A custom Prometheus exporter exposing Docker container metrics via Flask. This was created for a homelab project"
LABEL version="1.0.0"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/metrics || exit 1

CMD ["python", "statporter.py"]
