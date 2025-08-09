from flask import Flask, Response
import docker
import os
import json
import tempfile
import sys

from prometheus_client import (
    CollectorRegistry,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

app = Flask(__name__)
print("Statporter is starting...")

# --- Docker client setup ---
DOCKER_SOCKET_PATH = "/var/run/docker.sock"
DOCKER_HOST = os.getenv("DOCKER_HOST", f"unix://{DOCKER_SOCKET_PATH}")

# If using the default unix socket, make sure it's mounted
if DOCKER_HOST.startswith("unix://") and not os.path.exists(DOCKER_SOCKET_PATH):
    raise RuntimeError(
        f"Docker socket not found at {DOCKER_SOCKET_PATH}. "
        "Is it mounted into the container? (e.g., -v /var/run/docker.sock:/var/run/docker.sock:ro)"
    )

# Prefer from_env() so it picks up DOCKER_HOST, TLS vars, etc.
try:
    client = docker.from_env()
    # .ping() validates connectivity early
    client.ping()
except Exception:
    # Fallback to explicit base_url if from_env didn’t pick it up
    client = docker.DockerClient(base_url=DOCKER_HOST)
    client.ping()

# Optional debug stats directory (set DEBUG_STATS_DIR=/tmp/debug_stats to enable)
DEBUG_STATS_DIR = os.getenv("DEBUG_STATS_DIR", "").strip()
if DEBUG_STATS_DIR:
    os.makedirs(DEBUG_STATS_DIR, exist_ok=True)


def get_metrics_as_prometheus_text() -> bytes:
    """
    Scrape container stats and return Prometheus text format bytes.
    """
    registry = CollectorRegistry()

    g_cpu_pct = Gauge(
        "container_cpu_percent",
        "Container CPU percent (approx)",
        ["name", "id", "image"],
        registry=registry,
    )
    g_mem_bytes = Gauge(
        "container_memory_usage_bytes",
        "Container memory usage in bytes",
        ["name", "id", "image"],
        registry=registry,
    )
    g_mem_pct = Gauge(
        "container_memory_percent",
        "Container memory usage as percent of limit",
        ["name", "id", "image"],
        registry=registry,
    )
    g_net_rx = Gauge(
        "container_network_receive_bytes_total",
        "Container network received bytes (since container start)",
        ["name", "id", "image"],
        registry=registry,
    )
    g_net_tx = Gauge(
        "container_network_transmit_bytes_total",
        "Container network transmitted bytes (since container start)",
        ["name", "id", "image"],
        registry=registry,
    )

    # Only running containers by default (same behavior as docker-py list())
    containers = client.containers.list()

    for c in containers:
        name = c.name.replace("-", "_")
        cid = c.short_id
        image = (
            c.image.tags[0]
            if c.image and c.image.tags
            else c.image.id if c.image else "unknown"
        )

        try:
            stats = c.stats(stream=False)
        except Exception as e:
            # Expose as comment in the scrape output
            comment = f"# Could not retrieve stats for {name}: {e}\n"
            return comment.encode("utf-8") + generate_latest(registry)

        # Optional JSON dump for debug
        if DEBUG_STATS_DIR:
            try:
                debug_path = os.path.join(DEBUG_STATS_DIR, f"{name}_stats.json")
                with open(debug_path, "w") as f:
                    json.dump(stats, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
            except Exception as e:
                # Non-fatal; show as comment
                sys.stderr.write(f"Could not write debug for {name}: {e}\n")

        try:
            cpu_stats = stats.get("cpu_stats", {}) or {}
            precpu_stats = stats.get("precpu_stats", {}) or {}

            cpu_total = (cpu_stats.get("cpu_usage", {}) or {}).get("total_usage", 0)
            precpu_total = (precpu_stats.get("cpu_usage", {}) or {}).get(
                "total_usage", 0
            )

            cpu_system = cpu_stats.get("system_cpu_usage")
            precpu_system = precpu_stats.get("system_cpu_usage")

            cpu_percent = 0.0
            if cpu_system is not None and precpu_system is not None:
                cpu_delta = cpu_total - precpu_total
                system_delta = cpu_system - precpu_system
                if system_delta > 0 and cpu_delta > 0:
                    percpu = (cpu_stats.get("cpu_usage", {}) or {}).get(
                        "percpu_usage", []
                    ) or []
                    cpu_percent = (
                        (cpu_delta / system_delta) * max(len(percpu), 1) * 100.0
                    )

            mem_stats = stats.get("memory_stats", {}) or {}
            mem_usage = mem_stats.get("usage", 0) or 0
            mem_limit = mem_stats.get("limit", 1) or 1
            mem_percent = (mem_usage / mem_limit) * 100.0 if mem_limit else 0.0

            net_rx, net_tx = 0, 0
            for iface in (stats.get("networks", {}) or {}).values():
                net_rx += iface.get("rx_bytes", 0) or 0
                net_tx += iface.get("tx_bytes", 0) or 0

            labelset = dict(name=name, id=cid, image=image)
            g_cpu_pct.labels(**labelset).set(cpu_percent)
            g_mem_bytes.labels(**labelset).set(mem_usage)
            g_mem_pct.labels(**labelset).set(mem_percent)
            g_net_rx.labels(**labelset).set(net_rx)
            g_net_tx.labels(**labelset).set(net_tx)

        except Exception as e:
            # If processing one container fails, keep the scrape going
            sys.stderr.write(f"Error processing metrics for {name}: {e}\n")

    return generate_latest(registry)


@app.route("/metrics")
def metrics():
    sys.stdout.write("Metrics endpoint hit!\n")
    sys.stdout.flush()
    payload = get_metrics_as_prometheus_text()
    return Response(payload, mimetype=CONTENT_TYPE_LATEST)


@app.route("/health")
def health():
    try:
        client.ping()
        return "ok\n", 200
    except Exception as e:
        return f"unhealthy: {e}\n", 500


if __name__ == "__main__":
    # Honor $PORT if set, default to 9800 for your compose mapping
    port = int(os.getenv("PORT", "9800"))
    app.run(host="0.0.0.0", port=port, debug=False)
