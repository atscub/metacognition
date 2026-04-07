## Decompose Protocol

---

### Step 1 — Strip the Jargon

The system needs to answer two questions for every request: **who is this, and are they allowed?** Currently it hands out time-limited paper tickets at login. The tickets encode identity on their face so nobody needs to look anything up. Three problems: some users' tickets need to be cancelled mid-flight (can't do that — the ticket is self-contained), some users need to work without internet access (the ticket enables this, good), and some users need stable credentials that don't expire (the ticket expires).

The team has turned this into a philosophical debate — "JWT vs. sessions" — when the real observation is: **three client types with incompatible requirements are being forced through one token format**. That's the actual bug.

---

### Step 2 — Atomic Components

**Inputs:** A credential (password, token, key). A request (what they want).

**Outputs:** Identity confirmed/denied. Permission granted/denied.

**Real constraints** (non-negotiable, externally imposed):
- Admin revocation within 5 seconds — this is a compliance requirement, not a preference
- 30-minute admin inactivity timeout
- Mobile offline mode — must work without reaching the auth server
- Mobile sessions lasting weeks
- API key rotation without breaking pipelines mid-flight
- Mobile peak: ~750K req/min (50/user × 15K DAU)
- Integration peak: 10K+ req/hour per partner, 40+ partners

**Assumed constraints** (inherited from the current implementation, not actually required):
- All clients use the same token format — there is no reason for this
- Single shared secret — arbitrary
- 24-hour expiry across the board — satisfies nobody

**Core transformation:** Credential → verified identity + permissions. That's it.

---

### Step 3 — Question Each Component

