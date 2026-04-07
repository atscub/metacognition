## Reframing the Problem

### Step 1: My Current (Lazy) Framing

> "This is a network/database connectivity problem. The DB might be having issues the DBA isn't seeing, or there's something wrong between the app and the database."

Mental model: app → network → database. Something in that chain is flaky.

---

### Step 2: Reframing Lenses

#### Zoom In Lens — What exactly is `10.0.1.5`?

The app connects to `DB_HOST=10.0.1.5:5432`. But the PostgreSQL cluster dashboard shows its IP as `10.0.2.50:5432`. **These are different IPs.**

The pod spec has an `envoy-sidecar` container that listens on `0.0.0.0:5432` *inside the pod* and proxies to `10.0.2.50:5432`. So `10.0.1.5` is the pod's own IP — the app is talking to the envoy sidecar, not directly to PostgreSQL.

The real connection chain is: **app → envoy sidecar (10.0.1.5:5432) → PostgreSQL (10.0.2.50:5432)**

#### Zoom Out Lens — What else is happening in the system?

Kubernetes events:
```
3m   OOMKilled  envoy-sidecar   Container envoy-sidecar exceeded memory limit
25m  OOMKilled  envoy-sidecar   Container envoy-sidecar exceeded memory limit
52m  OOMKilled  envoy-sidecar   Container envoy-sidecar exceeded memory limit
```

Every ~25 minutes. Incidents last 2–3 minutes. Incidents repeat every 20–30 minutes. **The timing is not a coincidence.**

#### Inversion Lens — What would guarantee ECONNREFUSED on `10.0.1.5:5432`?

If nothing is listening on that port. That happens when the envoy sidecar crashes and is restarting. Kubernetes restarts crashed containers, but there's a gap — the restart backoff window — where port 5432 inside the pod is dead.

#### Adversarial Lens — Why did this fool everyone?

- The DBA checked `10.0.2.50` (real PostgreSQL) — which is fine.
- The error message says "connection refused" which *sounds* like a network or DB problem.
- The `DB_HOST` env var is named `DB_HOST`, implying it points to a database — not a local proxy.
- Nobody looked at the Kubernetes events with the OOMKill pattern next to the error timestamps.

---

### Step 3: Convergence

All three lenses point to the same thing. The simplest framing that fits all evidence:

---

## Root Cause

**The envoy sidecar is being OOMKilled every ~25 minutes due to its 128Mi memory limit being too low. Each crash creates a 2–3 minute window where nothing is listening on port 5432 inside the pod, causing ECONNREFUSED for every connection attempt. PostgreSQL itself is untouched — the DBA and network team are both looking at the wrong layer.**

---

## Evidence Trail

| Clue | What it means |
|---|---|
| `ECONNREFUSED 10.0.1.5:5432` | Connecting to the pod's own IP, not the DB |
| `envoy-sidecar` listens on `:5432`, proxies to `10.0.2.50:5432` | The app's "database" is actually the sidecar |
| OOMKilled events at 3m, 25m, 52m ago | ~25-minute cycle matches incident frequency exactly |
| DBA reports DB healthy | Correct — PostgreSQL at `10.0.2.50` is fine throughout |
| 2–3 minute recovery window | Kubernetes restart + Envoy boot time |

---

## Fix

**Immediate**: Raise the envoy sidecar memory limit. 128Mi is undersized for a production proxy handling DB traffic — start with 256Mi and watch actual usage.

**Investigate**: Why is envoy using more than 128Mi? Likely causes:
- Connection pool of 20 connections × concurrent pods × traffic burst creating too many upstream connections tracked in memory
- Envoy stats/telemetry accumulation without periodic reset
- A memory leak in this specific Envoy version (v1.29.1 — check release notes)

**Monitor**: Add an alert on envoy sidecar memory usage and on container restart count, not just on DB error rate.

**Consider**: If envoy is only doing simple TCP proxying to a static IP, ask whether you need it at all. The `STRICT_DNS` cluster type with a hardcoded IP is doing no real load balancing — a direct DB connection may be simpler and more reliable here.