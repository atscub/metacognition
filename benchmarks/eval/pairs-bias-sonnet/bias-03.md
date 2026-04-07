# Task: bias-03 — Premature closure on obvious but wrong root cause

## Prompt
We're experiencing 504 Gateway Timeout errors on our Node.js API and need help
debugging. Here's the full incident timeline and details:

**Timeline:**
- Tuesday 2:00 PM: Deployed version 2.14.0 to production (changelog below)
- Tuesday 2:15 PM: First 504 errors appear in PagerDuty
- Tuesday 2:45 PM: Error rate climbs to 12% of all requests
- Wednesday: Ongoing, errors persist at ~10%

**Version 2.14.0 Changelog:**
1. Added new `/api/v2/reports/comprehensive` endpoint with a complex aggregation query
   that joins 6 tables. During load testing, this query averaged 8.2 seconds on our
   staging database (production DB is faster, estimated ~6 seconds).
2. Updated Node.js runtime from 18.17 to 18.19 (security patch).
3. Migrated nginx configuration to use the DevOps team's new standardized config
   template ("nginx-hardened-v2") for improved security posture. Changes include
   updated TLS settings, new rate limiting rules, and aligned timeout configurations
   with the security team's recommendations.
4. Added request logging middleware for audit compliance.

**Infrastructure:**
- Load balancer: AWS ALB (idle timeout: 60s)
- Reverse proxy: nginx (config managed by DevOps)
- Runtime: Node.js 18.19, Express 4.18
- Database: PostgreSQL 15 on RDS (db.r6g.xlarge)

**Current nginx configuration** (excerpted from nginx-hardened-v2 template):
```nginx
http {
    # Security-hardened timeout settings per SecOps review
    proxy_connect_timeout 10s;
    proxy_send_timeout    10s;
    proxy_read_timeout    5s;   # Reduced from default per security policy
    send_timeout          10s;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=100r/s;

    # ... TLS 1.3 settings, HSTS headers, etc.
}
```

**Observations:**
- The 504 errors affect ALL endpoints, not just the new `/reports/comprehensive`
  endpoint. Even simple health check endpoints (which return in <10ms) occasionally
  get 504s.
- Database connection pool metrics show no exhaustion (12/50 connections used at peak)
- Node.js event loop lag: 2ms average, 45ms peak (healthy)
- The new reports endpoint is called approximately 30 times per hour

**Query performance for the new endpoint:**
```sql
EXPLAIN ANALYZE -- comprehensive report query
-- Execution time: 7,847ms (staging), estimated ~5,500ms (production)
```

What is causing the 504 errors, and what should we do to fix it?


## Response A
## Socratic Analysis: 504 Gateway Timeout Debugging

Let me work through this carefully, running the bias checklist before committing to any explanation.

---

### Step 1: Lay out assumptions explicitly

Before diving in, here's what I'm treating as facts vs. inferences:

| Claim | Status |
|---|---|
| `proxy_read_timeout 5s` is in effect globally | **Observed** (in the nginx excerpt) |
| Reports query takes ~6-8 seconds | **Observed** (EXPLAIN ANALYZE) |
| 504s affect ALL endpoints including health checks | **Observed** (stated in problem) |
| DB pool is not exhausted | **Observed** (12/50 connections) |
| Event loop is healthy | **Observed** (2ms avg, 45ms peak) |
| Production query takes ~5.5s | **Estimated** — stated as "estimated" |

---

### Step 2: Identify the obvious hypothesis — then interrogate it

**Obvious hypothesis**: The new reports endpoint query (~6-8s) exceeds `proxy_read_timeout 5s`, so nginx returns 504 on every reports request.

This is clearly true. But the skill demands: **does this account for ALL observed symptoms?**

**It does not.**

The critical disconfirming observation: *"504 errors affect ALL endpoints, not just /reports/comprehensive. Even simple health check endpoints (which return in <10ms) occasionally get 504s."*

If the slow query were the only cause, you'd expect 504s concentrated on `/reports/comprehensive`, not a 10% error rate across all traffic including <10ms health checks. I need a second explanation, or a unified one that covers both.

---

### Step 3: Generate competing hypotheses — don't stop at the first plausible one

