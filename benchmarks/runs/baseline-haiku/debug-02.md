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