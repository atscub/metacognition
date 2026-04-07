# Task: arch-05 — Auth system design — JWT vs session tokens

## Prompt
You are designing the authentication system for CloudDash, a cloud infrastructure
management platform. The product has three client types:

**1. Mobile App (iOS + Android)**
- Native apps, ~15K daily active users
- Users stay logged in for weeks; sessions rarely expire
- Offline mode: must access cached data without round-tripping to the auth server
- API calls: ~50 requests/minute per active user during infrastructure incidents

**2. Admin Panel (Web SPA)**
- Used by ~200 internal operators and customer support staff
- Handles sensitive operations: user deletion, billing adjustments, infrastructure
  teardown, audit log access
- Security requirement from compliance: "Any admin session must be revocable within
  5 seconds of a security event (e.g., compromised credentials, terminated employee)"
- Admin sessions should timeout after 30 minutes of inactivity

**3. Third-Party Integrations**
- 40+ partners use the CloudDash API for CI/CD pipelines, monitoring dashboards, etc.
- Authentication via API keys with scoped permissions
- Some integrations make 10K+ requests/hour
- Keys must be rotatable without downtime

Current (broken) implementation:
```python
# auth/middleware.py — current unified approach
SECRET_KEY = os.environ['JWT_SECRET']

def authenticate(request):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        return User(id=payload['sub'], roles=payload['roles'])
    except jwt.ExpiredSignatureError:
        raise Unauthorized("Token expired")
    except jwt.InvalidTokenError:
        raise Unauthorized("Invalid token")

# Token issued at login:
def login(username, password):
    user = verify_credentials(username, password)
    token = jwt.encode({
        'sub': user.id,
        'roles': user.roles,
        'exp': datetime.utcnow() + timedelta(hours=24),
    }, SECRET_KEY, algorithm='HS256')
    return {'access_token': token}
```

Problems with the current system:
- When an admin's credentials were compromised last month, it took 24 hours to revoke
  access (had to wait for JWT expiry). The incident report flagged this as a P0.
- Mobile users complain about being logged out every 24 hours and having to re-enter
  credentials during critical infrastructure incidents.
- Third-party integrations have embedded JWTs in their CI configs; when tokens expire,
  their pipelines break silently at 3 AM.
- All three client types share the same token format, making it impossible to apply
  different security policies.

The team is debating: **Should we switch entirely to server-side sessions, or fix the
JWT implementation?**

The tech lead argues: "JWTs are stateless and scale better. We just need shorter expiry
times and a refresh token flow."

The security engineer argues: "Server-side sessions give us instant revocation. JWTs are
fundamentally unsuitable for anything requiring revocation."

Design the auth system. Specify the token format, storage, expiry, and revocation
strategy. Address all three client types and the problems listed above.


## Response A
## First Principles Decomposition

Before touching the solution space, let me strip away the vocabulary.

---

### Step 1: Problem Without Jargon

> "We have three different kinds of callers making requests. We need to know who they are and whether they're allowed. Some callers we must be able to kick out instantly. Some callers must work without a network. Some callers make huge numbers of requests and their credentials must be changeable on demand. Right now everyone uses the same mechanism, and it satisfies none of them."

The debate framing ("JWTs vs sessions") is already wrong — it assumes one mechanism must serve all three callers. That's the inherited assumption to break.

---

### Step 2: Atomic Components Per Caller

**What does "authentication" actually require at its core?**

```
Input:  credential attached to request
Output: identity + permissions  OR  rejection
The ???: look up or decode the credential → check if it's still valid
```

The moment you need to *stop* a valid credential from working, you need something the server controls. The moment you need to work *without the server*, you need something the client holds. These are in tension — and they pull differently for each caller type.

| Requirement | Admin | Mobile | Third-Party |
|---|---|---|---|
| Revoke in <5s | **YES** (compliance) | No | No (downtime-free rotation instead) |
| Work offline | No | **YES** | No |
| Long-lived session | No (30min) | **YES** (weeks) | YES (indefinite) |
| High request volume | No (200 users) | Medium (50/min) | **YES** (10K+/hr) |

---

### Step 3: Question Each Inherited Assumption

**"Shorter expiry + refresh tokens solves admin revocation"**

No. A 15-minute access token means a compromised admin still has up to 15 minutes. The compliance requirement is 5 seconds. The only mechanism that satisfies this is: the server checks a record it controls on *every* request, and can flip that record. That's a server-side session. This isn't a tradeoff — it's a hard constraint.

