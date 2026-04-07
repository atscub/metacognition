## Root Cause: Envoy Sidecar OOMKill Crash Loop

The database is fine. The DBA is right, but so is the platform team — it's not a network issue per se, it's a **proxy crash loop**.

### The smoking gun: cross-reference three facts

**1. IP mismatch reveals the architecture**

| Config location | Address |
|---|---|
| `DB_HOST` env var (what the app connects to) | `10.0.1.5:5432` |
| Actual PostgreSQL cluster | `10.0.2.50:5432` |
| Envoy sidecar listener | `0.0.0.0:5432` (in the same pod) |

`10.0.1.5` is the pod's own IP. The app isn't connecting to the database directly — it's connecting to the Envoy sidecar running in the same pod, which then proxies to `10.0.2.50:5432`.

**2. Kubernetes events show the sidecar is dying repeatedly**

```
3m   OOMKilled  envoy-sidecar  Container exceeded memory limit
25m  OOMKilled  envoy-sidecar  Container exceeded memory limit
52m  OOMKilled  envoy-sidecar  Container exceeded memory limit
```

Cadence: ~22–27 minutes between kills.

**3. The burst pattern matches exactly**

- Errors every 20–30 minutes → matches OOMKill frequency
- Recovery after 2–3 minutes → matches Kubernetes container restart + readiness time
- DB dashboard shows no issues → traffic never reaches the database during an outage

### What happens during an incident

```
Envoy sidecar hits 128Mi limit
         ↓
Kubernetes OOMKills the container
         ↓
Port 5432 has no listener in the pod
         ↓
App tries to connect to 10.0.1.5:5432 → ECONNREFUSED (×48)
         ↓
Kubernetes restarts the sidecar (~2-3 min)
         ↓
Envoy is back, connections restored
```

The database never sees a blip because no traffic is reaching it.

### Fix

**Immediate:** Increase the Envoy sidecar memory limit — 128Mi is very tight for a proxy handling production database traffic.

```yaml
- name: envoy-sidecar
  resources:
    limits:
      memory: "256Mi"   # was 128Mi
    requests:
      memory: "128Mi"   # add a request too, for scheduler accuracy
```

**Then investigate why it's leaking/growing:** Envoy shouldn't be accumulating memory for a simple TCP proxy. Check:
- Whether connection tracking is accumulating stale entries (look at `envoy_cluster_upstream_cx_active` metrics)
- Whether the pool's `max: 20` connections × number of pod replicas is creating more upstream connections than expected
- Envoy admin endpoint (`/memory`, `/clusters`) for diagnostics before the next OOMKill

**Longer term:** Add a memory usage alert on the sidecar before it hits the limit, so you catch this proactively rather than via application errors.