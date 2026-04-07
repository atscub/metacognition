## Root Cause: Node 10.0.5.21 is unhealthy, surfaced every 5 minutes by DNS TTL expiry

Let me separate signal from noise first, then explain what the logs actually show.

---

### Red herrings (not the cause)

- **v3.14.2 deploy (Apr 5)** — failures have been happening for 2 weeks; this predates it by ~13 days. None of those changes touch connection handling anyway.
- **npm audit findings** — accepted risk, no exploit path, zero relation to Redis connectivity.
- **Node.js 18→20 discussion** — no decision made, nothing changed.
- **Log level change (Apr 6 09:15)** — this just made the existing failures *visible*. It revealed the problem, didn't cause it.

---

### The actual smoking gun: two correlated facts

**Fact 1:** Failures started ~2 weeks ago = same day as the subnet migration (2026-03-23).

**Fact 2:** DNS TTL is `300` seconds (5 minutes). Failures occur roughly every 5 minutes.

---

### What the logs are telling you

```
[09:22:14] Connected to 10.0.5.22:6379          ← healthy node, works fine
...
[09:27:08] Connection reset by peer (10.0.5.21)  ← 10.0.5.21 actively closes the connection
[09:27:08] Reconnecting → resolved → 10.0.5.21  ← DNS TTL expired, re-resolved, got same bad node
[09:27:09] ETIMEDOUT connecting to 10.0.5.21    ← now completely unreachable
[09:27:14] Retry 1 → resolved → 10.0.5.21       ← still pinned to bad node (DNS cache still warm)
[09:27:15] ETIMEDOUT
[09:27:20] Retry 2 → resolved → 10.0.5.20       ← finally gets healthy node
[09:27:20] Connected to 10.0.5.20:6379          ← recovers
```

The sequence on 10.0.5.21 is: "connection reset" (node is up, actively closing) → "ETIMEDOUT" (node goes dark). This is consistent with a node that's in a bad state — possibly in the middle of a Sentinel failover loop, or misconfigured after the subnet migration so it intermittently accepts then drops connections.

The cycle: every 5 minutes (one DNS TTL), clients re-resolve `redis-cluster.internal`. Round-robin DNS occasionally routes them to 10.0.5.21. 10.0.5.21 fails. Client retries until it gets 10.0.5.20 or 10.0.5.22. Recovery takes 10-15 seconds. This matches exactly.

---

### Diagnosis steps

Run these to confirm:

```bash
# 1. Is 10.0.5.21 actually responding?
redis-cli -h 10.0.5.21 -p 6379 PING

# 2. What does Sentinel think about this node?
redis-cli -h 10.0.5.21 -p 26379 SENTINEL masters
redis-cli -h 10.0.5.20 -p 26379 SENTINEL replicas mymaster

# 3. Check for repeated failover events on 10.0.5.21 (sign of a flapping node)
redis-cli -h 10.0.5.21 -p 6379 INFO replication
redis-cli -h 10.0.5.21 -p 6379 DEBUG SLEEP 0  # just to test responsiveness

# 4. Check firewall/security group rules left over from migration
# Look for rules still referencing old 10.0.1.0/24 subnet that may affect 10.0.5.21
```

The migration is the likely origin of 10.0.5.21's problem — a firewall rule that wasn't updated, a misconfigured bind address, or a Sentinel configuration still referencing old IPs causing 10.0.5.21 to be repeatedly demoted/promoted.

---

### Fix

**Immediate (stop the bleeding):**
Remove 10.0.5.21 from DNS rotation until you've fixed the underlying node issue:

```
redis-cluster.internal.  300  IN  A  10.0.5.20
redis-cluster.internal.  300  IN  A  10.0.5.22
```

**Proper fix:**
1. Audit 10.0.5.21 — check `redis.conf` bind addresses, Sentinel config files (`sentinel.conf`) for any remaining references to the old `10.0.1.x` subnet, and any firewall rules that weren't updated during migration.
2. Once fixed and stable, add it back to DNS.

**Structural fix (prevents this class of problem in future):**
Your client is connecting directly to Redis nodes via round-robin DNS. It should be connecting via Sentinel, which knows the current master and handles failover transparently. Configure your Redis client to use Sentinel mode:

```js
// Instead of connecting to redis-cluster.internal directly,
// connect to Sentinels and let them tell you the master
const client = new Redis({
  sentinels: [
    { host: '10.0.5.20', port: 26379 },
    { host: '10.0.5.21', port: 26379 },
    { host: '10.0.5.22', port: 26379 },
  ],
  name: 'mymaster',
});
```

This way, if a node fails, the client asks Sentinel for the current master instead of blindly retrying a known-bad IP.