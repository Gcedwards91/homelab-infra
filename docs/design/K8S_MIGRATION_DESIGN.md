# Kubernetes Migration - Design Specification

**Status:** IN PROGRESS
**Target:** Replace Docker Compose single-host stack with Kubernetes (k3s locally, EKS on AWS)
**Manifest repository:** `homelab-k8/k8s/` (application manifests); `statporter/deploy/` (statporter - already complete)
**Estimated scope:** ~30 files created or modified across homelab-infra, homelab-k8, and statporter

---

## Background Required

Before implementing, read:

- `CLAUDE.md` - full stack architecture, service table, playground constraints, alert expression notes, known gotchas
- `weather-app/docker-final/docker-compose.yml` - authoritative current service definitions and config
- `weather-app/docker-final/nginx/nginx.conf` - sub-path routing, security headers, 403 blocks to preserve
- `weather-app/docker-final/prometheus/prometheus.yml` - scrape job names (job names must be preserved - alerts reference them)
- `weather-app/docker-final/prometheus/rules/alerts.yml` - all alert expressions; several change with the K8s label set
- `weather-app/docker-final/promtail/promtail-config.yaml` - Docker socket approach being replaced by pod log path approach
- `weather-app/docker-src/playground.py` - Docker socket calls being replaced with Kubernetes API calls
- `statporter/deploy/` - complete K8s manifests for statporter (ServiceAccount, ClusterRole, Deployment, Service)
- `statporter/GO-REWRITE-DESIGN.md` - statporter label migration path (name= -> pod/namespace/container=)

---

## Summary

The Docker Compose stack runs all services on a single host using a shared bridge network, with the Docker socket as the control plane for log shipping (Promtail), container stats (statporter), and the playground toggle (weather-app). None of these Docker socket dependencies translate directly to Kubernetes.

```
Current (Docker Compose):
  Host
  └── docker bridge "monitoring"
        ├── nginx (reverse proxy, :80 exposed)
        ├── weather-app (mounts /var/run/docker.sock rw - playground toggle)
        ├── demo-container
        ├── prometheus
        ├── grafana
        ├── loki
        ├── promtail (mounts /var/run/docker.sock ro + /var/lib/docker/containers)
        ├── statporter (mounts /var/run/docker.sock ro - container stats)
        ├── tempo
        ├── otel-collector
        └── alertmanager

Target (Kubernetes):
  Cluster (k3s on dreadnought / EKS on AWS)
  └── namespace: homelab
        ├── nginx-ingress-controller (IngressClass: nginx)
        ├── Ingress: homelab (sub-path routing + security headers)
        ├── Deployment: weather-app (calls K8s API for playground toggle - no socket)
        ├── Deployment: demo-container
        ├── Deployment: prometheus (ClusterRole for K8s service discovery)
        ├── Deployment: grafana
        ├── Deployment: loki
        ├── DaemonSet: promtail (reads /var/log/pods - no socket)
        ├── Deployment: statporter (K8s API for container stats - already complete)
        ├── Deployment: tempo
        ├── Deployment: otel-collector
        └── Deployment: alertmanager
```

**Three Docker socket dependencies eliminated:**

| Service     | Docker dependency                                                         | K8s replacement                                       |
| ----------- | ------------------------------------------------------------------------- | ----------------------------------------------------- |
| statporter  | `/var/run/docker.sock` (ro) - container stats                             | metrics-server + kubelet stats API (already complete) |
| promtail    | `/var/run/docker.sock` (ro) + `/var/lib/docker/containers` - log shipping | DaemonSet mounting `/var/log/pods`                    |
| weather-app | `/var/run/docker.sock` (rw) - playground container toggle                 | `kubernetes` Python client + Role/RoleBinding         |

---

## Design Decisions (Resolved)

### Decision 1 - Ingress controller

**Chosen: nginx-ingress (not Traefik).**

k3s ships with Traefik by default, but the current nginx.conf has specific behavior that needs to be preserved: sub-path routing for Grafana and Prometheus, 403 blocks on `/metrics` and `/api/playground/status`, W3C TraceContext header passthrough, and a CSP with `'unsafe-eval'`. nginx-ingress preserves configuration parity and allows direct reuse of the existing header set. Install nginx-ingress via its manifest at k3s bootstrap and disable Traefik with `--disable traefik`.

---

### Decision 2 - Namespace layout

**Chosen: single namespace `homelab`.**

App and observability services in one namespace. No reason to split at single-operator homelab scale - it adds RBAC complexity without operational benefit. All inter-service calls use short DNS names (`loki`, `prometheus`, `grafana`, etc.) within the namespace, matching the current Docker bridge behavior exactly.

---

### Decision 3 - Playground API migration

**Chosen: Python `kubernetes` client with namespaced Role scoped to the demo-container Deployment.**

weather-app gets a ServiceAccount. A `Role` (not ClusterRole) in the `homelab` namespace grants `get` and `patch` on `deployments/scale`, with `resourceNames: ["demo-container"]` as an additional scope limiter. The playground toggle changes from `container.start()`/`container.stop()` to patching `spec.replicas` between 0 and 1. The hardcoded `DEMO_CONTAINER = "demo-container"` constant is preserved - never takes container name from request input.

---

### Decision 4 - Log shipping

