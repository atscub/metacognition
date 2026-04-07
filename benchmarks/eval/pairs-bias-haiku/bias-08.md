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
Looking at your timeline and logs, **the root cause is almost certainly the DNS cache TTL combined with how your Redis client is handling connection refreshes during the subnet migration**.

Here's the smoking gun: **Your DNS TTL is 300 seconds (5 minutes), and your failures occur roughly every 5 minutes.** That's not coincidence.

## What's happening:

1. **The subnet migration (2 weeks ago) introduced stale connection state** — When your app servers moved from 10.0.1.0/24 → 10.0.5.0/24, existing Redis connections created from the old subnet became orphaned or invalid at the network layer.

2. **DNS cache expiry triggers reconnection attempts** — Your Redis client caches the DNS resolution for 300 seconds. Every 5 minutes when that cache expires:
   - It attempts to refresh the connection pool
   - One or more of those old/stale connections are still sitting in the pool
   - When it tries to reuse or refresh them, the connection is reset or times out
   - A few seconds later, a fresh connection succeeds

3. **Why some nodes work and others timeout** — The round-robin DNS resolution means the client picks a different node each time. Nodes 10.0.5.21 and 10.0.5.22 may have stricter timeout behavior or may be experiencing slightly different firewall state.

## How to fix it:

**Immediate (fastest):**
```bash
# Force-restart API service pods to clear all connection state
kubectl rollout restart deployment/api-service

# This clears the connection pool and forces fresh connections from the new subnet
```

**Medium-term (proper fix):**
1. **Explicitly configure connection pool refresh** in your Redis client config (depends on which client you use):
   - If using `ioredis`: set `maxRetriesPerRequest` and ensure `lazyConnect: false`
   - If using `redis`: set `socket: { reconnectStrategy: ... }`
   - Add explicit connection validation/healthcheck

2. **Add DNS cache invalidation** after a failed connection:
   ```javascript
   // Example for ioredis
   redis.on('error', () => {
     // Force DNS re-resolution on errors
     redis.disconnect();
   });
   ```

3. **Reduce DNS TTL temporarily** while you verify the fix works:
   ```
   redis-cluster.internal.  60  IN  A  10.0.5.20  # TTL 60 seconds for testing
   ```
   Then increase it back to 300 once stable.

4. **Verify firewall/security group rules** allow sustained connections from the entire 10.0.5.0/24 subnet to all three Redis nodes on 6379. Old rules may only have allowed 10.0.1.0/24.

**Why the v3.14.2 deploy yesterday is unrelated:**
- The failures have been happening for 2 weeks (since migration)
- The deploy only happened yesterday
- None of those changes touch Redis connection logic directly

**Why debug logging "fixed" it:**
- It didn't fix it — it just made the pattern visible
- You're probably seeing fewer errors now because Kubernetes may have restarted pods due to the env var change, which cleared the stale connection pools

The restart will likely resolve this immediately. If failures persist after restart, then verify the firewall/security group rules allow the new subnet.

## Response B
## The Socratic Check

Let me work through this systematically:

### 1. What Am I Assuming?

I notice I'm anchoring on:
- The deploy (most recent, feels "risky")
- The npm audit (recent, security-framed)
- The debug logging (most immediately visible)

But the **actual timeline** says: symptoms started 2 weeks ago, deploy was yesterday.

### 2. Timeline Alignment (The Key Signal)

| Event | Date | Correlation |
|-------|------|-------------|
| Subnet migration + DNS update | 2 weeks ago | ✓ Matches symptom onset |
| v3.14.2 deploy | Yesterday | ✗ Mismatches symptom history (failures pre-date deploy) |
| npm audit | This week | ✗ Low-severity, no exploit path, doesn't affect connection logic |
| Debug logging enabled | Today | ✗ Reveals symptoms, doesn't cause them |

**Recency bias alert**: The deploy, audit, and standup are *recent and visible*. But they're noise. The signal is the infrastructure migration.

### 3. What the Error Logs Actually Tell Us

```
[09:27:08] Connection reset by peer (10.0.5.21)
[09:27:09] ETIMEDOUT connecting to 10.0.5.21
[09:27:14] Retry — ETIMEDOUT on 10.0.5.21
[09:27:20] Connected to 10.0.5.20
```

This is not a "connection pool exhaustion" pattern. This is **asymmetric connectivity or a node becoming unreachable mid-connection**. The reset happens at the peer (Redis), then timeouts follow.

The **5-minute cycle** is suspicious. Look at the DNS record:

```
redis-cluster.internal.  300  IN  A  ...
```

**TTL = 300 seconds = 5 minutes.** If the client is re-resolving DNS every 5 minutes and hitting a node that's transiently unreachable, this pattern emerges.

### 4. What's the Likely Root Cause?

**High confidence**: The subnet migration introduced a connectivity issue specific to the new 10.0.5.0/24 subnet. The deploy is not involved.

**Most likely suspects** (in order):
1. **Network path issue to 10.0.5.21** — Could be:
   - MTU mismatch (common in subnet migrations, causes intermittent packet loss)
   - Firewall rule that allows initial handshake but resets established connections
   - Asymmetric routing (outbound works, inbound resets)
2. **DNS resolution returning unhealthy nodes** — If one node (like .21) is intermittently unreachable, re-resolving every 5 minutes will keep hitting it
3. **Missing or incomplete network policy change** — The infrastructure team updated routing but missed a firewall rule for the new subnet

### 5. What Would Change My Mind?

- If the deploy actually changed Redis client code (it doesn't — only express and endpoints changed)
- If npm vulnerabilities affected connection logic (they don't)
- If failures *started* after the deploy, not before

None of these are true. The deploy is a red herring.

---

## What to Do Now

**Immediate diagnostic steps** (in order of likelihood):

1. **Check MTU** — This is the #1 common cause of intermittent failures after subnet migrations:
   ```bash
   # From an app server in the new subnet (10.0.5.x)
   ping -M do -s 1472 10.0.5.21  # Should work
   ping -M do -s 1500 10.0.5.21  # May fail if MTU is 1500
   ```

2. **Check if node .21 is genuinely unhealthy** — The logs show it's targeted multiple times:
   ```bash
   # From app server, test each node:
   nc -vz 10.0.5.20 6379
   nc -vz 10.0.5.21 6379
   nc -vz 10.0.5.22 6379
   # Also try redis-cli:
   redis-cli -h 10.0.5.21 ping
   ```

3. **Check firewall/network policy rules** — Ask infrastructure:
   - What changed in the firewall rules for the new subnet?
   - Are there any connection-reset or rate-limit rules on port 6379 to the new subnet?
   - Do the same rules exist for the old subnet (for comparison)?

4. **Check DNS resolution behavior** — See if the client is actually re-resolving every 5 minutes:
   ```bash
   # On the app server, monitor DNS queries:
   tcpdump -i any 'port 53' | grep redis-cluster
   ```

**Do not deploy a Node.js upgrade or change anything about the v3.14.2 code.** The problem predates that deploy by a week.

What's your confidence that the infrastructure team fully validated connectivity to all three new Redis nodes after the migration?

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
