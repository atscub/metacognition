## The binary debate is a false dichotomy

Both engineers are arguing for a universal solution to three fundamentally different security models. The right answer is: **different clients get different auth mechanisms**, each matched to its actual requirements.

---

## Architecture Overview

```
Client Type         Mechanism              Revocation Strategy
─────────────────────────────────────────────────────────────
Admin Panel    →    Server-side sessions   Instant: delete from Redis
Mobile App     →    JWT + refresh tokens   Refresh-time + blocklist for emergencies
3rd-Party      →    API keys               Replace old key, add new; overlap window
```

---

## Admin Panel: Server-Side Sessions Only

The security engineer is right **for this client only**. The compliance requirement ("revoke within 5 seconds") is physically incompatible with stateless JWTs unless you build a blocklist — at which point you've rebuilt sessions with extra steps.

### Session design

```python
# auth/admin_sessions.py
import secrets
import json
from datetime import datetime

ADMIN_SESSION_TTL = 1800  # 30 minutes, slides on activity

def create_admin_session(user: AdminUser, request_context: dict) -> str:
    session_id = secrets.token_urlsafe(32)
    session_data = {
        'user_id': user.id,
        'roles': user.roles,
        'created_at': datetime.utcnow().isoformat(),
        'ip': request_context['ip'],
        'user_agent': request_context['user_agent'],
    }
    pipe = redis.pipeline()
    pipe.setex(f"session:{session_id}", ADMIN_SESSION_TTL, json.dumps(session_data))
    pipe.sadd(f"user_sessions:{user.id}", session_id)  # index for bulk revocation
    pipe.expire(f"user_sessions:{user.id}", 86400 * 7)
    pipe.execute()
    return session_id

def authenticate_admin(request) -> AdminUser:
    session_id = request.cookies.get('admin_session')
    if not session_id:
        raise Unauthorized("No session")

    raw = redis.getex(f"session:{session_id}", ex=ADMIN_SESSION_TTL)  # sliding window
    if not raw:
        raise Unauthorized("Session expired or revoked")

    data = json.loads(raw)
    return AdminUser(id=data['user_id'], roles=data['roles'])

def revoke_user_sessions(user_id: str):
    """Called on: employee termination, credential compromise, manual security action."""
    session_ids = redis.smembers(f"user_sessions:{user_id}")
    if session_ids:
        pipe = redis.pipeline()
        for sid in session_ids:
            pipe.delete(f"session:{sid}")
        pipe.delete(f"user_sessions:{user_id}")
        pipe.execute()
    # Sessions gone → next request within seconds gets 401
```

### Cookie configuration

```python
response.set_cookie(
    'admin_session',
    session_id,
    httponly=True,       # no JS access
    secure=True,         # HTTPS only
    samesite='Strict',   # CSRF protection
    max_age=None,        # session cookie, dies with browser
)
```

With 200 admin users, Redis memory cost is negligible (~500 bytes × 200 sessions = 100KB). The scalability argument doesn't apply here.

---

## Mobile App: Short-Lived JWTs + Server-Side Refresh Tokens

The tech lead is right **for this client**, with one critical fix: the refresh token must be server-side so it's revocable.

### Why short-lived JWTs work here

- 15-minute access tokens validate stateless at high frequency (50 req/min × 15K users = manageable)
- Revocation happens at refresh time, not every request
- Emergency revocation: add JTI to a Redis blocklist (rare, short-lived TTL)

### Token structure

