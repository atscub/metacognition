## Current Framing
"Network/database issue — the app can't reach the DB because of network flakiness or routing"

## Alternative Framings via Reframing Lenses

### Zoom In Lens: What's Actually Happening?
**Critical observation**: The Envoy sidecar is being **OOMKilled every 20-50 minutes**. This isn't a side detail—look at the Kubernetes events:
- 3m ago: OOMKilled
- 25m ago: OOMKilled  
- 52m ago: OOMKilled

The **burst pattern matches exactly**: 20-30 minutes of success → sidecar hits memory limit and crashes → 2-3 minute restart window = connection failures → sidecar comes back up. Repeat.

### Inversion Lens: What Guarantees Failures?
What would guarantee ECONNREFUSED in bursts?
1. ✅ Sidecar dies → local proxy unavailable → connections refused
2. Connection pool exhaustion
3. DNS failure
4. Network partition

The sidecar being OOMKilled does #1.

### The Adversarial Lens: Address Mismatch
Secondary problem: **The app is configured to connect to `10.0.1.5:5432`, but:**
- The Envoy sidecar **listens on `0.0.0.0:5432`** (the pod's localhost)
- The Envoy sidecar **proxies to `10.0.2.50:5432`** (the actual database)
- The health check shows the database is at **`10.0.2.50:5432`**

**Why is the app connecting to `10.0.1.5`?** That's not the database, it's not localhost, and it's not the proxy. Either:
1. There's iptables/kube-proxy magic redirecting 10.0.1.5→localhost that breaks when the sidecar is down
2. The configuration is wrong and should be `localhost` or `127.0.0.1`
3. 10.0.1.5 is a ghost/stale address

---

## Root Cause

**Primary**: Envoy sidecar has a **memory leak**. It accumulates memory for 20-30 minutes, hits the 128Mi limit, gets OOMKilled, and takes 2-3 minutes to restart. During that restart window, all connections fail.

**Secondary**: App configuration points to the wrong database address (10.0.1.5 instead of localhost/127.0.0.1), which works only when the sidecar can intercept it via iptables. When the sidecar dies, the app loses connectivity.

---

## Next Steps

1. **Immediate** (stop the bleeding):
   - Increase Envoy sidecar memory limit from `128Mi` to `256Mi` or `512Mi` to buy time
   - This might extend the cycle to 40+ minutes, buying you breathing room

2. **Root cause** (fix the memory leak):
   - Profile the Envoy sidecar process during an incident to find what's consuming memory
   - Check Envoy logs for connection leak, buffer leak, or listener issues
   - Common culprits: unclosed connections, unbounded ring buffers, DNS cache growing without bounds

3. **Configuration fix**:
   - Change `DB_HOST` from `10.0.1.5` to `localhost` or `127.0.0.1:5432`
   - This ensures the app explicitly uses the sidecar proxy, and makes your architecture clearer

Do you have access to Envoy sidecar logs or the ability to profile its memory during an incident? That's where the leak is.