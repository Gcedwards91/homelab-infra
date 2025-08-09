from flask import Flask, Response
import docker
import platform
import os
import json
import tempfile
import sys

app = Flask(__name__)
print("Statporter is starting...")


def get_docker_client():
    system = platform.system()
    in_container = os.path.exists("/.dockerenv")
    if system == "Windows" and not in_container:
        return docker.DockerClient(base_url="npipe:////./pipe/docker_engine")
    return docker.DockerClient(base_url="unix://var/run/docker.sock")


client = get_docker_client()


def get_metrics():
    lines = []
    containers = client.containers.list()
    debug_dir = os.path.join(tempfile.gettempdir(), "debug_stats")
    os.makedirs(debug_dir, exist_ok=True)

    for container in containers:
        name = container.name.replace("-", "_")
        try:
            stats = container.stats(stream=False)
        except Exception as e:
            lines.append(f"# Could not retrieve stats for {name}: {e}")
            continue

        try:
            debug_path = os.path.join(debug_dir, f"{name}_stats.json")
            with open(debug_path, "w") as f:
                json.dump(stats, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            lines.append(f"# Could not write debug for {name}: {e}")

        try:
            cpu_stats = stats.get("cpu_stats", {})
            precpu_stats = stats.get("precpu_stats", {})

            cpu_total = cpu_stats.get("cpu_usage", {}).get("total_usage", 0)
            precpu_total = precpu_stats.get("cpu_usage", {}).get("total_usage", 0)

            cpu_system = cpu_stats.get("system_cpu_usage", None)
            precpu_system = precpu_stats.get("system_cpu_usage", None)

            cpu_percent = 0.0
            if cpu_system is not None and precpu_system is not None:
                cpu_delta = cpu_total - precpu_total
                system_delta = cpu_system - precpu_system
                if system_delta > 0 and cpu_delta > 0:
                    percpu = cpu_stats.get("cpu_usage", {}).get("percpu_usage", [])
                    cpu_percent = (cpu_delta / system_delta) * len(percpu) * 100.0
            else:
                lines.append(
                    f"# {name} missing system_cpu_usage (cpu_system={cpu_system}, precpu_system={precpu_system})"
                )

            mem_usage = stats.get("memory_stats", {}).get("usage", 0)
            mem_limit = stats.get("memory_stats", {}).get("limit", 1)
            mem_percent = (mem_usage / mem_limit) * 100.0

            net_rx, net_tx = 0, 0
            for interface in stats.get("networks", {}).values():
                net_rx += interface.get("rx_bytes", 0)
                net_tx += interface.get("tx_bytes", 0)

            lines.append(f'container_cpu_percent{{name="{name}"}} {cpu_percent}')
            lines.append(f'container_memory_usage_bytes{{name="{name}"}} {mem_usage}')
            lines.append(f'container_memory_percent{{name="{name}"}} {mem_percent}')
            lines.append(
                f'container_network_receive_bytes_total{{name="{name}"}} {net_rx}'
            )
            lines.append(
                f'container_network_transmit_bytes_total{{name="{name}"}} {net_tx}'
            )
        except Exception as e:
            lines.append(f"# Error processing metrics for {name}: {e}")

    return "\n".join(lines) + "\n"


@app.route("/metrics")
def metrics():
    print("Endpoint hit!")
    sys.stdout.flush()
    return Response(get_metrics(), mimetype="text/plain")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9800, debug=True)
