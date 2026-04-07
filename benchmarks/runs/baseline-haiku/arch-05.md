I'll design a **hybrid authentication system** that rejects the false binary choice ("JWTs vs sessions") and uses the right tool for each client type. The security engineer and tech lead are both right—about different parts of the system.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    CloudDash Auth System                     │
├──────────────┬──────────────────────┬──────────────────────┤
│  Mobile App  │    Admin Panel       │  Third-Party API     │
├──────────────┼──────────────────────┼──────────────────────┤
│ Refresh      │ Short-lived JWT +    │ Scoped API Key       │
│ Token (RS)   │ Server Session       │ (Vault-backed)       │
│              │ (Revocation List)    │                      │
│ Long-lived   │ 15-min expiry        │ No expiry            │
│ Access Token │ 5-sec revocation     │ Rotatable            │
│ (offline)    │                      │                      │
└──────────────┴──────────────────────┴──────────────────────┘
```

---

## 1. Admin Panel: Short-Lived JWT + Revocation List

**Why this approach:** Admins need instant revocation *and* efficient validation at scale.

### Token Format
```python
# Access token (issued at login) — short expiry
{
    'sub': admin_user_id,
    'client_type': 'admin_panel',
    'session_id': 'sess_8f2a9d1b',  # Links to server-side session
    'roles': ['admin', 'audit_reader'],
    'iat': <issued_at>,
    'exp': <now + 15 minutes>,
    'jti': '<unique_token_id>'  # For revocation tracking
}
```

### Revocation Strategy
```python
# Redis: fast, in-memory revocation list (TTL = token lifetime)
class RevocationManager:
    def revoke(self, session_id: str):
        """Instant revocation"""
        redis.setex(
            f'revoked_session:{session_id}',
            value='1',
            ex=3600  # TTL longer than max token lifetime
        )
    
    def is_revoked(self, session_id: str) -> bool:
        """O(1) check, ~1ms"""
        return redis.exists(f'revoked_session:{session_id}')

def validate_admin_token(token: str):
    payload = jwt.decode(token, ADMIN_SECRET, algorithms=['HS256'])
    
    # Check revocation FIRST (fastest path)
    if RevocationManager.is_revoked(payload['session_id']):
        raise Unauthorized("Session revoked")  # ~1ms
    
    # Then check expiry
    if payload['exp'] < time.time():
        raise Unauthorized("Token expired")
    
    return User(id=payload['sub'], roles=payload['roles'])
```

### Session Lifecycle (Server-Side)
```python
@dataclass
class AdminSession:
    session_id: str
    user_id: str
    created_at: datetime
    last_activity: datetime
    ip_address: str
    user_agent: str
    is_revoked: bool = False

# On login
session = AdminSession(
    session_id=secrets.token_urlsafe(32),
    user_id=user.id,
    created_at=now(),
    last_activity=now(),
    ip_address=request.ip,
    user_agent=request.headers['User-Agent']
)
db.sessions.insert(session)

# On every request: update last_activity
db.sessions.update(session_id, last_activity=now())

# Idle timeout check (30 minutes)
if (now() - session.last_activity) > 30 * 60:
    raise Unauthorized("Session idle")
```

### Revocation on Security Event (< 5 seconds)
```python
async def on_compromise_detected(admin_id: str):
    """Called when compromised credentials detected"""
    # 1. Revoke all active sessions (O(n) where n = ~200 admins)
    sessions = db.sessions.find_many(user_id=admin_id, is_revoked=False)
    session_ids = [s.session_id for s in sessions]
    
    # 2. Write to Redis (async, non-blocking)
    for session_id in session_ids:
        redis.setex(f'revoked_session:{session_id}', 1, 3600)
    
    # 3. Mark in DB (for audit trail)
    db.sessions.update_many(user_id=admin_id, is_revoked=True)
    
    # Next API call will hit revocation check and fail immediately
    # ~50ms end-to-end for typical admin with 2-3 sessions
