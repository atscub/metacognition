# Task: bias-08 — Redis cluster failures buried under recent noise

## Prompt
We've been dealing with intermittent connection failures to our Redis cluster for about
two weeks now. I need help figuring out the root cause. Here's everything that's happened:

Two weeks ago, our infrastructure team migrated the application servers from the old
10.0.1.0/24 subnet to a new 10.0.5.0/24 subnet as part of a datacenter consolidation.
During the migration, they also updated DNS to point our Redis cluster hostname
(redis-cluster.internal) to the new cluster IPs. The DNS zone file shows:

```
; Updated during subnet migration — 2026-03-23
redis-cluster.internal.  300  IN  A  10.0.5.20
redis-cluster.internal.  300  IN  A  10.0.5.21
redis-cluster.internal.  300  IN  A  10.0.5.22
```

The Redis cluster runs 3 nodes with Sentinel for failover. The cluster has been stable
for 18 months prior to this.

---

Okay, so now for the recent stuff. Yesterday afternoon (2026-04-05) we deployed version
3.14.2 of our main API service. The release notes for this deploy:

```
v3.14.2 Changelog:
- Updated express from 4.18.2 to 4.19.1
- Added request correlation IDs to all log entries
- Fixed a typo in the /health endpoint response ("healhty" → "healthy")
- Migrated 2 endpoints from callbacks to async/await
- Added new GET /api/v2/reports/quarterly endpoint
```

This morning (2026-04-06), our on-call engineer noticed the Redis errors in the logs and
started investigating. As a first step, he changed the logging level from WARN to DEBUG
to get more detail:

```bash
# Applied this morning at 09:15 UTC
kubectl set env deployment/api-service LOG_LEVEL=DEBUG
```

After enabling debug logging, we can now see the actual errors:

```
[2026-04-06T09:22:14Z] DEBUG redis-client: Attempting connection to redis-cluster.internal
[2026-04-06T09:22:14Z] DEBUG redis-client: Resolved redis-cluster.internal → 10.0.5.22
[2026-04-06T09:22:14Z] INFO  redis-client: Connected to 10.0.5.22:6379
[2026-04-06T09:22:14Z] DEBUG redis-client: AUTH OK, SELECT db=0
...
[2026-04-06T09:27:08Z] ERROR redis-client: Connection reset by peer (10.0.5.21:6379)
[2026-04-06T09:27:08Z] DEBUG redis-client: Reconnecting to redis-cluster.internal
[2026-04-06T09:27:08Z] DEBUG redis-client: Resolved redis-cluster.internal → 10.0.5.21
[2026-04-06T09:27:09Z] ERROR redis-client: ETIMEDOUT connecting to 10.0.5.21:6379
[2026-04-06T09:27:14Z] DEBUG redis-client: Retry 1 — resolved → 10.0.5.21
[2026-04-06T09:27:15Z] ERROR redis-client: ETIMEDOUT connecting to 10.0.5.21:6379
[2026-04-06T09:27:20Z] DEBUG redis-client: Retry 2 — resolved → 10.0.5.20
[2026-04-06T09:27:20Z] INFO  redis-client: Connected to 10.0.5.20:6379
```

Also, our security team ran `npm audit` this week and flagged 3 low-severity
vulnerabilities in transitive dependencies:

```
found 3 vulnerabilities (3 low)
  protobufjs  <7.2.5    — Prototype Pollution
  semver      <7.5.4    — ReDoS
  word-wrap   <1.2.4    — ReDoS
```

None of these are in our direct dependencies and the security team marked them as
"accept risk — no exploit path in our usage."

Finally, in our team standup this morning, there was a 15-minute discussion about whether
we should upgrade from Node.js 18 to Node.js 20 before the 18.x EOL in September. The
platform team is pushing for it but the product team is worried about regression testing
capacity. No decision was made.

The symptom: intermittent connection failures to Redis, happening roughly every 5 minutes,
for the last 2 weeks. The failures last about 10-15 seconds each time before recovering.
Users see brief "service unavailable" errors during these windows.

What's causing this and how do we fix it?


## Response A
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

## Response B
## Socratic Analysis Before Answering

**Running the bias checklist first.**

### Recency Bias Check

The problem statement presents information roughly in this order:
1. Subnet migration (2026-03-23) — 2 weeks ago
2. v3.14.2 deployment (2026-04-05) — yesterday
3. Debug logging change (2026-04-06 09:15) — this morning
4. Debug logs — this morning
5. npm audit findings — this week
6. Node.js upgrade discussion — this morning's standup

**The recency trap**: The deployment and debug logs dominate the bottom half of the message and are visually prominent. A pattern-matching response might anchor on the deployment as the cause because it's "the recent change." The npm vulnerabilities and Node.js discussion are even more recent in the message — they're bait.

**Applying the timeline test**: The symptom is described as happening *for the last two weeks*. The deployment was *yesterday*. Therefore the deployment **cannot be the root cause**. Neither can the npm audit or the Node.js discussion. These are red herrings introduced by recency.

---

### What Am I Assuming? (Explicit Assumption List)

1. "Two weeks" of failures accurately describes symptom onset
2. The subnet migration date (2026-03-23) is approximately two weeks before today (2026-04-07)
3. "Roughly every 5 minutes" is the failure cadence
4. Failures last 10-15 seconds before recovering
5. The Redis cluster was stable for 18 months before the migration