**Chosen: Promtail DaemonSet reading `/var/log/pods`.**

Promtail supports Kubernetes pod log discovery natively via `kubernetes_sd_configs` and the standard node log path `/var/log/pods/<namespace>_<pod>_<uid>/<container>/*.log`. This is the direct replacement for the Docker socket approach. Grafana Alloy is the forward-looking choice but adds migration complexity. Promtail DaemonSet is the minimal-change path.

---

### Decision 5 - Prometheus scrape config

**Chosen: static ClusterIP service endpoints (not `kubernetes_sd_configs`).**

The set of services is known and fixed. Static configs using Kubernetes DNS (`weather-app.homelab.svc.cluster.local:5000`, etc.) are simpler and preserve the existing job names exactly. Job names matter: the `ContainerDown` alert references `job=~"weather_app|loki|prometheus|grafana|statporter"`. Changing job names would break that alert silently. Static scrape config avoids that risk.

---

### Decision 6 - Integration test strategy

**Chosen: Keep Docker Compose-based integration tests for CI; add separate k8s smoke tests.**

The existing CI integration tests (`pytest weather-app/docker-final/tests/`) test the application stack running under Docker Compose. These continue to run on every push and provide the pre-merge gate. A separate smoke test (`homelab-k8/tests/`) runs against a live k3s cluster via `workflow_dispatch` to verify the K8s manifests, using the same test patterns but targeting cluster endpoints.

---

## Part 1 - Cluster Bootstrap (k3s + Ansible)

### Target: `homelab-k8/ansible/k3s/`

k3s is the single-node cluster runtime for the on-prem deployment. The ansible playbooks in `homelab-k8/ansible/k3s/` bootstrap and configure the cluster. The `dreadnought` inventory entry already exists.

### `ansible/k3s/playbooks/k3s.yml` - install k3s

Key tasks:

```yaml
- name: Install k3s (Traefik disabled)
  shell: >
    curl -sfL https://get.k3s.io | sh -s - --disable traefik
  creates: /usr/local/bin/k3s

- name: Wait for node to be ready
  command: kubectl get nodes
  register: nodes
  until: "'Ready' in nodes.stdout"
  retries: 20
  delay: 5

- name: Copy kubeconfig to user home
  copy:
    src: /etc/rancher/k3s/k3s.yaml
    dest: "{{ ansible_env.HOME }}/.kube/config"
    remote_src: true
    owner: "{{ ansible_user }}"
    mode: "0600"
```

> `--disable traefik` is required. k3s 1.26+ installs Traefik 2 by default. nginx-ingress is installed separately in bootstrap.yml. Both ingress controllers running simultaneously will fight for port 80.

### `ansible/k3s/playbooks/bootstrap.yml` - post-install setup

Key tasks:

```yaml
- name: Install nginx-ingress-controller
  command: >
    kubectl apply -f
    https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.0/deploy/static/provider/cloud/deploy.yaml

- name: Wait for nginx-ingress to be ready
  command: >
    kubectl wait --namespace ingress-nginx
    --for=condition=ready pod
    --selector=app.kubernetes.io/component=controller
    --timeout=120s

- name: Create homelab namespace
  command: kubectl apply -f homelab-k8/k8s/namespace.yaml

- name: Apply all manifests
  command: kubectl apply -k homelab-k8/k8s/
```

> k3s bundles metrics-server by default. No separate metrics-server install needed. Verify with `kubectl top pods -n homelab` after bootstrap.

---

## Part 2 - Repository Layout and Namespace

### `homelab-k8/k8s/` directory structure

```
homelab-k8/k8s/
├── namespace.yaml
├── kustomization.yaml
├── ingress/
│   ├── ingress.yaml
│   └── configmap-proxy-headers.yaml
├── app/
│   ├── weather-app/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── serviceaccount.yaml
│   │   └── rbac.yaml
│   └── demo-container/
│       ├── deployment.yaml
│       └── service.yaml
├── observability/
│   ├── prometheus/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── configmap.yaml        # prometheus.yml + alerts.yml
│   │   ├── pvc.yaml
│   │   └── rbac.yaml             # ClusterRole for K8s SD (future)
│   ├── grafana/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── configmap.yaml        # grafana.ini + provisioning files + dashboards
│   │   └── pvc.yaml
│   ├── loki/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── configmap.yaml
│   │   └── pvc.yaml
│   ├── promtail/
│   │   ├── daemonset.yaml
│   │   ├── service.yaml
│   │   ├── configmap.yaml
│   │   ├── serviceaccount.yaml
│   │   └── rbac.yaml
│   ├── alertmanager/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── configmap.yaml
│   │   └── pvc.yaml
│   ├── tempo/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── configmap.yaml        # tempo-config.yml; data is emptyDir (ephemeral by design)
│   └── otel-collector/
│       ├── deployment.yaml
│       ├── service.yaml
│       └── configmap.yaml
└── secrets/
    └── README.md                  # never commit actual secrets - instructions only
```