```

**Benefit:** Instant revocation without invalidating all tokens globally. Within 5 seconds of event, existing credentials are unusable.

---

## 2. Mobile App: Refresh Token + Long-Lived Access Token

**Why this approach:** Mobile users stay logged in for weeks; 24-hour expiry creates frustration during incidents.

### Token Pair

**Access Token** (issued with refresh token)
```python
{
    'sub': user_id,
    'client_type': 'mobile',
    'scope': 'api:read,cache:write',
    'exp': <now + 7 days>,  # Long-lived for offline cache
    'device_id': 'device_abc123'  # Bind to device
}
```

**Refresh Token** (stored in secure DB, not JWT)
```python
@dataclass
class RefreshToken:
    token_id: str  # Unique, unguessable (secrets.token_urlsafe(32))
    user_id: str
    device_id: str
    created_at: datetime
    last_rotated_at: datetime
    expires_at: datetime  # 90 days
    revoked: bool = False
    
    # Rotation chain for security
    previous_token_id: str | None = None
```

### Token Exchange Flow
```python
def mobile_login(username, password, device_id):
    user = verify_credentials(username, password)
    
    # Create refresh token (server-side, not JWT)
    refresh_token = RefreshToken(
        token_id=secrets.token_urlsafe(32),
        user_id=user.id,
        device_id=device_id,
        created_at=now(),
        last_rotated_at=now(),
        expires_at=now() + timedelta(days=90)
    )
    db.refresh_tokens.insert(refresh_token)
    
    # Create access token (JWT, long expiry)
    access_token = jwt.encode({
        'sub': user.id,
        'client_type': 'mobile',
        'device_id': device_id,
        'exp': now() + timedelta(days=7)
    }, MOBILE_SECRET, algorithm='HS256')
    
    return {
        'access_token': access_token,
        'refresh_token': refresh_token.token_id,  # Opaque string
        'expires_in': 7 * 86400,
        'token_type': 'Bearer'
    }

def mobile_refresh(refresh_token: str):
    """Exchange refresh token for new access token"""
    rt = db.refresh_tokens.find_one(token_id=refresh_token)
    
    if rt.revoked or rt.expires_at < now():
        raise Unauthorized("Refresh token expired/revoked")
    
    # Rotate refresh token (new token issued, old marked as rotated)
    new_rt = RefreshToken(
        token_id=secrets.token_urlsafe(32),
        user_id=rt.user_id,
        device_id=rt.device_id,
        created_at=now(),
        last_rotated_at=now(),
        expires_at=now() + timedelta(days=90),
        previous_token_id=rt.token_id
    )
    db.refresh_tokens.insert(new_rt)
    db.refresh_tokens.update(rt.token_id, revoked=True)
    
    # Issue new access token with 7-day expiry
    new_access_token = jwt.encode({
        'sub': rt.user_id,
        'client_type': 'mobile',
        'device_id': rt.device_id,
        'exp': now() + timedelta(days=7)
    }, MOBILE_SECRET, algorithm='HS256')
    
    return {
        'access_token': new_access_token,
        'refresh_token': new_rt.token_id,
        'expires_in': 7 * 86400
    }
```

### Offline Mode: Cached Access Token
```python
# On mobile device (offline)
class OfflineCache:
    def cache_token(access_token: str, expires_at: datetime):
        """Store JWT locally (encrypted at rest via OS keychain)"""
        secure_storage.write('cached_access_token', access_token, expires_at)
    
    def get_cached_token() -> str | None:
        """Read from local storage when offline"""
        token, expires_at = secure_storage.read('cached_access_token')
        if expires_at > now():
            return token  # Use cached token
        return None

# Offline API calls
def api_call_offline(endpoint, params):
    token = OfflineCache.get_cached_token()
    if token:
        # Call API with cached token (will fail if revoked on server)
        # But app remains functional for reads until token expires
        return make_request(endpoint, params, token=token)
    else:
        raise OfflineError("No cached token; wait for connectivity")
```

**Benefit:** 7-day token expiry means mobile users rarely re-authenticate. Refresh token rotation (on every refresh) prevents token theft; old tokens become unusable. Offline mode works for ~7 days with cached tokens.

---

## 3. Third-Party Integrations: Scoped API Keys

**Why this approach:** Stateless, high-volume compatible; no expiry (keys rotated externally).

### API Key Format and Storage
```python
@dataclass
class ApiKey:
    key_id: str  # Public identifier (prefixed: pk_...)
    key_secret_hash: str  # Argon2 hash of actual secret
    organization_id: str
    scopes: list[str]  # ['infra:read', 'alerts:read', 'logs:read']
    name: str
    created_at: datetime
    last_used_at: datetime | None
    revoked: bool = False
    rate_limit: int = 10000  # requests/hour