**"JWTs scale better" (tech lead's claim):**

Let's test it numerically. Peak mobile load is ~12,500 req/sec. A Redis session lookup adds ~1ms round-trip. Redis handles ~1M ops/sec. The bottleneck is not session storage. The "stateless = scales better" claim is only meaningful at orders of magnitude higher throughput, or when you can't afford a fast store. You have Redis. This argument doesn't hold at this scale.

**"Sessions give instant revocation" (security engineer's claim):**

Correct, but overstated as "JWTs are fundamentally unsuitable." JWTs with a 15-minute expiry + a blocklist or server-side refresh token give you acceptable revocation for most clients. The security engineer is right about *admins* — 15 minutes is too long for a compromised employee who can tear down infrastructure. But 15 minutes is perfectly acceptable for mobile users.

**"JWT vs. sessions" as a binary:**

This is a false dilemma. The question is: *where does truth live?* In the token (fast but stale), in the server (fresh but requires lookup), or in both (hybrid). Different clients should answer this differently based on their actual requirements.

**The shared-token-format assumption:**

Removing this assumption dissolves most of the conflict. Admin needs instant revocation → server-side sessions. Mobile needs offline + long sessions → JWT access + server-side refresh. Integrations need stable, rotatable, scoped credentials → API keys. These aren't competing philosophies; they're three different problems that happened to share one (bad) implementation.

---

### Step 4 — Rebuild from First Principles

**Admin Panel:** The compliance requirement is "revoke within 5 seconds." The only mechanism that meets this is a server-side session: delete a Redis key and the session is gone in under a millisecond. Any JWT approach requires either (a) a blocklist (which is just a session store with extra steps) or (b) a 5-second expiry (which means constant re-auth overhead defeating the purpose). Use sessions.

**Mobile:** Needs offline-capable identity + long-lived sessions + tolerable revocation. The answer is the standard access token / refresh token split. A 15-minute JWT access token works offline, doesn't require a network call on every request, and means compromised tokens are live for at most 15 minutes. A long-lived refresh token stored server-side handles the "stay logged in for weeks" requirement. Revocation means revoking the refresh token; the access token decays on its own schedule.

**Integrations:** Neither JWTs nor sessions. API keys: opaque strings, stored as hashes, validated via a Redis-cached lookup. They don't expire on a schedule — they're revoked explicitly. Rotation without downtime means issuing the new key before revoking the old (configurable overlap window).

---

### Step 5 — Compare with Current Approach

The current implementation's failure modes are now mechanically explained:

| Problem | Root cause |
|---|---|
| 24-hour revocation window | JWT expiry is the only revocation mechanism; no server-side state |
| Mobile logout every 24 hours | Expiry calibrated for admin security, applied to all clients |
| CI pipelines breaking at 3AM | JWTs expire; API integrations need non-expiring credentials |
| Shared security policy | Single token format encodes a single policy for all three client types |

---

## The Design

---

### Architecture: Three Separate Auth Flows, One Entry Point

```
                    ┌──────────────────────────────────┐
                    │         authenticate()            │
                    │   (detects client type by token   │
                    │    format / route prefix)         │
                    └──────┬──────────┬────────────────┘
                           │          │          │
                    ┌──────▼──┐  ┌───▼────┐  ┌──▼──────────┐
                    │  Admin  │  │ Mobile │  │ Integration │
                    │Sessions │  │  JWT   │  │  API Keys   │
                    │(Redis)  │  │+ Refresh│  │  (hashed)   │
                    └─────────┘  └────────┘  └─────────────┘
```

---

### Client 1: Admin Panel — Server-Side Sessions

**Why:** The 5-second revocation requirement is the deciding constraint. Sessions stored in Redis can be deleted in under 1ms. No JWT-based approach meets this without becoming a session store anyway.

```python
# auth/admin_sessions.py
import secrets
import json
from datetime import datetime

ADMIN_SESSION_TTL = 30 * 60  # 30 minutes, sliding

def create_admin_session(user_id: str, roles: list, request_ip: str) -> str:
    session_id = secrets.token_urlsafe(32)
    session_data = {
        'user_id': user_id,
        'roles': roles,
        'ip': request_ip,
        'created_at': datetime.utcnow().isoformat(),
    }
    redis.setex(
        f'session:admin:{session_id}',
        ADMIN_SESSION_TTL,
        json.dumps(session_data)
    )
    return session_id

def validate_admin_session(session_id: str, request_ip: str) -> User:
    key = f'session:admin:{session_id}'
    raw = redis.get(key)
    if not raw:
        raise Unauthorized("Session expired or revoked")

    data = json.loads(raw)

    # Optional: IP binding for high-security operations
    if data['ip'] != request_ip:
        redis.delete(key)
        raise Unauthorized("Session IP mismatch")

    # Sliding window: reset TTL on activity
    redis.expire(key, ADMIN_SESSION_TTL)

    return User(id=data['user_id'], roles=data['roles'])

def revoke_admin_session(session_id: str):
    redis.delete(f'session:admin:{session_id}')

def revoke_all_admin_sessions(user_id: str):
    # Called on security event (terminated employee, compromised credentials)
    # Use a secondary index: set of session IDs per user
    session_ids = redis.smembers(f'user_sessions:{user_id}')
    pipeline = redis.pipeline()
    for sid in session_ids:
        pipeline.delete(f'session:admin:{sid}')
    pipeline.delete(f'user_sessions:{user_id}')
    pipeline.execute()
    # Propagation time: < 5ms. Meets compliance requirement.
```

**Storage:** HttpOnly, Secure, SameSite=Strict cookie. No localStorage — XSS cannot steal it.

**Revocation:** `revoke_all_admin_sessions(user_id)` is called immediately on security event. Propagation is synchronous with the next request (< 5ms). This meets the "<5 second" requirement.

**Inactivity timeout:** Redis TTL reset on every validated request. If no activity for 30 minutes, key expires and session is dead. No background jobs needed.

---

### Client 2: Mobile App — Short JWT + Server-Side Refresh Tokens

**Why:** Mobile needs offline operation (JWT validates without network), long sessions (refresh token lives for weeks), and reasonable revocation (refresh token can be invalidated; access token decays in 15 minutes — acceptable for mobile, not for admin).

```python
# auth/mobile_tokens.py
import secrets
from datetime import datetime, timedelta

ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=90)

def issue_mobile_tokens(user_id: str, device_id: str) -> dict:
    # Access token: short-lived JWT, works offline
    access_token = jwt.encode({
        'sub': user_id,
        'roles': get_user_roles(user_id),
        'client': 'mobile',
        'device': device_id,
        'exp': datetime.utcnow() + ACCESS_TOKEN_TTL,
        'iat': datetime.utcnow(),
    }, MOBILE_SECRET_KEY, algorithm='HS256')

    # Refresh token: opaque, stored server-side
    refresh_token = secrets.token_urlsafe(32)
    db.execute("""
        INSERT INTO refresh_tokens (token_hash, user_id, device_id, expires_at, used_at)
        VALUES (%s, %s, %s, %s, NULL)
    """, (hash_token(refresh_token), user_id, device_id,
          datetime.utcnow() + REFRESH_TOKEN_TTL))

    return {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'expires_in': int(ACCESS_TOKEN_TTL.total_seconds()),
    }

def refresh_mobile_tokens(refresh_token: str) -> dict:
    token_hash = hash_token(refresh_token)
    record = db.fetchone("""
        SELECT user_id, device_id, expires_at, used_at
        FROM refresh_tokens WHERE token_hash = %s
    """, (token_hash,))

    if not record:
        raise Unauthorized("Invalid refresh token")
    if record['expires_at'] < datetime.utcnow():
        raise Unauthorized("Refresh token expired")
    if record['used_at']:
        # Token reuse detected — possible theft; revoke all tokens for this user
        revoke_all_mobile_tokens(record['user_id'])
        raise Unauthorized("Refresh token already used — possible replay attack")

    # Single-use rotation: mark old token used, issue new pair
    db.execute("UPDATE refresh_tokens SET used_at = %s WHERE token_hash = %s",
               (datetime.utcnow(), token_hash))

    return issue_mobile_tokens(record['user_id'], record['device_id'])

def revoke_all_mobile_tokens(user_id: str):
    db.execute("DELETE FROM refresh_tokens WHERE user_id = %s", (user_id,))
    # Access tokens remain valid up to 15 minutes — acceptable for mobile

def validate_mobile_access_token(token: str) -> User:
    payload = jwt.decode(token, MOBILE_SECRET_KEY, algorithms=['HS256'])
    if payload.get('client') != 'mobile':
        raise Unauthorized("Wrong token type")
    return User(id=payload['sub'], roles=payload['roles'])
```

**Offline mode:** The 15-minute JWT validates locally on the device (or via cached public key). No network call required. During infrastructure incidents, mobile users can read cached data with their current access token even if auth servers are degraded.

**Long sessions:** Refresh tokens live 90 days and are silently rotated. Mobile SDKs handle refresh automatically before access token expiry. Users never see a login prompt unless they've been truly inactive for 90 days or their credentials were explicitly revoked.

**Revocation:** `revoke_all_mobile_tokens(user_id)` kills all refresh tokens. The user will be forced to re-authenticate at their next token refresh (within 15 minutes). This is the accepted trade-off for mobile — not P0 like admin.

**Replay detection:** Single-use refresh tokens with rotation. If a token is used twice, it indicates theft. All tokens for that user are immediately revoked.

---

### Client 3: Third-Party Integrations — API Keys

**Why:** CI/CD pipelines need stable credentials. JWTs expire (pipelines break at 3 AM). Sessions don't make sense for machine-to-machine. API keys are the right primitive: opaque, non-expiring by default, scoped, rotatable.

```python
# auth/api_keys.py
import hashlib
import secrets

KEY_PREFIX = 'cdash'

def generate_api_key(owner_id: str, scopes: list, label: str) -> dict:
    # Format: cdash_live_<32 random bytes in base62>
    raw_key = f'{KEY_PREFIX}_live_{secrets.token_urlsafe(32)}'
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    key_id = db.execute("""
        INSERT INTO api_keys (key_hash, owner_id, scopes, label, created_at, active)
        VALUES (%s, %s, %s, %s, NOW(), TRUE)
        RETURNING id
    """, (key_hash, owner_id, json.dumps(scopes), label))

    # Return raw key ONCE — never stored in plaintext
    return {'key_id': key_id, 'api_key': raw_key, 'scopes': scopes}

def validate_api_key(raw_key: str) -> User:
    if not raw_key.startswith(f'{KEY_PREFIX}_'):
        raise Unauthorized("Not an API key")

    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    # Redis cache: avoid DB hit on every request at 10K+ req/hour
    cached = redis.get(f'apikey:{key_hash}')
    if cached:
        data = json.loads(cached)
    else:
        data = db.fetchone("""
            SELECT owner_id, scopes, active FROM api_keys WHERE key_hash = %s
        """, (key_hash,))
        if not data:
            raise Unauthorized("Invalid API key")
        redis.setex(f'apikey:{key_hash}', 300, json.dumps(data))  # 5-min cache

    if not data['active']:
        raise Unauthorized("API key revoked")

    return ServiceAccount(id=data['owner_id'], scopes=data['scopes'])

def rotate_api_key(old_key_id: str, owner_id: str, overlap_seconds: int = 3600) -> dict:
    # Issue new key first — partner can configure their systems during overlap
    new_key_data = generate_api_key(owner_id,
                                    get_key_scopes(old_key_id),
                                    f"rotated from {old_key_id}")

    # Schedule old key deactivation after overlap window
    db.execute("""
        UPDATE api_keys SET deactivate_at = NOW() + INTERVAL '%s seconds'
        WHERE id = %s AND owner_id = %s
    """, (overlap_seconds, old_key_id, owner_id))

    return new_key_data  # New key returned; old key still works during overlap
```

**Rotation without downtime:** New key is issued first. The old key remains active for a configurable overlap window (default 1 hour). Partners update their CI config and verify the new key works before the old one is revoked. No 3 AM breakage.

**Scoped permissions:** Keys carry explicit permission scopes. A monitoring dashboard gets `read:metrics` — it cannot trigger infrastructure teardown even if the key is compromised.

**Caching:** The 5-minute Redis cache means the DB is not hit on every one of the 10K+ hourly requests. Revocation propagates within 5 minutes via cache TTL — acceptable for integrations. For immediate revocation, the cache key can be explicitly deleted.

---

### Unified Entry Point

```python
# auth/middleware.py
def authenticate(request):
    auth_header = request.headers.get('Authorization', '')
    session_cookie = request.cookies.get('admin_session')

    # Admin panel: cookie-based session
    if session_cookie:
        return validate_admin_session(session_cookie, request.remote_addr)

    if not auth_header.startswith('Bearer '):
        raise Unauthorized("No credentials provided")

    token = auth_header[7:]

    # API key: prefix-based detection
    if token.startswith('cdash_'):
        return validate_api_key(token)

    # JWT: decode header to check client type
    try:
        header = jwt.get_unverified_header(token)
        payload = jwt.decode(token, options={"verify_signature": False})
        client_type = payload.get('client')
    except jwt.InvalidTokenError:
        raise Unauthorized("Malformed token")

    if client_type == 'mobile':
        return validate_mobile_access_token(token)

    raise Unauthorized("Unknown token type")
```

---

### Summary: Why the Debate Was Wrong

The tech lead and security engineer were each right about *one* client type:

| Client | Tech Lead Right? | Security Engineer Right? | Actual answer |
|---|---|---|---|
| Admin Panel | No — 5-sec revocation rules out stateless | Yes — sessions are correct | Redis-backed sessions |
| Mobile App | Yes — short-lived JWT + refresh is correct | Partially — long-lived JWT is wrong | 15-min JWT + 90-day refresh token |
| Integrations | Irrelevant — neither sessions nor JWTs | Irrelevant | API keys with hashed storage |

The root mistake was asking "which authentication system should we use?" when the correct question was "what does each client type actually need, and what is the simplest primitive that satisfies exactly that?"

Three clients, three systems, one routing layer. The complexity is real but it's the complexity the problem actually has — not accidental complexity from forcing incompatible requirements through a single implementation.