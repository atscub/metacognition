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