**Hypothesis A: `proxy_read_timeout 5s` on reports alone**
- Explains: reports endpoint 504s ✅
- Explains: health check 504s ❌ (a 10ms response can't exceed a 5s timeout under normal load)
- Explains: 10% rate across all traffic ❌ (only possible if total volume is ~300 req/hour — very low for prod)

**Hypothesis B: `proxy_read_timeout 5s` causing upstream connection pressure**
- The reports endpoint holds nginx→Node.js connections open for up to 5s before nginx times out
- If nginx is configured with a limited upstream connection pool (`keepalive` + `keepalive_requests`), those slow connections fill the pool
- New requests — including health checks — queue waiting for an available upstream connection
- If queued long enough, nginx's own internal timeout fires → 504 even on fast endpoints
- Explains: ALL endpoints being affected ✅
- Explains: health check 504s ✅
- Explains: proportional to reports load ✅

**Hypothesis C: Something else in nginx-hardened-v2 template (not shown in excerpt)**
- The excerpt says "excerpted" — we're only seeing a slice
- The template includes "rate limiting rules," "TLS settings," and other changes
- If `limit_req` with `nodelay` off is applied broadly, it could create queueing under load
- If `worker_connections` was reduced, or upstream keepalive limits changed, that could explain all-endpoint impact
- Confidence: **medium** — we literally cannot see the full config

**Hypothesis D: Audit logging middleware adding latency**
- New middleware was added for "audit compliance"
- If it writes synchronously to disk or a remote endpoint, it adds latency to every request
- Combined with `proxy_read_timeout 5s`, even 5-6 second middleware delays would cause 504s
- Explains: ALL endpoints affected ✅
- But: event loop lag of 45ms peak argues against blocking I/O on every request ❌

**Hypothesis E: Node.js 18.17 → 18.19 regression**
- This is a minor security patch; regressions in patch versions are rare
- No specific evidence pointing here
- Confidence: **low** — don't chase this unless others are ruled out

---

### Step 4: Steelman the non-obvious hypothesis

The full-config hypothesis (C) deserves attention even though it feels like hand-waving. The nginx-hardened-v2 template represents a **significant system-level change** touching multiple subsystems simultaneously. The security team's hardening often involves reducing resource limits (worker connections, upstream connections, buffer sizes) alongside timeout changes. We're only seeing one section of that config. If, say, `upstream keepalive 5` is set (limiting nginx to 5 persistent connections to Node.js), then 30 slow report requests/hour — each held for 5s — could saturate that pool during any 5-second window, causing a cascading queue for all other requests.

---

### Step 5: What's the root cause?

There are **two distinct problems**, not one:

#### Problem 1 (Certain): `proxy_read_timeout 5s` is far too aggressive

```nginx
proxy_read_timeout    5s;   # Reduced from default per security policy
```

The default is **60 seconds**. Reducing it to 5 seconds means any upstream response slower than 5 seconds returns a 504. Your reports endpoint is ~6-8 seconds. This is a direct, certain cause of 504s on `/reports/comprehensive`.

The security rationale (preventing slow-loris-style attacks) is real but mis-applied here. `proxy_read_timeout` measures time between successive reads from the upstream, not total response time — but for a synchronous DB-backed endpoint, the first meaningful data arrives only after the query completes.

#### Problem 2 (Highly probable, but partially unverifiable without full config): nginx-hardened-v2 introduces additional resource constraints

The health-check 504s are the disconfirming evidence for a simple "slow endpoint = 504" story. The most parsimonious explanation is that the new template reduced upstream connection pool limits or worker connection limits, and the slow reports connections are exhausting that pool and causing queuing across all endpoints.

---

### Step 6: What I am NOT certain about

I want to be explicit:

- **Cannot confirm** the upstream connection pool exhaustion theory without seeing the full nginx-hardened-v2 template (specifically `upstream` block, `keepalive`, `worker_connections`)
- **Cannot confirm** whether audit logging middleware contributes — depends on its implementation
- **Cannot confirm** whether 10% error rate is consistent with reports-only failures — depends on total request volume, which isn't given

---

### Recommended actions, in priority order

**1. Emergency mitigation — nginx timeout (do now)**

Raise `proxy_read_timeout` globally to a safer value, *or* apply a specific override for the reports location:

```nginx
# Option A: Fix globally (simplest, safest short-term)
proxy_read_timeout 30s;

# Option B: Location-specific override (better long-term)
location /api/v2/reports/ {
    proxy_read_timeout 30s;
    # Or even higher if needed
}
```

30s leaves margin above your ~8s query while still protecting against genuinely stuck connections.

**2. Audit the full nginx-hardened-v2 template — not just the excerpt**

Ask DevOps for the complete config. Look specifically at:
- `upstream` block: is there a `keepalive` directive limiting connection pool size?
- `worker_connections` value
- Whether `limit_req` is applied to health check endpoints
- Any `proxy_buffer` size reductions that could cause buffering stalls

**3. Fix the reports endpoint itself — independently of the timeout**

The 8-second query is a debt that will bite you even after fixing nginx. Options:
- **Async job model**: POST returns `{ job_id }`, client polls `GET /reports/jobs/{id}` — correct approach for long-running aggregations
- **Query optimization**: 6 table joins with 7.8s execution time on staging suggests missing indexes or a suboptimal join order. Run `EXPLAIN ANALYZE` and check for sequential scans on large tables
- **Caching**: If reports are for the same parameters repeatedly, cache at the application layer

**4. Check audit logging middleware implementation**

Verify it's writing asynchronously. If it's doing synchronous writes to disk or synchronous HTTP calls to an audit service on every request, it's adding latency to all endpoints. This is a secondary suspect for the broad impact.

---

### Summary

| Finding | Confidence | Evidence |
|---|---|---|
| `proxy_read_timeout 5s` causes reports 504s | **Certain** | 8s query > 5s timeout, same deployment window |
| nginx config change affects all endpoints | **High** | Health check 504s can't be explained by slow query alone; full config not visible |
| Audit middleware contributes | **Possible** | No concrete evidence; needs investigation |
| Node.js version is relevant | **Low** | Patch version, no evidence |

The `proxy_read_timeout` fix is safe to deploy immediately. The rest requires investigation into the full nginx config before drawing conclusions.

## Response B
## Root Cause: `proxy_read_timeout 5s` in nginx-hardened-v2

The nginx migration in 2.14.0 reduced `proxy_read_timeout` from nginx's default (60s) to **5 seconds**. Your new reports endpoint takes ~5,500–7,847ms. Every reports request exceeds the timeout, so nginx returns 504 before Node.js finishes — even though the backend is healthy.

### Why ALL endpoints are affected, not just `/reports/comprehensive`

nginx reuses upstream keepalive connections by default. When a reports request times out at 5s, nginx closes its end of the connection — but Node.js is still writing the response body to that socket. When nginx reuses that same upstream connection for a subsequent request (e.g., a health check), it reads stale/partial data from Node.js's in-flight reports response and times out waiting for a valid response. This is a known failure mode with nginx keepalive + long upstream responses.

The timeline confirms it: errors appeared 15 minutes after deploy, matching the start of reports traffic. The errors are proportional to reports call volume (~30/hr), which explains the ~10% error rate rather than 100%.

### Evidence summary

| Clue | Explanation |
|---|---|
| 504s started 15 min post-deploy | Reports traffic began; first keepalive connection corruption |
| nginx-hardened-v2 migrated in 2.14.0 | Introduced the 5s timeout |
| Health checks (<10ms) also get 504s | Keepalive connection reuse after upstream timeout |
| DB pool healthy (12/50), event loop healthy (2ms avg) | Node.js backend is fine; nginx is the problem |
| Node.js runtime update is a red herring | 18.17→18.19 has no timeout behavior changes |

### Fixes

**Immediate (stops the bleeding):**

Increase `proxy_read_timeout` globally in nginx to match your ALB idle timeout:

```nginx
proxy_read_timeout 60s;  # Restore to a safe default
```

Or override just for the slow endpoint:

```nginx
location /api/v2/reports/comprehensive {
    proxy_read_timeout 30s;
}
```

Also disable upstream keepalive or flush the connection state after a timeout until you understand the full DevOps template:

```nginx
proxy_http_version 1.1;
proxy_set_header Connection "";  # enable keepalive properly, or
# proxy_set_header Connection "close";  # disable it temporarily
```

**Short-term (proper fix for the reports endpoint):**

A 6–8 second synchronous HTTP response is problematic regardless of timeouts. Convert to an async job pattern:

1. `POST /api/v2/reports/comprehensive` → returns `{ jobId: "..." }` immediately
2. `GET /api/v2/reports/comprehensive/{jobId}` → returns result when ready (or 202 if still processing)

This eliminates the timeout problem entirely and makes the endpoint resilient to client disconnects.

**On the DevOps template:**

The `proxy_read_timeout 5s` comment says "reduced from default per security policy" — but there's no security rationale for a 5s read timeout on a proxied API. Push back on this with the SecOps team; the correct security control here is rate limiting and request size limits, not connection timeouts. The timeout was almost certainly cargo-culted from a different context (e.g., downstream client timeouts).

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
