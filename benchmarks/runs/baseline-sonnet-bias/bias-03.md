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