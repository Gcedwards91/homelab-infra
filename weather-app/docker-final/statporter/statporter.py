import logging
import os
import sys
from typing import cast

import docker
from flask import Flask, Response
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
from prometheus_client.core import CollectorRegistry

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("statporter")

# ---------------------------------------------------------------------------
# Prometheus registry & gauges
# ---------------------------------------------------------------------------
registry = CollectorRegistry()

CPU_PERCENT = Gauge(
    "container_cpu_percent",
    "CPU usage percentage per container",
    ["name"],
    registry=registry,
)
MEM_USAGE = Gauge(
    "container_memory_usage_bytes",
    "Memory usage in bytes per container",
    ["name"],
    registry=registry,
)
MEM_PERCENT = Gauge(
    "container_memory_percent",
    "Memory usage percentage per container",
    ["name"],
    registry=registry,
)
NET_RX = Gauge(
    "container_network_receive_bytes_total",
    "Cumulative network bytes received per container",
    ["name"],
    registry=registry,
)
NET_TX = Gauge(
    "container_network_transmit_bytes_total",
    "Cumulative network bytes transmitted per container",
    ["name"],
    registry=registry,
)
BLKIO_READ = Gauge(
    "container_blkio_read_bytes_total",
    "Cumulative block I/O bytes read per container",
    ["name"],
    registry=registry,
)
BLKIO_WRITE = Gauge(
    "container_blkio_write_bytes_total",
    "Cumulative block I/O bytes written per container",
    ["name"],
    registry=registry,
)

# ---------------------------------------------------------------------------
# Docker client — lazily initialised so startup failures are visible
# ---------------------------------------------------------------------------
_client: docker.DockerClient | None = None


def get_client() -> docker.DockerClient:
    """Return a cached Docker client, creating it on first call."""
    global _client
    if _client is None:
        socket = os.getenv("DOCKER_HOST", "unix:///var/run/docker.sock")
        log.info("Connecting to Docker at %s", socket)
        _client = docker.DockerClient(base_url=socket)
    return _client


# ---------------------------------------------------------------------------
# Metric collection
# ---------------------------------------------------------------------------
def _cpu_percent(stats: dict) -> float:
    """Calculate CPU usage percentage from a Docker stats snapshot."""
    cpu_stats = stats.get("cpu_stats", {})
    precpu_stats = stats.get("precpu_stats", {})

    cpu_total = cpu_stats.get("cpu_usage", {}).get("total_usage", 0)
    precpu_total = precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
    cpu_system = cpu_stats.get("system_cpu_usage")
    precpu_system = precpu_stats.get("system_cpu_usage")

    if cpu_system is None or precpu_system is None:
        return 0.0

    cpu_delta = cpu_total - precpu_total
    system_delta = cpu_system - precpu_system

    if system_delta <= 0 or cpu_delta <= 0:
        return 0.0

    percpu = cpu_stats.get("cpu_usage", {}).get("percpu_usage")
    num_cpus = len(percpu) if percpu else os.cpu_count() or 1

    return (cpu_delta / system_delta) * num_cpus * 100.0


def _blkio_bytes(stats: dict) -> tuple[int, int]:
    """Return (bytes_read, bytes_written) from blkio_stats."""
    read_bytes = 0
    write_bytes = 0
    for entry in stats.get("blkio_stats", {}).get("io_service_bytes_recursive") or []:
        op = entry.get("op", "").lower()
        value = entry.get("value", 0)
        if op == "read":
            read_bytes += value
        elif op == "write":
            write_bytes += value
    return read_bytes, write_bytes


def collect_metrics() -> None:
    """Scrape all running containers and update Prometheus gauges."""
    try:
        client = get_client()
        containers = client.containers.list()
    except Exception:
        log.exception("Failed to list containers")
        return

    for container in containers:
        name = (container.name or container.short_id).replace("-", "_")
        try:
            stats = cast(dict, container.stats(stream=False))
        except Exception:
            log.warning("Could not retrieve stats for %s", name, exc_info=True)
            continue

        try:
            # CPU
            cpu = _cpu_percent(stats)
            CPU_PERCENT.labels(name=name).set(cpu)

            # Memory
            mem_usage = stats.get("memory_stats", {}).get("usage", 0)
            mem_limit = stats.get("memory_stats", {}).get("limit") or 1
            mem_pct = (mem_usage / mem_limit) * 100.0
            MEM_USAGE.labels(name=name).set(mem_usage)
            MEM_PERCENT.labels(name=name).set(mem_pct)

            # Network
            net_rx_bytes = 0
            net_tx_bytes = 0
            for iface in stats.get("networks", {}).values():
                net_rx_bytes += iface.get("rx_bytes", 0)
                net_tx_bytes += iface.get("tx_bytes", 0)
            NET_RX.labels(name=name).set(net_rx_bytes)
            NET_TX.labels(name=name).set(net_tx_bytes)

            # Disk I/O
            blkio_read, blkio_write = _blkio_bytes(stats)
            BLKIO_READ.labels(name=name).set(blkio_read)
            BLKIO_WRITE.labels(name=name).set(blkio_write)

            log.debug(
                "%s — cpu=%.2f%% mem=%.2f%% net_rx=%d net_tx=%d blkio_r=%d blkio_w=%d",
                name,
                cpu,
                mem_pct,
                net_rx_bytes,
                net_tx_bytes,
                blkio_read,
                blkio_write,
            )

        except Exception:
            log.exception("Error processing metrics for %s", name)


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)


@app.route("/metrics")
def metrics():
    """Prometheus scrape endpoint."""
    log.debug("Scrape request received")
    collect_metrics()
    return Response(generate_latest(registry), mimetype=CONTENT_TYPE_LATEST)


@app.route("/healthz")
def healthz():
    """Health check endpoint — verifies Docker connectivity."""
    try:
        get_client().ping()
        return "ok", 200
    except Exception:
        log.exception("Health check failed")
        return "docker unavailable", 503


# ---------------------------------------------------------------------------
# Gunicorn serves this app — see Dockerfile CMD.
# Run locally with: gunicorn --bind 0.0.0.0:9800 statporter:app
# ---------------------------------------------------------------------------