### `namespace.yaml`

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: homelab
```

### `kustomization.yaml`

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: homelab
resources:
  - namespace.yaml
  - ingress/ingress.yaml
  - ingress/configmap-proxy-headers.yaml
  - app/weather-app/deployment.yaml
  - app/weather-app/service.yaml
  - app/weather-app/serviceaccount.yaml
  - app/weather-app/rbac.yaml
  - app/demo-container/deployment.yaml
  - app/demo-container/service.yaml
  - observability/prometheus/deployment.yaml
  - observability/prometheus/service.yaml
  - observability/prometheus/configmap.yaml
  - observability/prometheus/pvc.yaml
  - observability/grafana/deployment.yaml
  - observability/grafana/service.yaml
  - observability/grafana/configmap.yaml
  - observability/grafana/pvc.yaml
  - observability/loki/deployment.yaml
  - observability/loki/service.yaml
  - observability/loki/configmap.yaml
  - observability/loki/pvc.yaml
  - observability/promtail/daemonset.yaml
  - observability/promtail/service.yaml
  - observability/promtail/configmap.yaml
  - observability/promtail/serviceaccount.yaml
  - observability/promtail/rbac.yaml
  - observability/alertmanager/deployment.yaml
  - observability/alertmanager/service.yaml
  - observability/alertmanager/configmap.yaml
  - observability/alertmanager/pvc.yaml
  - observability/tempo/deployment.yaml
  - observability/tempo/service.yaml
  - observability/tempo/configmap.yaml
  - observability/otel-collector/deployment.yaml
  - observability/otel-collector/service.yaml
  - observability/otel-collector/configmap.yaml
```

> Statporter manifests are in a separate repo (`statporter/deploy/`). Apply them separately with `kubectl apply -f statporter/deploy/` after the homelab-k8 manifests. The statporter RBAC requires cluster-level permissions (nodes, nodes/proxy) and cannot be included in the kustomization without a ClusterRole.

---

## Part 3 - statporter (COMPLETE)

Manifests are in `statporter/deploy/`. No changes needed here. Apply with:

```sh
kubectl apply -f statporter/deploy/
```

This creates: `ServiceAccount/statporter`, `ClusterRole/statporter`, `ClusterRoleBinding/statporter`, `Deployment/statporter`, `Service/statporter` in the `default` namespace.

> The statporter manifests use `namespace: default`. If the homelab namespace is preferred, update the `namespace:` field in all four files and re-apply. The ClusterRoleBinding subject namespace must also match.

Prometheus scrapes statporter at `statporter.default.svc.cluster.local:9800/metrics` (or `statporter.homelab.svc.cluster.local:9800/metrics` if the namespace is changed). Update the prometheus.yml scrape target accordingly - see Part 9.

---

## Part 4 - weather-app: Application Manifests and Playground Migration

### The change

The Docker socket mount on weather-app is removed. The playground toggle replaces `docker.from_env()` calls with the Kubernetes Python client patching the demo-container Deployment's replica count.

### `app/weather-app/serviceaccount.yaml`

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: weather-app
  namespace: homelab
```

### `app/weather-app/rbac.yaml`

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: weather-app
  namespace: homelab
rules:
  - apiGroups: ["apps"]
    resources: ["deployments/scale"]
    verbs: ["get", "patch"]
    resourceNames: ["demo-container"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: weather-app
  namespace: homelab
subjects:
  - kind: ServiceAccount
    name: weather-app
    namespace: homelab
roleRef:
  kind: Role
  name: weather-app
  apiGroup: rbac.authorization.k8s.io
```

> `resourceNames: ["demo-container"]` is the scope limiter. weather-app can only scale the demo-container Deployment, nothing else. This replaces the `DEMO_CONTAINER` constant as the blast-radius control. Both the constant and the RBAC restriction must be present.

### `app/weather-app/deployment.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: weather-app
  namespace: homelab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: weather-app
  template:
    metadata:
      labels:
        app: weather-app
    spec:
      serviceAccountName: weather-app
      containers:
        - name: weather-app
          image: burningstar4/weather-app:latest
          ports:
            - containerPort: 5000
          env:
            - name: FLASK_SECRET_KEY
              valueFrom:
                secretKeyRef:
                  name: weather-app-secrets
                  key: flask-secret-key
            - name: PLAYGROUND_SECRET
              valueFrom:
                secretKeyRef:
                  name: weather-app-secrets
                  key: playground-secret
            - name: PLAYGROUND_ADMIN_KEY
              valueFrom:
                secretKeyRef:
                  name: weather-app-secrets
                  key: playground-admin-key
            - name: OTEL_EXPORTER_OTLP_ENDPOINT
              value: "http://otel-collector:4317"
            - name: OTEL_SERVICE_NAME
              value: "weather-app"
            - name: DEMO_NAMESPACE
              value: "homelab"
          resources:
            limits:
              cpu: "1000m"
              memory: "256Mi"
            requests:
              cpu: "250m"
              memory: "128Mi"
          livenessProbe:
            httpGet:
              path: /healthz
              port: 5000
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /healthz
              port: 5000
            initialDelaySeconds: 5
            periodSeconds: 10
```

> No `hostPath` or socket volume mount. The `serviceAccountName: weather-app` injects the token at `/var/run/secrets/kubernetes.io/serviceaccount/`. The Python `kubernetes` client reads this automatically when `config.load_incluster_config()` is called.

### `playground.py` changes

**Step 1 - Add to `requirements.txt`:**

```
kubernetes
```

Remove `docker` from requirements.txt (no longer needed).

**Step 2 - Replace Docker import and socket initialization:**

Remove:

```python
import docker
_docker_client = docker.from_env()
```

Add:

```python
import os
from kubernetes import client as k8s_client, config as k8s_config