```python
# auth/mobile_tokens.py
import uuid
from datetime import timedelta

ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=90)

def issue_mobile_tokens(user: User, device_id: str) -> dict:
    jti = str(uuid.uuid4())
    access_token = jwt.encode({
        'sub': user.id,
        'roles': user.roles,
        'jti': jti,
        'type': 'mobile_access',
        'exp': datetime.utcnow() + ACCESS_TOKEN_TTL,
        'iat': datetime.utcnow(),
    }, MOBILE_SECRET, algorithm='RS256')  # asymmetric: edge nodes can verify without secret

    refresh_token_id = str(uuid.uuid4())
    refresh_token_raw = secrets.token_urlsafe(32)

    db.refresh_tokens.insert({
        'id': refresh_token_id,
        'token_hash': sha256(refresh_token_raw),
        'user_id': user.id,
        'device_id': device_id,
        'expires_at': datetime.utcnow() + REFRESH_TOKEN_TTL,
        'superseded_at': None,  # set when rotated
        'revoked': False,
    })

    return {
        'access_token': access_token,
        'refresh_token': f"{refresh_token_id}.{refresh_token_raw}",
        'expires_in': int(ACCESS_TOKEN_TTL.total_seconds()),
    }
```

### Refresh with rotation (detects stolen tokens)

```python
def refresh_mobile_token(raw_refresh_token: str) -> dict:
    token_id, token_secret = raw_refresh_token.split('.', 1)
    record = db.refresh_tokens.get(id=token_id)

    if not record or record.revoked:
        raise Unauthorized("Refresh token revoked")

    if record.superseded_at is not None:
        # Token was already rotated — someone is replaying an old token.
        # This is a theft signal: revoke the entire family.
        revoke_all_device_tokens(record.user_id, record.device_id)
        raise Unauthorized("Token reuse detected — all sessions revoked")

    if sha256(token_secret) != record.token_hash:
        raise Unauthorized("Invalid refresh token")

    if record.expires_at < datetime.utcnow():
        raise Unauthorized("Refresh token expired")

    # Rotate: mark old as superseded, issue new
    db.refresh_tokens.update(id=token_id, superseded_at=datetime.utcnow())
    return issue_mobile_tokens(
        user=db.users.get(id=record.user_id),
        device_id=record.device_id,
    )
```

### Offline mode

The app stores access tokens locally. For offline cached data reads, the app uses the token to authenticate **locally** — the data layer checks token validity without hitting the network:

```python
# Mobile client-side (pseudocode)
def get_cached_data(resource_id):
    token = local_store.get_access_token()
    if token is None:
        raise NotAuthenticated()
    # For offline reads: accept expired tokens (they were valid when cached)
    payload = jwt.decode(token, PUBLIC_KEY, options={"verify_exp": False})
    return local_cache.get(resource_id, authorized_user=payload['sub'])
```

The JWT's offline utility is a **local authorization gate**, not a network auth check. This doesn't require server round-trips.

### Emergency revocation for mobile

```python
def emergency_revoke_mobile_user(user_id: str):
    # Mark all refresh tokens revoked in DB
    db.refresh_tokens.update_all(user_id=user_id, revoked=True)
    # Block any live access tokens via JTI blocklist (TTL = max access token lifetime)
    active_jtis = db.active_jtis_for_user(user_id)
    for jti in active_jtis:
        redis.setex(f"blocklist:jti:{jti}", 900, "1")  # 15 min TTL

def authenticate_mobile(request) -> User:
    token = extract_bearer(request)
    payload = jwt.decode(token, PUBLIC_KEY, algorithms=['RS256'])

    if redis.exists(f"blocklist:jti:{payload['jti']}"):
        raise Unauthorized("Token revoked")

    return User(id=payload['sub'], roles=payload['roles'])
```

This adds one Redis lookup per request, but only when you've added JTIs to the blocklist (which should be rare). Normal path has zero Redis lookups.

---

## Third-Party Integrations: API Keys

Neither JWT nor sessions. These are machine-to-machine credentials with different constraints entirely.

### Key design

```python
# auth/api_keys.py
import secrets
import hashlib

def generate_api_key(integration_id: str, scopes: list[str]) -> dict:
    raw_key = secrets.token_urlsafe(32)          # 256-bit entropy
    prefix = raw_key[:8]                          # shown in dashboard for identification
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    key_id = str(uuid.uuid4())
    db.api_keys.insert({
        'id': key_id,
        'integration_id': integration_id,
        'prefix': prefix,
        'key_hash': key_hash,
        'scopes': scopes,
        'created_at': datetime.utcnow(),
        'expires_at': None,
        'revoked': False,
        'rate_limit_rpm': 200,
    })

    # Show raw key ONCE — never stored, never recoverable
    return {'key': f"cd_{prefix}_{raw_key}", 'id': key_id}
```