**"Server-side sessions don't scale"**

For 200 admin users? This is irrelevant. Even at 10K+/hour (third-party volume), a Redis lookup is microseconds. Scale arguments are for millions of users. Don't cargo-cult them here.

**"Mobile offline mode requires auth to work offline"**

No. Offline mode means serving *cached data* without network. Auth doesn't need to work offline — you just need the client to know it has a valid session, and serve cached data from local storage. The auth server is only consulted when online. The access token can be checked locally (JWT) to decide whether to show cached data; the server is authoritative for actual mutations.

**"All three clients must use the same token format"**

This is the root cause of all four problems listed. There is zero architectural requirement for this. The current code makes it an assumption by using a single `authenticate()` function. Separate them.

**"API keys must eventually expire"**

Why? If the key is server-side validated and revocable on demand, expiry adds nothing except breaking pipelines at 3 AM. The current problem is JWTs embedded in CI configs — those expire. API keys should be indefinite-lived, revocable-on-demand, and rotatable with overlap.

---

### Step 4: Rebuild from Fundamentals

**Start with the minimal solution for each client type, add complexity only when a simpler version demonstrably fails.**

---

## The Design

### Client Type 1: Admin Panel — Server-Side Sessions

**Mechanism:** Traditional server-side session with Redis store.

```python
# auth/admin_auth.py

SESSION_TTL = 30 * 60  # 30 minutes, reset on activity

def admin_login(username: str, password: str, request) -> dict:
    user = verify_credentials(username, password)
    assert_has_role(user, 'admin')
    
    session_id = secrets.token_urlsafe(32)
    session_data = {
        'user_id': user.id,
        'roles': user.roles,
        'ip': request.remote_addr,
        'user_agent': request.headers.get('User-Agent'),
        'created_at': time.time(),
    }
    redis.setex(f'admin_session:{session_id}', SESSION_TTL, json.dumps(session_data))
    
    response = make_response({'ok': True})
    response.set_cookie(
        'admin_session', session_id,
        httponly=True,
        secure=True,
        samesite='Strict',
        max_age=SESSION_TTL,
    )
    return response

def authenticate_admin(request) -> User:
    session_id = request.cookies.get('admin_session')
    if not session_id:
        raise Unauthorized("No session")
    
    raw = redis.get(f'admin_session:{session_id}')
    if not raw:
        raise Unauthorized("Session expired or revoked")
    
    data = json.loads(raw)
    
    # Reset TTL on activity (sliding window)
    redis.expire(f'admin_session:{session_id}', SESSION_TTL)
    
    return User(id=data['user_id'], roles=data['roles'])

def revoke_admin_session(session_id: str):
    """Instant revocation — takes effect on next request (<5s in practice)."""
    redis.delete(f'admin_session:{session_id}')

def revoke_all_admin_sessions(user_id: str):
    """For compromised credentials: nuke everything for this user."""
    # Use a secondary index: set of session_ids per user
    session_ids = redis.smembers(f'admin_user_sessions:{user_id}')
    pipe = redis.pipeline()
    for sid in session_ids:
        pipe.delete(f'admin_session:{sid}')
    pipe.delete(f'admin_user_sessions:{user_id}')
    pipe.execute()
```

**Why this satisfies the requirements:**
- Revocation: `redis.delete()` — effective on next request, well under 5 seconds.
- 30-minute inactivity timeout: sliding TTL, reset on each authenticated request.
- Session hijacking mitigation: bind session to IP + User-Agent (log deviations, optionally reject).
- No JWT needed. No refresh token complexity. 200 users is trivially served by Redis.

**What the tech lead gets wrong here:** There is no "fix" for JWT that gives you 5-second revocation without a server-side blocklist — at which point you've added all the statefulness of sessions with none of the simplicity. Sessions are the right tool.

---

### Client Type 2: Mobile App — Short-Lived JWTs + Server-Side Refresh Tokens

**Mechanism:** Access token (JWT, 15 min) + Refresh token (opaque, stored server-side, 30 days).

