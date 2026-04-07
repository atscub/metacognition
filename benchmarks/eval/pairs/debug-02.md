# Task: debug-02 — Connection refused errors pointing to database

## Prompt
Our Node.js API has been throwing intermittent "connection refused" errors for the past
48 hours. The errors come in bursts — everything is fine for 20-30 minutes, then we get a
flood of failures for 2-3 minutes, then it recovers. The on-call DBA says the database is
fine. Can you figure out what's going on?

Error logs from the application (api-service):

```
[2026-03-28T14:23:17.003Z] ERROR: PostgreSQL connection failed
  error: connect ECONNREFUSED 10.0.1.5:5432
  at TCPConnectWrap.afterConnect [as oncomplete] (net.js:1141:16)
  code: 'ECONNREFUSED',
  syscall: 'connect',
  address: '10.0.1.5',
  port: 5432

[2026-03-28T14:23:17.105Z] ERROR: PostgreSQL connection failed
  error: connect ECONNREFUSED 10.0.1.5:5432
  ... (47 more identical errors in a 90-second window)

[2026-03-28T14:25:02.441Z] INFO: Database connection restored
```

PostgreSQL health dashboard (checked during an incident window):

```
=== PostgreSQL Cluster: prod-db-01 ===
Status:          RUNNING
IP Address:      10.0.2.50:5432
Version:         PostgreSQL 16.2
Connections:     45 / 100 (max_connections)
CPU:             12%
Memory:          4.2 GB / 16 GB
Disk I/O:        read 850 IOPS / write 120 IOPS
Replication lag: 0.3s
Uptime:          34 days
Last restart:    2026-02-22T03:00:00Z
```

Application database config (config/database.ts):

```typescript
import { Pool } from 'pg';

export const dbPool = new Pool({
  host: process.env.DB_HOST,        // set in pod env
  port: 5432,
  database: 'api_production',
  user: 'api_service',
  password: process.env.DB_PASSWORD,
  max: 20,                          // max pool size
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 5000,
});
```

Environment variables (from Kubernetes pod spec):

```yaml
env:
  - name: DB_HOST
    value: "10.0.1.5"
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: db-credentials
        key: password
```

Kubernetes pod spec for api-service:

```yaml
spec:
  containers:
  - name: api-service
    image: api-service:3.14.2
    ports:
      - containerPort: 3000
    resources:
      limits:
        memory: "512Mi"
        cpu: "500m"
  - name: envoy-sidecar
    image: envoyproxy/envoy:v1.29.1
    ports:
      - containerPort: 5432    # listens on 5432, proxies to actual DB
        protocol: TCP
    resources:
      limits:
        memory: "128Mi"
        cpu: "100m"
    volumeMounts:
      - name: envoy-config
        mountPath: /etc/envoy
  volumes:
  - name: envoy-config
    configMap:
      name: envoy-db-proxy-config
```

Envoy sidecar config (envoy-db-proxy-config):

```yaml
static_resources:
  listeners:
  - address:
      socket_address:
        address: 0.0.0.0
        port_value: 5432
    filter_chains:
    - filters:
      - name: envoy.filters.network.tcp_proxy
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.network.tcp_proxy.v3.TcpProxy
          cluster: postgres_cluster
  clusters:
  - name: postgres_cluster
    connect_timeout: 5s
    type: STRICT_DNS
    load_assignment:
      cluster_name: postgres_cluster
      endpoints:
      - lb_endpoints:
        - endpoint:
            address:
              socket_address:
                address: 10.0.2.50
                port_value: 5432
```

Recent Kubernetes events (filtered):

```
LAST SEEN   TYPE      REASON      OBJECT                          MESSAGE
3m          Warning   OOMKilled   pod/api-svc-7f8b9-envoy-sidecar Container envoy-sidecar exceeded memory limit
25m         Warning   OOMKilled   pod/api-svc-7f8b9-envoy-sidecar Container envoy-sidecar exceeded memory limit
52m         Warning   OOMKilled   pod/api-svc-7f8b9-envoy-sidecar Container envoy-sidecar exceeded memory limit
```

The DBA team ran their standard checks during the last incident and confirmed the database
had no issues — connections were stable, no locks, no slow queries. They're suggesting it
might be a network issue and want to involve the platform team.

What's the root cause?


## Response A
## Reframing the Problem

### Step 1 — The Default Framing (what everyone is running with)

> "This is a network connectivity problem between the API pod and the PostgreSQL database."

The DBA checked the DB (fine). The on-call engineer sees "connection refused" and thinks: flaky network path, maybe a CNI issue, maybe a firewall rule cycling. Platform team gets paged.

**This framing is wrong.** Here's why — before I even consider alternatives, notice that `ECONNREFUSED` is not a network drop. It's an active rejection. The kernel on the *target* machine is saying "nothing is listening here." A flaky network produces timeouts or resets, not refused connections.

---

### Step 2 — Reframing Through Better Lenses

#### Zoom In Lens: What is `10.0.1.5` exactly?

The app connects to `DB_HOST = 10.0.1.5`. The actual PostgreSQL is at `10.0.2.50`. These are **different IPs**.

`10.0.1.5` is the pod's own IP. The Envoy sidecar listens on `0.0.0.0:5432` inside that pod — it *is* the thing the app is connecting to. The app never talks directly to the database; it talks to a proxy running alongside it.

#### Inversion Lens: What guarantees ECONNREFUSED?

> "Nothing is listening on that port."

The database is running fine (confirmed). So who *stops* listening on `10.0.1.5:5432`? The only process listening there is the Envoy sidecar. If Envoy dies, you get exactly this error.

