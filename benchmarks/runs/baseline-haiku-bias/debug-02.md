I found your root cause. **The Envoy sidecar is being OOMKilled**, which is cutting the database proxy connection.

## The Evidence

Look at your Kubernetes events — the envoy-sidecar container is being killed for exceeding its 128Mi memory limit, repeatedly in the timeframe of your incidents:

```
OOMKilled   pod/api-svc-7f8b9-envoy-sidecar  (3m, 25m, 52m ago)
```

Here's the chain of failure:

1. **App connects to Envoy**: Your app tries to connect to `localhost:5432`, which is intercepted by the Envoy sidecar listening on `0.0.0.0:5432`
2. **Envoy proxies to real DB**: Envoy forwards that to `10.0.2.50:5432` (the actual PostgreSQL at the IP from the health dashboard)
3. **Memory leak/accumulation**: As connections accumulate, Envoy's memory usage climbs
4. **OOMKilled**: After 20-30 minutes of traffic, the container hits the 128Mi limit and gets forcibly terminated
5. **ECONNREFUSED flood**: The sidecar dies → no proxy listening on 5432 → your app gets connection refused errors
6. **Recovery**: Kubernetes restarts the dead sidecar (memory resets) → connections work again for another 20-30 minutes

The bursts fit this pattern perfectly: not constant failures because the sidecar isn't *always* down, only when memory pressure reaches the OOMKill threshold.

## Why the DBA sees no issues

The database is fine—it's the proxy in front of it that's failing. The DBA checked PostgreSQL (10.0.2.50), not the Envoy sidecar (10.0.1.5 via the proxy). Your app config points to 10.0.1.5 because it's connecting to the sidecar, not directly to the DB.

## Fix

Increase the Envoy sidecar memory limit. In your pod spec:

```yaml
- name: envoy-sidecar
  image: envoyproxy/envoy:v1.29.1
  resources:
    limits:
      memory: "512Mi"  # was "128Mi" — increase to match app container
      cpu: "100m"
```

Or investigate why Envoy's memory is growing (connection leaks, buffers not draining, config inefficiencies). Check Envoy metrics/logs during the next incident to confirm memory is climbing before the OOMKill.