```python
# auth/mobile_auth.py

ACCESS_TOKEN_TTL  = 15 * 60       # 15 minutes
REFRESH_TOKEN_TTL = 30 * 24 * 3600  # 30 days

def mobile_login(username: str, password: str) -> dict:
    user = verify_credentials(username, password)
    return _issue_token_pair(user)

def _issue_token_pair(user: User) -> dict:
    # Access token: stateless JWT, short-lived
    access_token = jwt.encode({
        'sub': user.id,
        'roles': user.roles,
        'type': 'access',
        'exp': datetime.utcnow() + timedelta(seconds=ACCESS_TOKEN_TTL),
    }, MOBILE_SECRET, algorithm='HS256')
    
    # Refresh token: opaque, stored server-side so it can be revoked
    refresh_token = secrets.token_urlsafe(48)
    redis.setex(
        f'mobile_refresh:{refresh_token}',
        REFRESH_TOKEN_TTL,
        json.dumps({'user_id': user.id, 'issued_at': time.time()}),
    )
    
    return {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'expires_in': ACCESS_TOKEN_TTL,
    }

def refresh_mobile_token(refresh_token: str) -> dict:
    raw = redis.get(f'mobile_refresh:{refresh_token}')
    if not raw:
        raise Unauthorized("Refresh token invalid or expired")
    
    data = json.loads(raw)
    user = User.get(data['user_id'])
    
    # Rotate refresh token (prevents refresh token theft replay)
    redis.delete(f'mobile_refresh:{refresh_token}')
    return _issue_token_pair(user)

def authenticate_mobile(request) -> User:
    token = extract_bearer(request)
    try:
        payload = jwt.decode(token, MOBILE_SECRET, algorithms=['HS256'])
        assert payload.get('type') == 'access'
        return User(id=payload['sub'], roles=payload['roles'])
    except jwt.ExpiredSignatureError:
        raise Unauthorized("Token expired — refresh required")
    except jwt.InvalidTokenError:
        raise Unauthorized("Invalid token")

def revoke_mobile_user(user_id: str):
    """Force logout: delete all refresh tokens for this user."""
    # Track refresh tokens per user with a secondary index
    tokens = redis.smembers(f'mobile_user_refreshes:{user_id}')
    pipe = redis.pipeline()
    for t in tokens:
        pipe.delete(f'mobile_refresh:{t}')
    pipe.delete(f'mobile_user_refreshes:{user_id}')
    pipe.execute()
    # User's current access token lives up to 15 more minutes — acceptable for mobile
```

**Why 15 minutes is acceptable for mobile (unlike admin):**

The compliance requirement is on admin. For mobile, a 15-minute window on a compromised token is a known, documented risk tradeoff — not a compliance violation. Document this explicitly. If compliance later extends to mobile, shorten the window (5 min is still usable with auto-refresh).

**Offline mode:** The mobile client caches API responses locally. When offline, it serves cached data directly — the access token isn't re-validated (no network). When the user comes back online, the next real API call either succeeds or triggers a refresh. The client holds the access token in secure storage (Keychain/Keystore) and treats it as "probably still valid" for cache display. This is entirely a client-side concern; the server doesn't change.

**Why this solves the 3 AM logout problem:** Auto-refresh happens transparently. The mobile SDK calls `/auth/refresh` when it gets a 401, before retrying. Users never see a login screen unless the 30-day refresh token expires or they're explicitly revoked.

---

### Client Type 3: Third-Party Integrations — Hashed API Keys

**Mechanism:** Long-lived opaque API keys, stored as hashes, cached in Redis, scoped permissions in DB, rotation with overlap window.

