# Homelab Infrastructure Project

A structured homelab project built to apply modern DevOps and SRE practices in a self-managed environment. This is not a tutorial stack — every component was configured, debugged, and wired together from scratch.

> **Live demo:** `http://your-domain.com` _(coming soon — AWS deployment in progress)_

---

## What This Is

A full-stack observability and application platform running on a single Proxmox host, built across four phases:

- **Infrastructure as Code** — VMs provisioned with Terraform, configured with Ansible
- **Containerized application stack** — Flask weather app, custom Prometheus exporter, Grafana, Loki, Promtail, nginx reverse proxy
- **Custom observability tooling** — a hand-built Prometheus exporter (`statporter`) that collects per-container CPU, memory, network, and disk I/O metrics via the Docker socket
- **CI/CD pipeline** — GitHub Actions (in progress)

---

## Architecture

```
                        ┌─────────────────────────────────────┐
                        │           Docker Host               │
                        │                                     │
  Browser ──── :80 ──▶  │  nginx (reverse proxy)              │
                        │     │                               │
                        │     ├──▶ weather-app  :5000         │
                        │     ├──▶ grafana       :3000        │
                        │     └──▶ prometheus    :9090        │
                        │                                     │
                        │  prometheus ◀── statporter  :9800   │
                        │  prometheus ◀── weather-app         │
                        │  prometheus ◀── grafana             │
                        │  prometheus ◀── loki                │
                        │                                     │
                        │  loki ◀── promtail                  │
                        │  promtail ── /var/run/docker.sock   │
                        └─────────────────────────────────────┘
```

---

## Stack

| Service     | Image                      | Purpose                                     |
| ----------- | -------------------------- | ------------------------------------------- |
| nginx       | `nginx:1.27-alpine`        | Reverse proxy, sub-path routing             |
| weather-app | `burningstar4/weather-app` | Flask app — UI + OpenWeatherMap API         |
| prometheus  | `prom/prometheus:v3.3.1`   | Metrics collection and storage              |
| grafana     | `grafana/grafana:11.6.1`   | Metrics and log visualization               |
| loki        | `grafana/loki:3.5.0`       | Log aggregation                             |
| promtail    | `grafana/promtail:3.5.0`   | Log shipping — Docker socket autodiscovery  |
| statporter  | `burningstar4/statporter`  | Custom Prometheus exporter for Docker stats |

---

## Statporter

`statporter` is a custom-built Prometheus exporter written in Python/Flask, served by Gunicorn. It was built to work around cgroups v2 compatibility issues with existing exporters at the time.

It collects the following metrics per container by querying the Docker socket directly:

| Metric                                   | Description                          |
| ---------------------------------------- | ------------------------------------ |
| `container_cpu_percent`                  | CPU usage %                          |
| `container_memory_usage_bytes`           | Memory usage in bytes                |
| `container_memory_percent`               | Memory usage %                       |
| `container_network_receive_bytes_total`  | Cumulative network bytes received    |
| `container_network_transmit_bytes_total` | Cumulative network bytes transmitted |
| `container_blkio_read_bytes_total`       | Cumulative disk I/O bytes read       |
| `container_blkio_write_bytes_total`      | Cumulative disk I/O bytes written    |

---

## Screenshots

### Weather App

![Weather App](docs/screenshots/weather-app.png)

### Grafana — Container Metrics Dashboard

![Grafana Dashboard](docs/screenshots/grafana-dashboard.png)

---

## Prerequisites

- Docker and Docker Compose
- An [OpenWeatherMap API key](https://openweathermap.org/api) (free tier works)

---

## Running Locally

```bash
# Clone the repo
git clone https://github.com/Gcedwards91/homelab-infra.git
cd homelab-infra/weather-app/docker-final

# Create your environment file
cp .env.example .env
# Edit .env and set a real GRAFANA_ADMIN_PASSWORD

# Pull and start the stack
docker compose pull
docker compose up -d

# Verify all services are healthy
docker compose ps
```

Once running:

| Service     | URL                         |
| ----------- | --------------------------- |
| Weather App | http://localhost            |
| Grafana     | http://localhost/grafana    |
| Prometheus  | http://localhost/prometheus |

Grafana is accessible without login in read-only mode. To make changes, log in with the credentials from your `.env` file.

---

## Project Structure

```
homelab-infra/
├── terraform/          # VM provisioning (Proxmox via Telmate provider)
├── lamp-ansible/       # Ansible playbooks — LAMP stack
├── scripts/            # Bash scripts — VM template preparation
├── weather-app/
│   └── docker-final/   # Production Docker Compose stack
│       ├── statporter/ # Custom Prometheus exporter
│       ├── grafana/    # Provisioned dashboards and datasources
│       ├── prometheus/ # Scrape config
│       ├── loki/       # Log retention config
│       ├── promtail/   # Log shipping config
│       └── nginx/      # Reverse proxy config
└── container-project/  # Earlier containerization work
```

---

## What's Next

- [ ] Migrate stack to Kubernetes (manifests in progress)
- [ ] Deploy to AWS (ECS or EKS) with Terraform
- [ ] TLS via ACM + Route53 custom domain
- [ ] CI/CD pipeline via GitHub Actions
- [ ] Secrets management via AWS Secrets Manager

---

## Build Journal

The full phase-by-phase build notes, lessons learned, and troubleshooting log are documented in the [Wiki](https://github.com/Gcedwards91/homelab-infra/wiki/Lessons-Learned-&-Journey).

---

## Author

**George Edwards**
[GitHub](https://github.com/Gcedwards91) · [LinkedIn](https://www.linkedin.com/in/gcedwards91/)