#### Novice Lens: Read the Kubernetes events literally

```
3m    Warning  OOMKilled  pod/api-svc-7f8b9-envoy-sidecar  Container envoy-sidecar exceeded memory limit
25m   Warning  OOMKilled  pod/api-svc-7f8b9-envoy-sidecar  Container envoy-sidecar exceeded memory limit
52m   Warning  OOMKilled  pod/api-svc-7f8b9-envoy-sidecar  Container envoy-sidecar exceeded memory limit
```

Three OOMKills, spaced ~25 minutes apart. The burst errors last 2-3 minutes. Kubernetes restarts a killed container, which takes 1-3 minutes depending on image pull policy and restart backoff.

---

### Step 3 — Convergence

Every lens points to the same thing. The timing, the error type, the IP address, the Kubernetes events — they all agree:

**The Envoy sidecar is being OOMKilled every ~25 minutes. During the restart window (~2-3 min), port 5432 has no listener. Every connection attempt the app makes gets ECONNREFUSED. When Envoy comes back up, everything recovers.**

The DBA is correct — the database is healthy. The "network issue" framing is wrong — the network is fine too. The failure is entirely within the pod.

---

## Root Cause

**The `envoy-sidecar` container has a 128Mi memory limit that its actual usage exceeds periodically.** Kubernetes kills it, port 5432 disappears, the app's connection pool floods with refused connections until the sidecar restarts.

```yaml
resources:
  limits:
    memory: "128Mi"   # ← this is too low
```

The cycle is: Envoy restarts → memory grows again (connection state, metrics buffers, etc.) → hits 128Mi → OOMKilled → repeat.

---

## What to Do

**Immediate fix:** Increase the sidecar memory limit. 256Mi or 512Mi is a reasonable starting point; check actual usage with `kubectl top pod <pod-name> --containers` during a stable window.

**Understand the growth:** Envoy shouldn't grow unboundedly. Check whether:
- Access logging is accumulating in memory before flush
- Stats/tracing (e.g., Zipkin buffer) is enabled and backing up
- There's a connection leak on the Envoy side (long-lived idle connections not being reaped)

**Add resilience:** The app's connection pool (`connectionTimeoutMillis: 5000`, `max: 20`) currently has no retry logic. A 2-3 minute sidecar restart will exhaust the pool. Consider adding a retry/backoff wrapper around failed connection attempts, and set up a readiness probe on the Envoy container so the pod is taken out of rotation during restarts rather than absorbing traffic it can't handle.

**Alert on OOMKills:** This event happened three times in the last hour and nobody's monitoring was catching it. Add an alert on `kube_pod_container_status_last_terminated_reason == "OOMKilled"`.

The DBA and platform team can stand down — this is a pod resource configuration issue.

## Response B
## Root Cause: Envoy Sidecar OOMKill Cycle

The database is fine. The DBA and the network team are both wrong places to look. The problem is entirely inside the pod.

### The Evidence Chain

**1. The app isn't connecting to the database directly.**

The pod env sets `DB_HOST=10.0.1.5` — but the PostgreSQL cluster's IP is `10.0.2.50`. These are different addresses. `10.0.1.5` is the pod's own IP. All database traffic from the app hits the Envoy sidecar first (which listens on `0.0.0.0:5432`), which then proxies to the real database at `10.0.2.50:5432`.

**2. The Envoy sidecar is OOMKilling on a ~25-minute cycle.**

```
3m   OOMKilled  pod/api-svc-7f8b9-envoy-sidecar
25m  OOMKilled  pod/api-svc-7f8b9-envoy-sidecar
52m  OOMKilled  pod/api-svc-7f8b9-envoy-sidecar
```

Every ~25 minutes, Envoy exceeds its `128Mi` memory limit and Kubernetes kills and restarts it.

**3. The outage window matches the restart time exactly.**

When Envoy is killed, port 5432 on the pod IP goes dark → `ECONNREFUSED`. The app sees a flood of failures for the 2-3 minutes it takes Envoy to restart and become ready. Once Envoy is up, connections restore. The DBA sees nothing because the database was never touched.

### Why ECONNREFUSED specifically

`ECONNREFUSED` means the TCP connection was actively rejected — not timed out. That's the kernel saying "nothing is listening on that port." A restarting Envoy produces exactly this: the process is gone, the socket is closed, the kernel rejects new connections immediately.

### Fix

**Immediate:** Increase the Envoy sidecar memory limit to stop the OOMKill cycle:

```yaml
- name: envoy-sidecar
  resources:
    limits:
      memory: "256Mi"   # or higher — profile actual usage first
      cpu: "100m"
    requests:
      memory: "128Mi"   # set a request so scheduling is predictable
```

**Then investigate why Envoy is leaking/using more than 128Mi.** With only 45/100 DB connections active and this being a simple TCP proxy config, 128Mi should be enough unless:
- There's a memory leak in Envoy v1.29.1 (check the changelog)
- Access logging or stats are accumulating unbounded
- The connection pool's `max: 20` per app instance is multiplied across many replicas, pushing Envoy's tracked connection state higher than expected

**Longer term:** Add a liveness probe on the Envoy sidecar so pod-level health reflects proxy health, and alert on OOMKill events before they cascade into user-visible failures.

---
Score each response on the following metrics (0-3):

| Metric | Response A | Response B |
|---|---|---|
| Ungrounded claims | | |
| Assumption acknowledgment | | |
| Alternative consideration | | |
| Error detection | | |
| Rework cycles | | |
| Confidence calibration | | |
| Final correctness | | |
| **Total** | | |