```python
# auth/api_key_auth.py

CACHE_TTL = 60  # 1-minute cache; balance between performance and revocation lag

def create_api_key(partner_id: str, scopes: list[str], label: str) -> dict:
    raw_key = f"cdash_{secrets.token_urlsafe(40)}"  # Prefix for easy identification
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    
    db.execute("""
        INSERT INTO api_keys (id, partner_id, key_hash, scopes, label, created_at, active)
        VALUES (gen_random_uuid(), %s, %s, %s, %s, NOW(), TRUE)
    """, [partner_id, key_hash, json.dumps(scopes), label])
    
    # Return raw key ONCE — never stored in plaintext
    return {'key': raw_key, 'label': label, 'scopes': scopes}

def authenticate_api_key(request) -> ApiCaller:
    raw_key = extract_bearer(request)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    
    # Check Redis cache first
    cache_key = f'api_key:{key_hash}'
    cached = redis.get(cache_key)
    
    if cached == b'REVOKED':
        raise Unauthorized("API key revoked")
    
    if cached:
        data = json.loads(cached)
        return ApiCaller(partner_id=data['partner_id'], scopes=data['scopes'])
    
    # Cache miss — hit DB
    row = db.fetchone("""
        SELECT partner_id, scopes FROM api_keys
        WHERE key_hash = %s AND active = TRUE
    """, [key_hash])
    
    if not row:
        redis.setex(cache_key, CACHE_TTL, b'REVOKED')  # Cache negative result too
        raise Unauthorized("Invalid API key")
    
    data = {'partner_id': row['partner_id'], 'scopes': json.loads(row['scopes'])}
    redis.setex(cache_key, CACHE_TTL, json.dumps(data))
    return ApiCaller(**data)

def rotate_api_key(old_key_id: str, partner_id: str) -> dict:
    """
    Rotation protocol:
    1. Create new key (both keys valid simultaneously)
    2. Partner updates their config
    3. Partner calls confirm_rotation() or old key auto-expires in 24h
    """
    new_key_data = create_api_key(
        partner_id=partner_id,
        scopes=get_key_scopes(old_key_id),
        label=f"rotated-{datetime.utcnow().date()}"
    )
    # Schedule old key deactivation in 24h (gives partner time to deploy)
    db.execute("""
        UPDATE api_keys SET rotation_expires_at = NOW() + INTERVAL '24 hours'
        WHERE id = %s
    """, [old_key_id])
    return new_key_data

def revoke_api_key(key_id: str):
    key_hash = db.fetchone("SELECT key_hash FROM api_keys WHERE id = %s", [key_id])['key_hash']
    db.execute("UPDATE api_keys SET active = FALSE WHERE id = %s", [key_id])
    # Immediately poison the cache
    redis.setex(f'api_key:{key_hash}', CACHE_TTL, b'REVOKED')
```

**Why API keys, not JWTs, for third parties:**

The current problem is JWTs embedded in CI configs that expire silently. API keys don't expire — they're revoked explicitly. The partner never has to rotate on a schedule; they rotate when they choose to. The key is validated server-side, so scopes can be updated without reissuing the key.

**Performance at 10K+/hr:** That's ~167/min, ~3/sec. Redis cache with 1-minute TTL means one DB hit per key per minute in the worst case. Trivially handled. The 1-minute TTL also means revocation takes effect within 60 seconds — acceptable for API keys (vs. the 5-second admin requirement).

---

### The Unified Middleware

```python
# auth/middleware.py

def authenticate(request) -> User | ApiCaller:
    """Route to the correct auth handler based on credential type."""
    
    # Admin: session cookie
    if 'admin_session' in request.cookies:
        return authenticate_admin(request)
    
    token = request.headers.get('Authorization', '')
    
    if not token.startswith('Bearer '):
        raise Unauthorized("No credentials provided")
    
    raw = token[7:]
    
    # API keys have a known prefix
    if raw.startswith('cdash_'):
        return authenticate_api_key(request)
    
    # Otherwise: mobile JWT
    return authenticate_mobile(request)
```

---

### Adjudicating the Debate

| Claim | Verdict |
|---|---|
| "JWTs scale better" | True but irrelevant for 200 admin users. Don't optimize for a problem you don't have. |
| "Just use shorter expiry + refresh" | Insufficient for admin. 5-second revocation requires server-side state, period. |
| "Sessions give instant revocation" | Correct — but this doesn't mean sessions everywhere. Mobile has different constraints. |
| "JWTs are fundamentally unsuitable" | Too strong. JWTs are fine as short-lived access tokens where 15-min revocation lag is acceptable. |

Both engineers are solving for a single mechanism. The actual answer is that the requirements across three client types are genuinely incompatible with any single mechanism. The fix is to stop treating this as one problem.

---

### Summary: What Each Client Gets

| | Token Type | Expiry | Revocation | Storage |
|---|---|---|---|---|
| Admin | Session cookie (opaque) | 30min sliding | Instant (Redis delete) | Redis |
| Mobile access | JWT (signed) | 15 min | Via refresh token expiry | Redis (refresh only) |
| Mobile refresh | Opaque token | 30 days | Instant (Redis delete) | Redis |
| Third-party | Hashed API key | Never | ~60s (cache TTL) | Postgres + Redis |

**The incident from last month** (24-hour admin revocation) is solved by the session approach. `revoke_all_admin_sessions(user_id)` takes milliseconds. The next request from that user — whenever it arrives — hits a missing Redis key and gets a 401.

## Response B
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
