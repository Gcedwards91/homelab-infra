# Use Python 3.11 slim image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DOCKERIZED=1
ENV FLASK_DEBUG=0

# Create working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential=12.9 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Expose the port the app runs on
EXPOSE 5000

# Start the app using gunicorn
CMD ["gunicorn", "--log-level", "debug", "-w", "2","-t", "60", "-b", "0.0.0.0:5000", "main:app"]

