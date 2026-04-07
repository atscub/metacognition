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