k8s_config.load_incluster_config()
_k8s_apps = k8s_client.AppsV1Api()

DEMO_CONTAINER = "demo-container"
DEMO_NAMESPACE = os.getenv("DEMO_NAMESPACE", "homelab")
```

**Step 3 - Replace the toggle function body:**

The function signature and the `hmac.compare_digest` passphrase check are unchanged. Only the inner Docker calls change:

```python
# Old (Docker):
container = _docker_client.containers.get(DEMO_CONTAINER)
if action == "start":
    container.start()
elif action == "stop":
    container.stop()

# New (Kubernetes):
replicas = 1 if action == "start" else 0
body = {"spec": {"replicas": replicas}}
_k8s_apps.patch_namespaced_deployment_scale(
    name=DEMO_CONTAINER,
    namespace=DEMO_NAMESPACE,
    body=body,
)
```

**Step 4 - Replace the status check:**

```python
# Old (Docker):
container = _docker_client.containers.get(DEMO_CONTAINER)
is_running = container.status == "running"

# New (Kubernetes):
deployment = _k8s_apps.read_namespaced_deployment_scale(
    name=DEMO_CONTAINER,
    namespace=DEMO_NAMESPACE,
)
is_running = (deployment.spec.replicas or 0) > 0
```

> When demo-container has 0 replicas, its Service has no endpoints. HTTP calls to `http://demo-container:8080/stress` from the stress endpoint will fail with a connection error - this is the correct "stopped" behavior. The Service resource itself stays up; only the pod count changes.

### `app/demo-container/deployment.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: demo-container
  namespace: homelab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: demo-container
  template:
    metadata:
      labels:
        app: demo-container
    spec:
      containers:
        - name: demo-container
          image: burningstar4/demo-container:latest
          ports:
            - containerPort: 8080
          resources:
            limits:
              cpu: "1000m"
              memory: "128Mi"
            requests:
              cpu: "100m"
              memory: "64Mi"
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 30
```

### `app/demo-container/service.yaml`

```yaml
apiVersion: v1
kind: Service
metadata:
  name: demo-container
  namespace: homelab
spec:
  selector:
    app: demo-container
  ports:
    - port: 8080
      targetPort: 8080
  type: ClusterIP
```

---

## Part 5 - Observability Stack Manifests

All services use ClusterIP Services and standard Deployments (replicas: 1 for all). Each service gets a ConfigMap holding its config file(s). Persistent data uses PVCs backed by the k3s local-path storage class. Tempo data remains ephemeral (emptyDir) - same as the Compose stack.

### PVC sizes

| Service      | PVC name          | Size |
| ------------ | ----------------- | ---- |
| prometheus   | prometheus-data   | 5Gi  |
| grafana      | grafana-data      | 2Gi  |
| loki         | loki-data         | 10Gi |
| alertmanager | alertmanager-data | 1Gi  |
| tempo        | (none - emptyDir) | -    |

> k3s local-path provisioner creates PVCs as hostPath volumes under `/var/lib/rancher/k3s/storage/`. Back this path up if trace/metric retention matters.

### ConfigMap strategy

Config files that currently live as bind mounts in the Compose stack become ConfigMap data keys:

| ConfigMap               | Keys                           | Source file                  |
| ----------------------- | ------------------------------ | ---------------------------- |
| `prometheus-config`     | `prometheus.yml`, `alerts.yml` | prometheus/ directory        |
| `grafana-config`        | `grafana.ini`                  | grafana/grafana.ini          |
| `grafana-provisioning`  | One key per provisioning file  | grafana/provisioning/\*_/_   |
| `grafana-dashboards`    | One key per dashboard JSON     | grafana/dashboards/\*.json   |
| `loki-config`           | `loki-config.yaml`             | loki/                        |
| `promtail-config`       | `promtail-config.yaml`         | new K8s version - see Part 6 |
| `alertmanager-config`   | `alertmanager.yml`             | alertmanager/                |
| `tempo-config`          | `tempo-config.yml`             | tempo-config.yml             |
| `otel-collector-config` | `config.yaml`                  | otel-collector-config.yml    |

> The grafana provisioning and dashboard ConfigMaps will be large. If the dashboard JSONs exceed the 1MB ConfigMap limit, use an initContainer to copy them from the image or an emptyDir sidecar. At current dashboard count this is not a concern.

### Grafana Deployment environment variables

These change from `.env` file values to Secret references:

```yaml
env:
  - name: GF_SECURITY_ADMIN_PASSWORD
    valueFrom:
      secretKeyRef:
        name: grafana-secrets
        key: admin-password
  - name: GF_SECURITY_ADMIN_USER
    value: "admin"
  - name: GF_AUTH_ANONYMOUS_ENABLED
    value: "true"
  - name: GF_AUTH_ANONYMOUS_ORG_ROLE
    value: "Viewer"
  - name: GF_SERVER_ROOT_URL
    value: "http://dreadnought/grafana"
  - name: GF_SERVER_SERVE_FROM_SUB_PATH
    value: "true"
  - name: GF_PATHS_PROVISIONING
    value: "/etc/grafana/provisioning"