### What Changed Two Weeks Ago?

Two things changed simultaneously during the subnet migration:
1. App servers moved from `10.0.1.0/24` → `10.0.5.0/24`
2. DNS for `redis-cluster.internal` was updated to new IPs (10.0.5.20/21/22)

### Reading the Logs Carefully

```
09:22:14  Connected to 10.0.5.22:6379
09:27:08  Connection reset by peer (10.0.5.21:6379)   ← ~5 min later
09:27:08  Reconnecting → resolved to 10.0.5.21
09:27:09  ETIMEDOUT connecting to 10.0.5.21
09:27:14  Retry 1 → 10.0.5.21
09:27:15  ETIMEDOUT connecting to 10.0.5.21
09:27:20  Retry 2 → 10.0.5.20
09:27:20  Connected to 10.0.5.20:6379                  ← recovered
```

Two separate signals here:
1. The failure cadence is **~5 minutes**
2. Node **10.0.5.21 consistently fails** — both the initial reset and subsequent timeouts target this node

---

## Root Cause Analysis

### The 5-Minute Interval Is The Key

**The DNS TTL is 300 seconds = exactly 5 minutes.**

But the failure pattern doesn't look like a DNS problem — the client is already resolving to correct `10.0.5.x` addresses. What else is 5 minutes?

**Firewall idle connection timeout.** Many stateful firewalls and security groups default to a ~300-second idle connection timeout. When a TCP connection carries no traffic for 5 minutes, the firewall silently drops its state table entry — no `FIN`, no `RST`. The connection *appears* alive to both endpoints until one side tries to send data, at which point it gets a reset or timeout.

This matches every data point:
- **Onset**: The new `10.0.5.0/24` subnet has different network policy than the old `10.0.1.0/24` subnet. The old environment apparently didn't have this restriction (or Redis connections were busy enough to not go idle)
- **Cadence**: ~5 minutes = 300s firewall idle timeout
- **Recovery**: 10-15 seconds = reconnection + retry time
- **User impact**: Brief "service unavailable" windows = exactly what a dropped-but-not-yet-detected connection produces

### Why 10.0.5.21 Specifically?

This node deserves separate attention. The other nodes (.20, .22) recover normally after reconnection. Node .21 times out consistently. Possible explanations:

- A host-level firewall rule (`iptables`/`nftables`) blocking inbound connections on .21 specifically
- A routing issue — the new subnet's routes for .21 may be misconfigured
- The node itself is unhealthy (Redis process issue, memory pressure) but Sentinel hasn't evicted it because it's *intermittently* reachable

This is a secondary problem — the 5-minute cycle is the primary driver, but every time the client lands on .21 during reconnection, it wastes two retry cycles before finding a healthy node, extending the outage window.

---

## What Is NOT The Cause

| Candidate | Verdict | Reasoning |
|-----------|---------|-----------|
| v3.14.2 deployment | **Not the cause** | Symptoms predate it by 13 days |
| async/await migration in 3.14.2 | **Not the cause** | Same timeline mismatch |
| DEBUG logging change | **Not the cause** | Made the problem visible, didn't create it |
| npm audit vulnerabilities | **Not the cause** | Low-severity, no exploit path, and wrong timeline |
| Node.js 18 vs 20 discussion | **Not the cause** | No decision made, no change applied |

---

## Recommended Fixes

**Fix 1 — Immediate: Enable TCP keepalives on the Redis client** (highest confidence)

Configure the Redis client to send TCP keepalives with an interval shorter than the firewall timeout. The exact config depends on your Redis client library, but the goal is to ensure idle connections send a keepalive probe every 60–120 seconds so the firewall keeps its state entry alive.

For `ioredis` (Node.js):
```js
new Redis({
  keepAlive: 60000,  // 60s keepalive interval
  // ...
})
```

For `node-redis`:
```js
createClient({
  socket: {
    keepAlive: 60000,
  }
})
```

**Fix 2 — Immediate: Investigate 10.0.5.21**

```bash
# From an app server in the new subnet:
redis-cli -h 10.0.5.21 -p 6379 ping
redis-cli -h 10.0.5.21 -p 6379 info server

# Check if the node is reachable at all:
nc -zv 10.0.5.21 6379

# Check Sentinel's view of this node:
redis-cli -h redis-sentinel.internal -p 26379 sentinel slaves mymaster
```

If .21 is consistently unreachable, it should either be repaired or removed from the Sentinel configuration so the client stops attempting to connect to it during failover.

**Fix 3 — Confirm with the infrastructure team**

Ask them directly: *"What are the firewall/security group rules for idle TCP connections in the 10.0.5.0/24 subnet?"* and *"Were connection tracking timeouts changed during the migration?"* The 5-minute correlation is strong enough that this is almost certainly the answer, but verifying the actual firewall policy would confirm it.

---

## Confidence Levels

- **High**: The root cause is in the subnet migration, not the deployment — timeline is definitive
- **High**: 10.0.5.21 has an independent problem that compounds the outage duration
- **Medium-high**: Firewall idle timeout is the primary mechanism — the 300s match is compelling but needs infrastructure team confirmation
- **Medium**: TCP keepalives will fix it — depends on the actual firewall timeout value and whether the client library honors the socket option correctly

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
