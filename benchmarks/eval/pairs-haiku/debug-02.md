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
**Current Framing:**
I was pointing at the Envoy sidecar OOMKilled events and thinking "proxy crashes → connection fails." But let me step back.

**Applying Lenses:**

### The Zoom In Lens (What exactly is the error?)
- App is trying to reach: **10.0.1.5:5432**
- Actual database is at: **10.0.2.50:5432**
- These are different IPs
- Error: `ECONNREFUSED` = "I tried to connect and nothing was listening"

### The Simplicity Lens
What if the real problem is that **the app is configured with the wrong IP address?**

The Envoy sidecar is set up to proxy requests on localhost → 10.0.2.50. The app should be connecting to `localhost:5432` or `127.0.0.1:5432`, not to `10.0.1.5:5432`.

**10.0.1.5 ≠ 10.0.2.50** (where the DB actually is)
**10.0.1.5 ≠ localhost** (where the Envoy proxy is listening)

### The Zoom Out Lens
There are two separate things in the pod:
1. The main app container (trying to reach 10.0.1.5)
2. An Envoy sidecar proxy (listening on localhost:5432, forwarding to the real DB at 10.0.2.50)

If the sidecar pattern is intentional (and the config clearly shows it is), then `DB_HOST: 10.0.1.5` is **misconfigured**. It should be `DB_HOST: localhost` or `127.0.0.1`.

### The Constraint Lens
What if `10.0.1.5` *used to work* but something changed? Or it's resolving to a different backend now? But even so — the presence of the Envoy sidecar suggests you *don't want* direct connections; you want them proxied.

---

## My Reframed Diagnosis

The root cause is actually **two issues converging**:

1. **Primary: App has wrong DB_HOST** — It's configured to connect directly to `10.0.1.5:5432` instead of using the Envoy sidecar proxy at `localhost:5432`. When `10.0.1.5` is unreachable (or resolves to an overloaded replica, or drops packets intermittently), the app fails.

2. **Secondary: Envoy sidecar is OOMKilled** — The 128Mi memory limit is too tight, and the sidecar is dying every 20-30 minutes. Even if the app were properly configured to use it, it wouldn't be available during those failure windows. When the sidecar goes down, Kubernetes restarts it, connectivity recovers.

The pattern (stable 20-30min → failures 2-3min → recovery) matches Envoy hitting OOM limits repeatedly.

**The fix:**
1. Change `DB_HOST` from `10.0.1.5` to `localhost` (use the sidecar proxy)
2. Increase Envoy memory limit from 128Mi to 256Mi or 512Mi (investigate memory leak if it persists)

Would you like me to check what `10.0.1.5` actually is in your cluster (it might be a service, a load balancer, or a misconfigured replica endpoint)?

## Response B
**Root cause: The Envoy sidecar is being OOMKilled, crashing the database proxy between your app and Postgres.**

Here's what's happening:

1. **The smoking gun**: Your Kubernetes events show the `envoy-sidecar` container being OOMKilled repeatedly (3m, 25m, 52m ago)
   - Memory limit: **128Mi** (extremely tight for a proxy handling database traffic)
   - When Envoy crashes, port 5432 inside the pod becomes unavailable

2. **The burst pattern explains itself**:
   - Envoy runs fine for 20-30 minutes, accumulating connections/buffers
   - Memory usage grows until it hits 128Mi
   - OOMKilled → port 5432 is dead → all connection attempts get ECONNREFUSED
   - Kubernetes restarts the pod after 2-3 minutes
   - Envoy comes up fresh with low memory → cycle repeats

3. **Why the DBA saw nothing**:
   - The actual PostgreSQL database (10.0.2.50) is healthy
   - The problem is the **proxy** (Envoy) between your app and the database, not the database itself
   - Your app config is pointed at `10.0.1.5:5432` (the sidecar) not the real DB IP

4. **The architecture issue**:
   - App connects to `10.0.1.5:5432` (localhost/sidecar)
   - Envoy intercepts and proxies to the real DB at `10.0.2.50:5432`
   - Envoy is starving for resources with a 128Mi limit under your connection load

**Fix (in priority order):**

1. **Immediate**: Increase Envoy sidecar memory limit
   ```yaml
   - name: envoy-sidecar
     resources:
       limits:
         memory: "512Mi"  # or at least 256Mi
         cpu: "100m"
   ```

2. **Monitor**: Add alerts on Envoy container restarts and memory usage

3. **Investigate**: Check if your app is leaking connections or creating excessive buffers in the proxy. A production proxy typically shouldn't need tuning this aggressive unless there's a leak.

4. **Verify**: After the fix, watch for 48+ hours to confirm the burst pattern stops (you should see 0 OOMKilled events).

The irony: DBA was right to check the database, and it *is* healthy. But this is a **proxy layer issue**, not a database issue. The platform team should own the Envoy config/sizing.

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
