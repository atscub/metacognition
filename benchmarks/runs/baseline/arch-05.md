## The Core Mistake: One Auth Strategy for Three Different Problems

Both engineers are arguing past each other because they're each right about different client types. The current system fails because it applies one token format uniformly. The fix isn't "JWTs vs sessions" — it's using the right mechanism per client.

---

## Strategy by Client Type

### Client 1: Mobile — Access/Refresh Token Pair

The 24-hour expiry is the wrong fix for a real problem. Short access tokens + long refresh tokens solve it without logging users out.

**Access token (JWT, RS256):**
```python
{
  "sub": "user_123",
  "roles": ["user"],
  "client": "mobile",
  "exp": now + 15 minutes,   # short-lived; limits exposure window
  "jti": "<uuid>"            # allows targeted blocklisting if needed
}
```

**Refresh token (opaque, server-side):**
```python
# Stored in DB:
{
  "token_hash": sha256(raw_token),
  "user_id": "user_123",
  "family_id": "<uuid>",     # for theft detection
  "expires_at": now + 30 days,
  "rotated": False
}
```

**Rotation flow:**
1. Mobile presents expired access token + valid refresh token
2. Server verifies refresh token hash, issues new access + refresh token pair
3. Old refresh token is invalidated (one-time use)
4. If a refresh token is reused → the entire family is revoked (theft signal)

**Offline support:** The JWT carries enough claims for cached data access. Mark sensitive mutations as pending offline; validate token hasn't been revoked on reconnect before flushing.

**Revocation:** Revoke the refresh token row → user is logged out at next token refresh (worst case: 15 minutes). For immediate revocation: maintain a Redis blocklist keyed by `jti`, with TTL equal to the access token lifetime. Blocklist stays tiny because entries self-expire.

---

### Client 2: Admin Panel — Server-Side Sessions (No JWTs)

The compliance requirement ("revocable within 5 seconds") makes this decision for you. A JWT blocklist that propagates in < 5 seconds is functionally a session store — you've rebuilt sessions with extra steps.

**Session token:** Opaque 256-bit random token, delivered as `HttpOnly; Secure; SameSite=Strict` cookie.

**Session record in Redis:**
```python
{
  "session_id": "<opaque_token>",        # key
  "user_id": "admin_456",
  "roles": ["admin"],
  "created_at": timestamp,
  "last_active": timestamp,              # for inactivity timeout
  "ip": "...",                           # anomaly detection
  "ttl": 30 minutes sliding             # Redis TTL, reset on activity
}
```

**Revocation:** `DEL session:<token>` in Redis. Propagation time: the next request from that session, which will fail validation immediately. Well under 5 seconds.

**Inactivity timeout:** On each authenticated request, `EXPIRE session:<token> 1800`. No activity → Redis TTL fires, session is gone.

**Automated revocation triggers:**
- Employee offboarding event → delete all sessions by `user_id` index
- Password change → delete all sessions except current
- Security event webhook → delete by user or session ID

**Why not short JWTs here?** Even 5-minute JWTs leave a 5-minute window. Honoring a 5-second SLA requires per-request server validation — which is exactly what sessions do, but without the complexity of managing a JWT blocklist with sub-5-second propagation guarantees.

---

### Client 3: Third-Party Integrations — API Keys

JWTs embedded in CI configs are a configuration anti-pattern. API keys are the right primitive: they don't expire unless you rotate them, they're revocable instantly, and they're the industry standard (see AWS, Stripe, GitHub).

**Key format:** `cld_live_<32_random_bytes_base58>` — the prefix makes them greppable for secret scanning.

**Storage:**
```python
{
  "key_id": "key_abc",
  "key_hash": sha256(raw_key),   # never store plaintext
  "org_id": "org_789",
  "scopes": ["infra:read", "deploys:write"],
  "rate_limit": 15000,           # per hour
  "created_at": timestamp,
  "expires_at": None,            # null = non-expiring
  "active": True
}
```

**Zero-downtime rotation:**
1. Org generates Key B while Key A is still active
2. Integration updates config to Key B, deploys, verifies
3. Org explicitly revokes Key A
4. Support multiple active keys per org (no arbitrary limit)

This eliminates the silent 3 AM failure. Keys break only when explicitly revoked.

**Performance at 10K+ req/hour:** Validate against a Redis cache keyed by `sha256(raw_key)`, TTL 60 seconds. On revocation, immediately delete cache entry. Validation cost: one Redis GET per request instead of a DB query.

---

## Unified Middleware

```python
def authenticate(request):
    # Route to the right strategy based on explicit signal
    auth_header = request.headers.get('Authorization', '')
    
    if auth_header.startswith('APIKey '):
        return authenticate_api_key(auth_header[7:])
    
    client_type = request.headers.get('X-Client-Type', '')
    
    if client_type == 'admin':
        return authenticate_session(request.cookies.get('session'))
    
    if client_type == 'mobile':
        token = auth_header.replace('Bearer ', '')
        return authenticate_jwt(token, expected_client='mobile')
    
    raise Unauthorized("Missing or unrecognized auth method")
```

Use an explicit `X-Client-Type` header rather than inferring from token format — ambiguity here is a security risk.

---

## Directly Answering the Team Debate

| | Tech Lead ("JWTs scale") | Security Engineer ("sessions revoke") |
|---|---|---|
| Mobile | Correct | Overfit — 15-min JWT + refresh is sufficient |
| Admin | Wrong — revocation requirement rules it out | Correct |
| Integrations | Wrong framing — API keys, not JWTs | Also wrong framing |

The mistake is treating "auth mechanism" as a system-wide binary choice. The three client types have genuinely incompatible requirements:

- **Mobile** needs stateless local validation for offline support + high request volume → short JWT + server-side refresh token
- **Admin** needs sub-5-second revocation with no tolerance for a validity window → server-side sessions
- **Integrations** need stable, non-expiring credentials with explicit lifecycle management → API keys

Redis is now a critical dependency for admin sessions and API key caching. That's the real infrastructure tradeoff to solve — Redis Cluster with read replicas, not the JWT vs sessions debate.