# Database lookup (on every request)
def authenticate_api_key(api_key_string: str):
    key_id, key_secret = api_key_string.split('.')  # Format: pk_xxx.secret_yyy
    
    # Lookup by public ID (fast)
    key = db.api_keys.find_one(key_id=key_id)
    
    if not key or key.revoked:
        raise Unauthorized("Key revoked or invalid")
    
    # Verify secret (Argon2, slow but rare)
    if not argon2.verify(key.key_secret_hash, key_secret):
        raise Unauthorized("Invalid key secret")
    
    # Check rate limit (Redis counter)
    usage = redis.incr(f'api_usage:{key_id}', 1)
    if usage > key.rate_limit:
        raise RateLimited("Rate limit exceeded")
    
    # Update last_used_at (async)
    db.api_keys.update(key_id, last_used_at=now(), async=True)
    
    return Scope(organization_id=key.organization_id, scopes=key.scopes)
```

### Key Rotation (Zero Downtime)
```python
def rotate_key(key_id: str):
    """Old key remains active; new key issued"""
    old_key = db.api_keys.find_one(key_id=key_id)
    
    # Create new key
    new_key = ApiKey(
        key_id=f'pk_{secrets.token_urlsafe(16)}',
        key_secret_hash=argon2.hash(secrets.token_urlsafe(32)),
        organization_id=old_key.organization_id,
        scopes=old_key.scopes,
        name=f"{old_key.name} (rotated)",
        created_at=now()
    )
    db.api_keys.insert(new_key)
    
    # Return new key to user; old key still works for 7 days
    db.api_keys.update(old_key.key_id, expires_at=now() + timedelta(days=7))
    
    return new_key.key_id, new_key.key_secret
```

**Benefit:** Stateless (no sessions to maintain). API keys live indefinitely until rotated; can be revoked instantly. High volume requests don't require session lookups.

---

## Validation Middleware (Unified Entry Point)

```python
def authenticate(request) -> Scope:
    """Route to correct validator based on client type"""
    
    auth_header = request.headers.get('Authorization', '')
    
    # Detect client type from token format
    if auth_header.startswith('Bearer '):
        token = auth_header.replace('Bearer ', '')
        
        try:
            # Try to decode (doesn't verify yet)
            payload = jwt.decode(token, options={"verify_signature": False})
            client_type = payload.get('client_type')
        except:
            raise Unauthorized("Invalid token")
        
        if client_type == 'admin_panel':
            return validate_admin_token(token)
        elif client_type == 'mobile':
            return validate_mobile_token(token)
        else:
            raise Unauthorized("Unknown client type")
    
    elif auth_header.startswith('Bearer pk_'):
        # API key format
        api_key = auth_header.replace('Bearer ', '')
        return authenticate_api_key(api_key)
    
    else:
        raise Unauthorized("Missing or invalid Authorization header")
```

---

## How This Solves Original Problems

| Problem | Solution |
|---------|----------|
| **24-hour wait for revocation** | Admin revocation via Redis is instant (~50ms). Mobile refresh tokens rotated on use. API keys revocable immediately. |
| **Mobile logout frustration** | 7-day access tokens + offline caching. Mobile users rarely re-authenticate. |
| **Silent pipeline breaks** | API keys don't expire. Partners rotate keys on their schedule (not server-side expiry). |
| **One-size-fits-all tokens** | Three distinct strategies: JWT+session (admin), JWT+refresh (mobile), API key (integrations). |

---

## Summary of Trade-Offs

| Aspect | Admin | Mobile | Third-Party |
|--------|-------|--------|-------------|
| **Token Type** | JWT | JWT + Refresh | API Key (Vault) |
| **Expiry** | 15 min | 7 days | None |
| **Revocation** | Redis (instant) | Token rotation | Key revocation |
| **Storage** | DB (sessions) | DB (refresh tokens) | Vault |
| **Scaling** | O(n) session lookups; acceptable for ~200 admins | Refresh token rotation adds 1 DB write per 7 days | O(1) lookups; highest scale capability |
| **Offline Mode** | N/A | 7-day cached tokens | N/A |

The key insight: **reject the binary choice.** JWTs excel at reducing server state for integrations and mobile apps. Server-side sessions (with short JWT lifetimes) are essential for instant revocation. Using both in the right context solves the tension between scalability and security.