### Zero-downtime rotation

The critical insight: support multiple active keys per integration simultaneously.

```
Rotation procedure:
1. Partner calls POST /api-keys → gets new key (old key still active)
2. Partner deploys new key to CI config
3. Partner calls DELETE /api-keys/{old_id} → old key revoked
4. No 3 AM pipeline failures
```

```python
def rotate_api_key(integration_id: str, old_key_id: str) -> dict:
    # Step 1: Create new key (old still active)
    new_key = generate_api_key(
        integration_id=integration_id,
        scopes=db.api_keys.get(id=old_key_id).scopes,
    )
    # Step 2: Return new key — caller deploys it
    # Step 3: Caller confirms deployment, then calls revoke_api_key(old_key_id)
    return new_key

def revoke_api_key(key_id: str):
    db.api_keys.update(id=key_id, revoked=True)
    redis.delete(f"api_key_cache:{key_id}")  # purge validation cache
```

### High-volume validation caching

At 10K req/hour, avoid hitting the DB on every request:

```python
API_KEY_CACHE_TTL = 30  # seconds — short enough to catch revocations quickly

def authenticate_api_key(request) -> Integration:
    raw_key = extract_bearer(request)
    if not raw_key.startswith("cd_"):
        raise Unauthorized("Invalid key format")

    prefix = raw_key[3:11]  # extract prefix for lookup
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    cache_key = f"api_key_cache:{key_hash[:16]}"

    cached = redis.get(cache_key)
    if cached:
        data = json.loads(cached)
        return Integration(id=data['integration_id'], scopes=data['scopes'])

    record = db.api_keys.get(prefix=prefix, key_hash=key_hash, revoked=False)
    if not record:
        raise Unauthorized("Invalid or revoked API key")

    redis.setex(cache_key, API_KEY_CACHE_TTL, json.dumps({
        'integration_id': record.integration_id,
        'scopes': record.scopes,
    }))
    return Integration(id=record.integration_id, scopes=record.scopes)
```

Revocation propagates within 30 seconds — acceptable for machine clients that aren't subject to the 5-second compliance requirement.

---

## Routing middleware

```python
# auth/middleware.py
def authenticate(request) -> AuthPrincipal:
    path = request.path
    auth_header = request.headers.get('Authorization', '')

    # Admin panel routes: cookie-based sessions
    if path.startswith('/admin/'):
        return authenticate_admin(request)

    # API key auth: machine clients
    if auth_header.startswith('Bearer cd_'):
        return authenticate_api_key(request)

    # Mobile JWT: everything else
    if auth_header.startswith('Bearer '):
        return authenticate_mobile(request)

    raise Unauthorized("No valid credentials")
```

---

## Summary: which problems are now solved

| Problem | Solution |
|---|---|
| 24h to revoke compromised admin | Admin sessions deleted from Redis → effective in <1 second |
| Mobile users logged out every 24h | 90-day refresh tokens, 15-min access tokens auto-renewed |
| Mobile offline access | JWT validated locally against cached data, `verify_exp=False` for reads |
| Pipelines breaking at 3 AM | API keys don't expire; rotation is overlap-based |
| Unified token format blocks per-client policy | Three separate auth paths with independent configuration |

---

## Where each engineer is right

**Tech lead is right that** short-lived JWTs + refresh tokens are the correct mobile pattern. The "just use shorter expiry" instinct is correct; the mistake was applying it everywhere including admin.

**Security engineer is right that** for admin, server-side sessions are the correct answer. But JWTs aren't "fundamentally unsuitable" — they're unsuitable specifically when you need sub-5-second revocation at request time without building a blocklist.

The mistake in the current implementation isn't the use of JWTs. It's using one mechanism for three different threat models.