```

> `GF_SERVER_ROOT_URL` must use the actual hostname or load balancer address. On k3s with nginx-ingress, this is the node's IP or hostname. On EKS, this is the ALB DNS name (or Route53 alias). The sub-path suffix `/grafana` is required for the Grafana Ingress rule to work correctly.

---

## Part 6 - Promtail DaemonSet

This is the most structurally different service migration. The Docker socket approach cannot run in K8s - there is no Docker daemon to query. The K8s replacement reads log files from the node's pod log directory directly.

### What changes

|                   | Docker Compose                                        | K8s DaemonSet                                      |
| ----------------- | ----------------------------------------------------- | -------------------------------------------------- |
| Kind              | Service (one instance)                                | DaemonSet (one pod per node)                       |
| Log source        | `/var/run/docker.sock` + `/var/lib/docker/containers` | `/var/log/pods` (node hostPath)                    |
| Service discovery | `docker_sd_configs`                                   | `kubernetes_sd_configs` (pod role)                 |
| Container filter  | `label_logging=true`                                  | All pods in namespace (filtered by label)          |
| Log path format   | `/var/lib/docker/containers/<id>/<id>-json.log`       | `/var/log/pods/<ns>_<pod>_<uid>/<container>/*.log` |

### `observability/promtail/serviceaccount.yaml`

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: promtail
  namespace: homelab
```

### `observability/promtail/rbac.yaml`

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: promtail
rules:
  - apiGroups: [""]
    resources: ["nodes", "nodes/proxy", "services", "endpoints", "pods"]
    verbs: ["get", "watch", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: promtail
subjects:
  - kind: ServiceAccount
    name: promtail
    namespace: homelab
roleRef:
  kind: ClusterRole
  name: promtail
  apiGroup: rbac.authorization.k8s.io
```

### `observability/promtail/configmap.yaml` - updated promtail-config.yaml

The Docker socket scrape config is replaced entirely:

```yaml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki.homelab.svc.cluster.local:3100/loki/api/v1/push

scrape_configs:
  - job_name: kubernetes-pods
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names: ["homelab"]

    pipeline_stages:
      - docker: {}
      - json:
          expressions:
            asctime:
            levelname:
            name:
            message:
            pathname:
            lineno:
            event:
            request_id:
            method:
            path:
            remote_addr:
            status:

    relabel_configs:
      # Keep only pods with logging=true label
      - source_labels: [__meta_kubernetes_pod_label_logging]
        regex: "true"
        action: keep

      # Pod name -> pod label
      - source_labels: [__meta_kubernetes_pod_name]
        target_label: pod

      # Namespace -> namespace label
      - source_labels: [__meta_kubernetes_namespace]
        target_label: namespace

      # Container name -> container label (replaces the 'container' label from Docker)
      - source_labels: [__meta_kubernetes_pod_container_name]
        target_label: container

      # App label -> job label
      - source_labels: [__meta_kubernetes_pod_label_app]
        target_label: job

      # Set log path from pod UID and container name
      - source_labels:
          [
            __meta_kubernetes_namespace,
            __meta_kubernetes_pod_name,
            __meta_kubernetes_pod_uid,
            __meta_kubernetes_pod_container_name,
          ]
        action: replace
        regex: (.+);(.+);(.+);(.+)
        replacement: /var/log/pods/$1_$2_$3/$4/*.log
        target_label: __path__
```

> The `container` label in Loki changes from the container name (e.g., `weather-app`) to the same name because the K8s container name matches. Existing Grafana log queries using `{container="weather-app"}` continue to work. The `job` label maps from the pod's `app=` label, so pods must have an `app:` label set in their Deployment template.

### `observability/promtail/daemonset.yaml`

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: promtail
  namespace: homelab
spec:
  selector:
    matchLabels:
      app: promtail
  template:
    metadata:
      labels:
        app: promtail
    spec:
      serviceAccountName: promtail
      tolerations:
        - key: node-role.kubernetes.io/control-plane
          effect: NoSchedule
      containers:
        - name: promtail
          image: grafana/promtail:3.6.11
          args: ["-config.file=/etc/promtail/promtail.yaml"]
          volumeMounts:
            - name: config
              mountPath: /etc/promtail
            - name: pods
              mountPath: /var/log/pods
              readOnly: true
            - name: positions
              mountPath: /tmp
          resources:
            limits:
              cpu: "500m"
              memory: "256Mi"
            requests:
              cpu: "100m"
              memory: "128Mi"
      volumes:
        - name: config
          configMap:
            name: promtail-config
        - name: pods
          hostPath:
            path: /var/log/pods
        - name: positions
          emptyDir: {}
```

> The `toleration` for `control-plane` ensures Promtail runs on the k3s control plane node (single-node setup). Without it, the DaemonSet pod will not schedule on the control plane.
>
> Promtail's pod `logging=true` label must be present in the DaemonSet template `labels:` to avoid Promtail shipping its own logs to Loki recursively. Promtail does handle this gracefully, but it produces noisy self-reference entries. Omit the `logging: "true"` label from the DaemonSet pod template.

---

## Part 7 - Ingress

### nginx-ingress controller ConfigMap - enable snippets

nginx-ingress 1.9+ disables `allow-snippet-annotations` by default. The CSP and header passthrough require it. Patch the controller ConfigMap after install:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: ingress-nginx-controller
  namespace: ingress-nginx
data:
  allow-snippet-annotations: "true"
```

### `ingress/configmap-proxy-headers.yaml`

Proxy headers passed to all upstreams:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: proxy-headers
  namespace: homelab
data:
  traceparent: "$http_traceparent"
  tracestate: "$http_tracestate"
  X-Real-IP: "$remote_addr"
  X-Forwarded-For: "$proxy_add_x_forwarded_for"
  X-Forwarded-Proto: "$scheme"
  X-Forwarded-Host: "$http_host"
```

### `ingress/ingress.yaml`

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: homelab
  namespace: homelab
  annotations:
    nginx.ingress.kubernetes.io/proxy-headers-hash-bucket-size: "64"
    nginx.ingress.kubernetes.io/proxy-set-headers: "homelab/proxy-headers"

    nginx.ingress.kubernetes.io/configuration-snippet: |
      add_header X-Content-Type-Options "nosniff" always;
      add_header X-Frame-Options "DENY" always;
      add_header Referrer-Policy "strict-origin-when-cross-origin" always;
      add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self'; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self';" always;

    nginx.ingress.kubernetes.io/server-snippet: |
      location = /metrics { return 403; }
      location = /api/playground/status { return 403; }

spec:
  ingressClassName: nginx
  rules:
    - http:
        paths:
          - path: /grafana
            pathType: Prefix
            backend:
              service:
                name: grafana
                port:
                  number: 3000
          - path: /prometheus
            pathType: Prefix
            backend:
              service:
                name: prometheus
                port:
                  number: 9090
          - path: /
            pathType: Prefix
            backend:
              service:
                name: weather-app
                port:
                  number: 5000
```

> No `rewrite-target` annotations are needed. Grafana handles the `/grafana` prefix via `GF_SERVER_SERVE_FROM_SUB_PATH=true`. Prometheus handles `/prometheus` via `--web.external-url` and `--web.route-prefix=/`. The current Compose nginx.conf proxies both services the same way, without stripping the prefix before forwarding.
>
> The `server-snippet` blocks `/metrics` and `/api/playground/status` at the nginx level. These return 403 regardless of which upstream they would otherwise route to. This preserves the same restriction as the current nginx.conf.
>
> The `X-Frame-Options: DENY` header is preserved from the current nginx.conf. Note that Grafana embeds iframes for panels. If iframe embedding within the same origin is needed, change this to `SAMEORIGIN` (consistent with what the nginx.conf currently sets in one location - verify current value before deploying).

---

## Part 8 - Secrets

Never commit secret values. Create them with `kubectl create secret generic` before applying manifests.

### Secrets required before `kubectl apply -k homelab-k8/k8s/`

```sh
kubectl create secret generic weather-app-secrets \
  --namespace homelab \
  --from-literal=flask-secret-key='<value>' \
  --from-literal=playground-secret='<value>' \
  --from-literal=playground-admin-key='<value>'

kubectl create secret generic grafana-secrets \
  --namespace homelab \
  --from-literal=admin-password='<value>'

kubectl create secret generic weather-app-owm-key \
  --namespace homelab \
  --from-literal=api-key='<value>'
```

> The OpenWeatherMap API key is currently baked into the running container via an env var set at Compose startup. In K8s it should be a Secret, injected the same way as the other weather-app secrets. Update `weather.py` to read it from `os.getenv("OWM_API_KEY")` and add the env injection to the Deployment.
>
> `secrets/README.md` in the manifest repo documents which secrets are required and what values to use - never the values themselves.

---

## Part 9 - Prometheus Scrape Config Updates

The container name DNS entries (`weather-app`, `grafana`, etc.) that work on the Docker bridge network become Kubernetes Service DNS names in the format `<service>.<namespace>.svc.cluster.local`. Within the same namespace, short names (`weather-app`, `grafana`) resolve identically. The Prometheus Deployment is in the `homelab` namespace, so all targets remain short-name resolvable.

**Job names must not change.** The `ContainerDown` alert filters by `job=~"weather_app|loki|prometheus|grafana|statporter"`. Changing job names silently breaks this alert.

### Updated `prometheus.yml`

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - /etc/prometheus/rules/*.yml

alerting:
  alertmanagers:
    - static_configs:
        - targets: ["alertmanager:9093"]

scrape_configs:
  - job_name: "prometheus"
    static_configs:
      - targets: ["prometheus:9090"]

  - job_name: "weather_app"
    static_configs:
      - targets: ["weather-app:5000"]

  - job_name: "grafana"
    metrics_path: /grafana/metrics
    static_configs:
      - targets: ["grafana:3000"]
    params:
      orgId: ["1"]

  - job_name: "loki"
    static_configs:
      - targets: ["loki:3100"]

  - job_name: "promtail"
    static_configs:
      - targets: ["promtail:9080"]

  - job_name: "statporter"
    scrape_interval: 10s
    scrape_timeout: 5s
    static_configs:
      - targets: ["statporter.default.svc.cluster.local:9800"]
```

> `statporter` is the only target with a non-homelab namespace. If the statporter manifests are updated to use `namespace: homelab`, this target becomes `statporter:9800` like the rest. Until then, the FQDN is required.

---

## Part 10 - Alert Expression Updates

Three alert expressions reference statporter metric labels by name. The Go statporter uses `pod`, `namespace`, and `container` labels instead of the Python version's `name=` label. Two additional alert descriptions reference `$labels.name` which no longer exists.

### `alerts.yml` changes

**`DemoContainerDown`** (breaking change - expression and annotations both change):

```yaml
# Old:
expr: (up{job="statporter"} == 1) and on() absent(container_cpu_percent{name="demo_container"})

# New:
expr: (up{job="statporter"} == 1) and on() absent(container_cpu_percent{namespace="homelab",container="demo_container"})
```

> `on()` is required. The reasoning is documented in `CLAUDE.md` under the Playground Feature section. The namespace is `homelab` (or `default` if statporter uses the default namespace). Use underscores in the label value (`demo_container`, not `demo-container`) - normalizeName convention preserved in the Go rewrite.

**`DemoContainerHighCPU`** (breaking change):

```yaml
# Old:
expr: container_cpu_percent{name="demo_container"} > 80
annotations:
  description: "Container {{ $labels.name }} CPU has been above 80% for 10 seconds."

# New:
expr: container_cpu_percent{namespace="homelab",container="demo_container"} > 80
annotations:
  description: "{{ $labels.namespace }}/{{ $labels.pod }}/{{ $labels.container }} CPU has been above 80% for 10 seconds."
```

**`ContainerHighMemory`** (description annotation only - expression is not label-filtered):

```yaml
# Old description:
description: "Container {{ $labels.name }} memory usage is above 80% for 5 minutes."

# New description:
description: "{{ $labels.namespace }}/{{ $labels.pod }}/{{ $labels.container }} memory usage is above 80% for 5 minutes."
```

**`ContainerHighCPU`** (description annotation only):

```yaml
# Old description:
description: "Container {{ $labels.name }} CPU usage has been above 90% for 5 minutes."

# New description:
description: "{{ $labels.namespace }}/{{ $labels.pod }}/{{ $labels.container }} CPU usage has been above 90% for 5 minutes."
```

**`ContainerDown`** (no change needed) - this alert fires on `up{job=...}` which is unchanged.

---

## Part 11 - CI/CD Updates

### `docker-build-statporter.yml`

The current workflow builds the Python statporter from `weather-app/docker-final/statporter/`. Once the Go image is live, this workflow is retired in favor of a separate workflow in the `statporter` repo.

In the `statporter` repo, add `.github/workflows/docker-build.yml`:

```yaml
name: Build and push statporter

on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Log in to DockerHub
        uses: docker/login-action@v3
        with:
          username: ${{ vars.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: burningstar4/statporter:latest
```

In `homelab-infra`, `docker-build-statporter.yml` is deleted (or archived as a comment) once the Go image is confirmed live.

### `unit-tests.yml`

Add a Go test job alongside the existing Python unit tests:

```yaml
test-statporter-go:
  runs-on: ubuntu-latest
  defaults:
    run:
      working-directory: ../statporter # only works if statporter is checked out as a sibling
  steps:
    - uses: actions/checkout@v4
      with:
        repository: Gcedwards91/statporter
        path: statporter
    - uses: actions/setup-go@v5
      with:
        go-version: "1.26"
    - run: go test ./...
      working-directory: statporter
```

> Alternatively, Go tests live in the `statporter` repo's own CI workflow. If the statporter repo has its own test job, this step can be omitted from `homelab-infra` CI.

### `integration-tests.yml`

No changes needed immediately. The Docker Compose integration tests continue to run unchanged against the Compose stack. The K8s smoke tests are a separate workflow (`k8s-smoke-tests.yml`, `workflow_dispatch` only) in `homelab-k8`.

---

## Migration Path (Compose -> K8s)

Run the Compose stack and K8s stack in parallel during cutover. They can run on the same host as long as port 80 is not bound by both at the same time (the Compose stack's nginx and the k3s nginx-ingress both want `:80`).

**Step 1 - Bootstrap the cluster (no traffic yet)**

- Run k3s.yml and bootstrap.yml ansible playbooks
- Verify: `kubectl get nodes` shows Ready, `kubectl get pods -n ingress-nginx` shows controller Running

**Step 2 - Apply statporter manifests**

- `kubectl apply -f statporter/deploy/`
- Verify: statporter pod Running, `/metrics` returns Prometheus text

**Step 3 - Create all Secrets**

- `kubectl create secret generic weather-app-secrets ...`
- `kubectl create secret generic grafana-secrets ...`
- `kubectl create secret generic weather-app-owm-key ...`

**Step 4 - Apply all homelab-k8 manifests**

- `kubectl apply -k homelab-k8/k8s/`
- Verify: all pods Running or Healthy, Prometheus targets green, Grafana loads

**Step 5 - Smoke test the K8s stack (no public traffic yet)**

- Port-forward nginx-ingress: `kubectl port-forward -n ingress-nginx svc/ingress-nginx-controller 8080:80`
- Verify Flask pages, Grafana sub-path, Prometheus sub-path, playground toggle

**Step 6 - Cutover**

- Stop Compose stack: `docker compose down` (Compose nginx releases port 80)
- k3s nginx-ingress takes over port 80

**Step 7 - Post-cutover verification**

- All Prometheus scrape targets green
- Playground toggle starts and stops demo-container pod
- DemoContainerDown alert fires within 2 collection rounds of stopping demo-container
- Loki receiving logs from all pods (Grafana all-logs dashboard)
- Traces appearing in Tempo for weather-app and statporter

---

## Testing Checklist

### Cluster bootstrap

- [ ] `kubectl get nodes` shows dreadnought in `Ready` state
- [ ] `kubectl get pods -n ingress-nginx` shows controller pod `Running`
- [ ] `kubectl top pods -n homelab` returns data (confirms metrics-server is active)
- [ ] No Traefik pods present: `kubectl get pods -n kube-system | grep traefik` returns empty

### statporter

- [ ] `kubectl get pods -n default` shows statporter `Running`
- [ ] `kubectl port-forward svc/statporter 9800:9800 -n default` then `curl localhost:9800/metrics` returns all 7 metric names with `pod=`, `namespace=`, `container=` labels
- [ ] Stop demo-container pod: `kubectl scale deployment demo-container --replicas=0 -n homelab` - within 20 seconds `absent(container_cpu_percent{container="demo_container"})` fires in Prometheus

### weather-app playground

- [ ] Playground login works (passphrase via admin endpoint, login via UI)
- [ ] Toggle ON: `kubectl get pods -n homelab | grep demo-container` shows pod Running
- [ ] Toggle OFF: demo-container pod terminates; `kubectl get deployment demo-container -n homelab -o jsonpath='{.spec.replicas}'` returns 0
- [ ] Stress endpoint works when demo-container is running
- [ ] weather-app cannot scale any deployment other than demo-container (verify with `kubectl auth can-i patch deployments/scale --subresource=scale -n homelab --as=system:serviceaccount:homelab:weather-app`)

### Observability stack

- [ ] All Prometheus scrape targets green: `http://dreadnought/prometheus/targets`
- [ ] No scrape errors in Prometheus logs
- [ ] Grafana loads at `http://dreadnought/grafana/` with all provisioned dashboards visible
- [ ] Loki receiving logs: Grafana all-logs dashboard shows log lines from all pods
- [ ] `container=` label in Loki matches the pod container names (not blank)
- [ ] Tempo traces appear for weather-app and statporter in unified observability dashboard
- [ ] DemoContainerDown alert fires after stopping demo-container pod
- [ ] DemoContainerDown alert resolves after restarting demo-container pod
- [ ] DemoContainerHighCPU alert fires during playground CPU stress

### Ingress

- [ ] `/` routes to Flask app, Flask pages load
- [ ] `/grafana/` routes to Grafana (no trailing-slash redirect loop)
- [ ] `/prometheus/` routes to Prometheus UI
- [ ] `curl http://dreadnought/metrics` returns 403
- [ ] `curl http://dreadnought/api/playground/status` returns 403
- [ ] Security headers present: `curl -I http://dreadnought/` shows `X-Frame-Options`, `Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy`

### Alert expressions

- [ ] `DemoContainerDown` fires when demo-container is stopped and statporter is healthy
- [ ] `DemoContainerHighCPU` fires during playground stress test
- [ ] `ContainerDown` fires when a monitored service pod is deleted
- [ ] No `name=` label references remain in any alert expression (`grep -r 'name=' weather-app/docker-final/prometheus/rules/`)

---

## What This Does Not Cover

- **AWS EKS deployment** - Terraform-managed, deferred. EKS adds ALB Ingress Controller, ACM for TLS, Route53, Secrets Manager replacing K8s Secrets, IAM roles for service accounts.
- **TLS / HTTPS** - deferred to EKS/ACM. `SESSION_COOKIE_SECURE = True` must also be set at that time.
- **Prometheus Operator / ServiceMonitor** - static scrape configs are used throughout. If the prometheus-operator is added, replace static configs with ServiceMonitor resources.
- **Horizontal Pod Autoscaling** - `replicas: 1` for all services. Statporter must stay at 1 replica (multiple replicas would duplicate metrics). HPA is not applicable to most services in this stack.
- **Grafana dashboard URL in `about_me.html`** - the `/d/homelab-observability/homelab-observability` path is unchanged. The hostname changes from `localhost` to `dreadnought` (or whatever the cluster host is). Update the hyperlink when cutover is complete.
- **RBAC for Prometheus K8s service discovery** - the `prometheus/rbac.yaml` scaffold is included in the directory layout. The current prometheus.yml uses static scrape targets. If `kubernetes_sd_configs` is added in a future iteration, the ClusterRole is needed then.
- **Multi-node k3s** - single-node cluster. Adding worker nodes requires updating the k3s ansible playbook with a join-token step and the Promtail DaemonSet will automatically schedule on new nodes.
- **Grafana Alloy** - not in scope. Alloy is the successor to Promtail. Migration from Promtail DaemonSet to Alloy is a separate future step.
- **Tempo named volume** - trace data remains ephemeral on K8s (emptyDir), consistent with the Compose stack. Add a PVC if trace retention across pod restarts becomes a requirement.
