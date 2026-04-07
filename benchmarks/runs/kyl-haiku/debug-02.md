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