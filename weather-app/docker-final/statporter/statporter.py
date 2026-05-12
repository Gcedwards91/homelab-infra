import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import cast

import docker
from flask import Flask, Response
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
from prometheus_client.core import CollectorRegistry

# -------- Logging --------
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("statporter")

# -------- Prometheus registry & gauges --------
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

SCRAPE_INTERVAL = int(
    os.getenv("SCRAPE_INTERVAL", "10")
)  # seconds between collection rounds
_SCRAPE_WORKERS = 16  # max parallel Docker stats calls

# -------- Docker client — lazily initialised so startup failures are visible --------
_client: docker.DockerClient | None = None


def get_client() -> docker.DockerClient:
    """Return a cached Docker client, creating it on first call."""
    global _client
    if _client is None:
        socket = os.getenv("DOCKER_HOST", "unix:///var/run/docker.sock")
        log.info("Connecting to Docker at %s", socket)
        _client = docker.DockerClient(base_url=socket)
    return _client


# -------- Metric collection --------
_seen_names: set[str] = set()


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


def _scrape_one(container) -> tuple[str, dict] | None:
    """Fetch stats for a single container. Returns (name, stats) or None on failure."""
    name = (container.name or container.short_id).replace("-", "_")
    try:
        stats = cast(dict, container.stats(stream=False))
        return name, stats
    except Exception:
        log.warning("Could not retrieve stats for %s", name, exc_info=True)
        return None


def collect_metrics() -> None:
    """Scrape all running containers in parallel and update Prometheus gauges."""
    global _seen_names
    try:
        client = get_client()
        containers = client.containers.list()
    except Exception:
        log.exception("Failed to list containers")
        return

    if not containers:
        return

    current_names: set[str] = set()

    # Fan out Docker stats calls across all containers simultaneously.
    # Each call takes ~1s; parallel execution keeps total time near that of one call.
    workers = min(len(containers), _SCRAPE_WORKERS)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = pool.map(_scrape_one, containers)

    for result in results:
        if result is None:
            continue
        name, stats = result
        current_names.add(name)
        try:
            cpu = _cpu_percent(stats)
            CPU_PERCENT.labels(name=name).set(cpu)

            mem_usage = stats.get("memory_stats", {}).get("usage", 0)
            mem_limit = stats.get("memory_stats", {}).get("limit") or 1
            mem_pct = (mem_usage / mem_limit) * 100.0
            MEM_USAGE.labels(name=name).set(mem_usage)
            MEM_PERCENT.labels(name=name).set(mem_pct)

            net_rx_bytes = 0
            net_tx_bytes = 0
            for iface in stats.get("networks", {}).values():
                net_rx_bytes += iface.get("rx_bytes", 0)
                net_tx_bytes += iface.get("tx_bytes", 0)
            NET_RX.labels(name=name).set(net_rx_bytes)
            NET_TX.labels(name=name).set(net_tx_bytes)

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

    # Remove gauges for containers no longer running so absent() fires correctly.
    _gauges = (
        CPU_PERCENT,
        MEM_USAGE,
        MEM_PERCENT,
        NET_RX,
        NET_TX,
        BLKIO_READ,
        BLKIO_WRITE,
    )
    for gone in _seen_names - current_names:
        for gauge in _gauges:
            try:
                gauge.remove(gone)
            except Exception:
                pass
    _seen_names = current_names


def _collection_loop() -> None:
    """Background thread: collect metrics on a fixed interval.

    Sleeps for SCRAPE_INTERVAL minus however long the collection took, so a slow
    round doesn't cause immediate back-to-back scrapes but also doesn't stack delay.
    """
    log.info(
        "Background collector starting — interval=%ds workers=%d",
        SCRAPE_INTERVAL,
        _SCRAPE_WORKERS,
    )
    while True:
        start = time.monotonic()
        try:
            collect_metrics()
        except Exception:
            log.exception("Unhandled error in collection loop")
        elapsed = time.monotonic() - start
        log.debug("Collection round complete in %.2fs", elapsed)
        time.sleep(max(0.0, SCRAPE_INTERVAL - elapsed))


# -------- Flask app --------
app = Flask(__name__)


@app.route("/metrics")
def metrics():
    """Prometheus scrape endpoint — serves from background-collected cache."""
    log.debug("Scrape request received")
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


# -------- Start background collector --------
threading.Thread(
    target=_collection_loop, daemon=True, name="statporter-collector"
).start()
