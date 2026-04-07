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