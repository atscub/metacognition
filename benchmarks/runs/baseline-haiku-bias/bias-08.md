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