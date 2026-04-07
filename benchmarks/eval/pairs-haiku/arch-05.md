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
Now let me apply this framework to the CloudDash auth problem:

---

## Step 1: Restate Without Jargon

**Current framing**: JWT vs. server-side sessions, stateless vs. stateful, revocation strategy.

**Reframed**: We have three groups of users with *completely different needs*:
- **Mobile**: Needs to work offline, stay logged in for weeks, rarely needs revocation
- **Admins**: Need instant revocation (5s), frequent inactivity timeouts (30m), handle sensitive ops
- **Integrations**: Need long-lived credentials, no interactive login, extreme reliability

The current system tries to use one token format for all three. The problems occur when we force a 24-hour expiry onto people who stay logged in for weeks, or when we can't revoke an admin token instantly.

**The core question**: Does a single auth mechanism even make sense here, or are we solving three different problems?

---

## Step 2: Identify Atomic Components

### **Inputs** (What comes in):
1. Initial credential verification (password, API key, etc.)
2. Subsequent requests with proof of previous auth
3. Security events (compromise detected, user deleted, etc.)

### **Outputs** (What must happen):
1. Allow legitimate requests to pass through
2. Block revoked/expired credentials immediately
3. Different policies for different user types (timeout, revocation speed, offline access)

### **Real Constraints** (not assumptions):
- Mobile must work offline → can't check server on every request
- Admin revocation must be <5 seconds → can't rely only on JWT expiry
- Integrations make 10K req/hour → can't afford high latency on every auth check
- Compliance requires audit trail of who accessed what when

### **Hidden Assumptions in the Current Design**:
- All three client types should use JWTs ← **Why?** Statelessness? But stateless doesn't mean simpler — it means moving the problem elsewhere.
- One expiry time fits all ← **Why?** Simplicity? But now we're breaking all three use cases.
- Token revocation means waiting for expiry ← **Why?** Because JWTs are signed blobs. But that's a limitation of the choice, not a law of nature.

---

## Step 3: Question Each Component

| Component | Question | Answer |
|-----------|----------|--------|
| **JWT for everyone** | Is this solving a real problem or inherited from "JWTs are stateless"? | Inherited. Statelessness only matters if auth is a bottleneck. For 3 client types with different needs, forced uniformity creates *more* complexity. |
| **24-hour expiry** | What if each client type had its own expiry? | Mobile: 90 days (cached, rarely refresh). Admin: 30 min. Integration: 1 year or never (API keys). This solves problems instead of creating them. |
| **Single token format** | What if we used different token types for different clients? | Admin tokens could be revocation-checked server-side; mobile could use long-lived JWTs with offline support; integrations use API keys entirely. |
| **"Revoke = wait for expiry"** | Is revocation actually a problem with JWTs, or a problem with how we're using them? | The *policy* (24h expiry, no revocation) is the problem. JWTs can be fine if you don't need instant revocation. But admins *do*, so they need a different mechanism. |

---

## Step 4: Rebuild from Fundamentals

**Insight**: Instead of choosing "JWTs or sessions?" globally, we should ask: *Which mechanism best fits each client type's actual constraints?*

### **For Mobile Users** (long-lived, offline, tolerates stale data):
- **Mechanism**: Long-lived JWT + optional refresh token
- **Expiry**: 90 days (users log in ~2x/quarter)
- **Revocation**: Best-effort (if compromised, add to blocklist; otherwise wait for expiry)
- **Offline**: Cache token locally, use it for offline requests
- **Rationale**: Stateless is actually good here — no server round-trip for offline access. Long expiry means no interruptions during incidents.

### **For Admin Sessions** (short-lived, must revoke instantly, sensitive operations):
- **Mechanism**: Short-lived JWT + server-side session revocation list
- **Expiry**: 30 minutes (JWT is just a compact credential carrier)
- **Revocation**: Write admin ID to Redis revocation list (checked on every request), revoke takes <100ms
- **Rationale**: JWT gives us a compact token to carry in the request. The server checks a revocation list on auth. Cost: one Redis lookup per request (acceptable for ~200 internal users).

### **For API Keys** (long-lived, no login, high volume, scoped):
- **Mechanism**: Stateless API keys (not JWTs) + optional short-term delegated tokens
- **Key format**: `key_<org-id>_<random>` (parseable, no secrets embedded)
- **Storage**: Hash in DB (bcrypt), check on every request, cache result for 60s
- **Rotation**: Issue new key, old one works for 24 hours (grace period), then disabled
- **Rationale**: API keys are explicitly designed for this; trying to shoehorn users into JWT login doesn't fit the integration model.

---

## Step 5: Compare with Current Approach

| Problem in Original | Root Cause | New Design |
|---|---|---|
| Admin compromise → 24h delay | Single JWT format forced on all users | Separate revocation list for admins, checked every request |
| Mobile users logged out every 24h | Assumed short expiry needed for security | 90-day mobile tokens, users rarely re-authenticate |
| Integration pipelines break at 3 AM | API keys embedded in configs, no revocation flow designed | Dedicated API key system, graceful rotation period |
| Impossible to apply different policies | Unified architecture treated policy as config | Three separate mechanisms, each optimized for its use case |

---

## The Real Decision

The tech lead says "JWTs just need refresh tokens." The security engineer says "JWTs are unsuitable." **Both are right, for different client types:**

- **JWTs are excellent for mobile** (stateless, offline-capable, long expiry reasonable)
- **JWTs are unsuitable for admins** (need instant revocation → add server state)
- **JWTs are irrelevant for integrations** (use dedicated API key system)

The mistake wasn't choosing JWTs; it was choosing one mechanism for three incompatible problems.

---

# AuthN Design for CloudDash

Based on this decomposition:

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Client Type                        │
├──────────────────┬──────────────────┬──────────────────┤
│  Mobile App      │  Admin Panel     │  Integrations    │
├──────────────────┼──────────────────┼──────────────────┤
│ Credential Type  │ Credential Type  │ Credential Type  │
│ → JWT            │ → JWT            │ → API Key        │
│ (long-lived)     │ (short-lived)    │ (key_...)        │
├──────────────────┼──────────────────┼──────────────────┤
│ Auth Path        │ Auth Path        │ Auth Path        │
│ → Verify sig     │ → Verify sig     │ → Hash check     │
│   (offline OK)   │ → Check revoke   │   & scope check  │
│                  │   (Redis)        │                  │
└──────────────────┴──────────────────┴──────────────────┘
```

---

## 1. Mobile Tokens (Long-Lived JWT)

**Token Format**:
```python
{
  "sub": "user_123",
  "type": "mobile",
  "roles": ["user"],
  "scopes": ["infrastructure:read", "infrastructure:write"],
  "iat": 1712515200,
  "exp": 1720291200,  # 90 days
  "device_id": "uuid"  # Tie to device for additional security
}
```

**Implementation**:
```python
# auth/tokens/mobile.py
from datetime import timedelta
import jwt

MOBILE_EXPIRY = timedelta(days=90)
MOBILE_SECRET = os.environ['JWT_MOBILE_SECRET']

def issue_mobile_token(user_id: str, device_id: str) -> str:
    """Issue a long-lived JWT for mobile clients."""
    now = datetime.utcnow()
    payload = {
        'sub': user_id,
        'type': 'mobile',
        'roles': get_user_roles(user_id),
        'scopes': get_user_scopes(user_id),
        'device_id': device_id,
        'iat': int(now.timestamp()),
        'exp': int((now + MOBILE_EXPIRY).timestamp()),
    }
    return jwt.encode(payload, MOBILE_SECRET, algorithm='HS256')

def verify_mobile_token(token: str) -> dict:
    """Verify mobile JWT (stateless, no revocation check)."""
    try:
        return jwt.decode(token, MOBILE_SECRET, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        raise Unauthorized("Token expired")
    except jwt.InvalidTokenError:
        raise Unauthorized("Invalid token")
```

**Why this works**:
- Stateless verification (no server round-trip for offline requests)
- Long expiry means no interruptions during incidents
- Device ID ties token to specific device (if device stolen, token is still bound)
- Mobile app caches token locally for offline access

**Revocation** (best-effort):
- If user's phone is lost, admin adds user ID to "mobile_revocation_list" (Redis, 24h TTL)
- On next online sync, mobile client checks if revoked and clears cached token
- This is "eventual" revocation, not instant, but acceptable for non-admins

---

## 2. Admin Tokens (Short-Lived JWT + Server-Side Revocation)

**Token Format**:
```python
{
  "sub": "admin_456",
  "type": "admin",
  "session_id": "sess_xyz789",  # Ties token to a revocable session
  "roles": ["admin"],
  "scopes": ["*"],  # Full access
  "iat": 1712515200,
  "exp": 1712516800,  # 30 minutes
}
```

**Implementation**:
```python
# auth/tokens/admin.py
from datetime import timedelta
from redis import Redis

ADMIN_EXPIRY = timedelta(minutes=30)
ADMIN_SECRET = os.environ['JWT_ADMIN_SECRET']
redis_client = Redis(host='localhost', port=6379, db=0)

def issue_admin_token(user_id: str) -> tuple[str, str]:
    """Issue admin JWT + session ID. Return (token, session_id)."""
    session_id = f"sess_{secrets.token_urlsafe(24)}"
    now = datetime.utcnow()
    
    payload = {
        'sub': user_id,
        'type': 'admin',
        'session_id': session_id,
        'roles': ['admin'],
        'scopes': ['*'],
        'iat': int(now.timestamp()),
        'exp': int((now + ADMIN_EXPIRY).timestamp()),
    }
    
    token = jwt.encode(payload, ADMIN_SECRET, algorithm='HS256')
    
    # Store session in Redis with 30-min TTL (matches token expiry)
    redis_client.setex(f"admin_session:{session_id}", 1800, user_id)
    
    return token, session_id

def verify_admin_token(token: str) -> dict:
    """Verify admin JWT + check revocation list."""
    try:
        payload = jwt.decode(token, ADMIN_SECRET, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        raise Unauthorized("Token expired")
    except jwt.InvalidTokenError:
        raise Unauthorized("Invalid token")
    
    # Check revocation list (instant revocation)
    session_id = payload['session_id']
    if not redis_client.exists(f"admin_session:{session_id}"):
        raise Unauthorized("Session revoked")
    
    # Refresh session TTL on every successful verification
    redis_client.expire(f"admin_session:{session_id}", 1800)
    
    return payload

def revoke_admin_session(session_id: str) -> None:
    """Instantly revoke an admin session (< 100ms)."""
    redis_client.delete(f"admin_session:{session_id}")
```

**Why this works**:
- JWT carries session ID (compact, can verify signature offline if needed)
- Server-side session in Redis = instant revocation (< 100ms)
- 30-minute expiry + inactivity timeout: every request refreshes the TTL
- If admin is terminated, security team deletes session ID from Redis; all tokens invalid immediately
- Audit trail: log every session creation/revocation to compliance DB

**Revocation Flow (5-second requirement)**:
```python
# admin/routes.py
@app.post('/api/admin/revoke-session')
@require_role('security_admin')
def revoke_session(session_id: str):
    """Security team revokes a compromised admin session."""
    revoke_admin_session(session_id)
    
    # Log to audit trail
    audit_log.write({
        'event': 'admin_session_revoked',
        'session_id': session_id,
        'revoked_by': request.user_id,
        'timestamp': datetime.utcnow(),
        'reason': request.json.get('reason'),
    })
    
    return {'status': 'revoked', 'affected_token_count': 1}
```

---

## 3. API Keys (Stateless + Optional Delegation)

**Key Format** (parseable, not a JWT):
```
key_<org_id>_<32-char-random>

Example: key_org_abc123_7K8mP9zXq2vY4nR6wL1sD5tF8gH2j3k4
```

**Implementation**:
```python
# auth/tokens/api_key.py
import hashlib
import hmac

class APIKey:
    """Stateless API key system."""
    
    def __init__(self, redis_client: Redis, db_client: Database):
        self.redis = redis_client
        self.db = db_client
        self.cache_ttl = 60  # Cache key validity for 60 seconds
    
    def issue_key(self, org_id: str, name: str, scopes: list[str]) -> str:
        """Issue a new API key."""
        key_id = f"key_{org_id}_{secrets.token_urlsafe(32)}"
        key_secret = secrets.token_urlsafe(64)
        
        # Store hashed secret + metadata in DB
        key_hash = hashlib.sha256(key_secret.encode()).hexdigest()
        
        self.db.api_keys.insert({
            'key_id': key_id,
            'key_hash': key_hash,  # Never store plaintext
            'org_id': org_id,
            'name': name,
            'scopes': scopes,
            'created_at': datetime.utcnow(),
            'status': 'active',
        })
        
        # Return only once (user must save it)
        return f"{key_id}:{key_secret}"
    
    def verify_key(self, key_id: str, key_secret: str) -> dict:
        """Verify API key with caching."""
        # Check cache first (60s TTL)
        cache_key = f"apikey:{key_id}"
        cached = self.redis.get(cache_key)
        if cached:
            return json.loads(cached)
        
        # Miss: check DB
        key_record = self.db.api_keys.find_one({
            'key_id': key_id,
            'status': 'active',
        })
        
        if not key_record:
            raise Unauthorized("Invalid API key")
        
        # Constant-time comparison to prevent timing attacks
        key_hash = hashlib.sha256(key_secret.encode()).hexdigest()
        if not hmac.compare_digest(key_hash, key_record['key_hash']):
            raise Unauthorized("Invalid API key")
        
        # Build credential object and cache
        credential = {
            'key_id': key_id,
            'org_id': key_record['org_id'],
            'scopes': key_record['scopes'],
            'type': 'api_key',
        }
        
        self.redis.setex(cache_key, 60, json.dumps(credential))
        return credential
    
    def rotate_key(self, key_id: str) -> tuple[str, str]:
        """Rotate an API key with grace period."""
        new_key = self.issue_key(
            org_id=self.db.api_keys.find_one({'key_id': key_id})['org_id'],
            name=f"{key_id} (rotated)",
            scopes=self.db.api_keys.find_one({'key_id': key_id})['scopes'],
        )
        
        # Mark old key as "rotating" (accepts requests for 24h, then disabled)
        self.db.api_keys.update_one(
            {'key_id': key_id},
            {'$set': {'status': 'rotating', 'rotation_deadline': datetime.utcnow() + timedelta(hours=24)}}
        )
        
        return new_key

def verify_api_key(request) -> dict:
    """Middleware to verify API key in Authorization header."""
    header = request.headers.get('Authorization', '')
    if not header.startswith('Bearer '):
        raise Unauthorized("Missing API key")
    
    key_id, key_secret = header[7:].split(':', 1)
    return APIKey(redis_client, db_client).verify_key(key_id, key_secret)
```

**Why this works**:
- Parseable key format (integrations can recognize them, easier to debug)
- No plaintext secrets stored (only hashed)
- Cache + 60s TTL = fast (10K req/hour = ~2.8 req/sec, cache hit rate >99%)
- Rotation with 24h grace period = no broken pipelines at 3 AM
- Scoped permissions = principle of least privilege (integrations can't access everything)

**Rotation Flow**:
```python
# integrations/routes.py
@app.post('/api/integrations/rotate-key')
def rotate_api_key():
    """Integration requests key rotation."""
    old_key_id = extract_key_id(request.headers['Authorization'])
    new_key, expiry = APIKey(redis_client, db_client).rotate_key(old_key_id)
    
    return {
        'new_key': new_key,
        'note': 'Old key valid for 24 hours, then disabled automatically',
        'rotation_deadline': expiry,
    }
```

---

## 4. Unified Auth Middleware

```python
# auth/middleware.py — NOW DELEGATES TO SPECIFIC HANDLERS
def authenticate(request) -> AuthContext:
    """Route to the correct auth handler based on credential type."""
    
    header = request.headers.get('Authorization', '')
    
    # Identify credential type
    if header.startswith('Bearer '):
        token = header[7:]
        
        # Try to decode JWT (fast path, no server state)
        try:
            payload = jwt.decode(token, options={'verify_signature': False})
            token_type = payload.get('type')
        except:
            raise Unauthorized("Invalid token")
        
        if token_type == 'mobile':
            return verify_mobile_token(token)
        elif token_type == 'admin':
            return verify_admin_token(token)
        else:
            raise Unauthorized("Unknown token type")
    
    elif header.startswith('Bearer key_'):
        key_id, key_secret = header[7:].split(':', 1)
        return verify_api_key(key_id, key_secret)
    
    else:
        raise Unauthorized("Invalid authorization header")

# Middleware registration (Flask example)
@app.before_request
def require_auth():
    """Protect all /api/* routes."""
    if request.path.startswith('/api/'):
        try:
            request.user = authenticate(request)
        except Unauthorized as e:
            return jsonify({'error': str(e)}), 401
```

---

## 5. Security & Compliance

### **Secrets Management**:
```python
# Don't store secrets in code
SECRETS = {
    'JWT_MOBILE_SECRET': os.environ['JWT_MOBILE_SECRET'],
    'JWT_ADMIN_SECRET': os.environ['JWT_ADMIN_SECRET'],
}

# Rotate secrets every 90 days
# Old secrets still valid for 7 days (grace period for cached tokens)
```

### **Audit Trail**:
```python
# Log all auth events for compliance
audit_log = {
    'mobile_token_issued': {'user_id', 'device_id', 'timestamp'},
    'mobile_token_revoked': {'user_id', 'reason', 'timestamp'},
    'admin_session_created': {'user_id', 'session_id', 'ip', 'timestamp'},
    'admin_session_revoked': {'session_id', 'revoked_by', 'reason', 'timestamp'},
    'api_key_issued': {'org_id', 'key_id', 'scopes', 'timestamp'},
    'api_key_rotated': {'old_key_id', 'new_key_id', 'timestamp'},
    'failed_auth_attempt': {'credential_type', 'reason', 'ip', 'timestamp'},
}
```

### **Incident Response**:
```python
# If admin credentials compromised
1. Security team calls DELETE /api/admin/sessions/{user_id}
2. All active sessions for that user revoked immediately (< 100ms)
3. New login required with forced 2FA
4. Audit log records: who, when, why

# If API key compromised
1. Integration requests rotation
2. Old key marked as "rotating" (24h grace)
3. New key issued immediately
4. Old key disabled after 24h (pipelines have time to update)
5. Audit log records: compromise reason, rotation deadline
```

---

## Summary Table

| Aspect | Mobile | Admin | Integration |
|--------|--------|-------|-------------|
| **Token Type** | Long JWT | Short JWT | API Key |
| **Expiry** | 90 days | 30 min | Never (rotated) |
| **Server State** | None | Redis (revocation) | DB (scopes) |
| **Revocation** | Eventual (24h) | Instant (<100ms) | Graceful (24h) |
| **Offline Support** | Yes (cached) | No | No |
| **Signature Check Cost** | Low (stateless) | Low (stateless) | Medium (DB cached 60s) |
| **Use Case** | Long-lived client | Sensitive ops | Integrations |

---

## Migration Path from Current System

1. **Phase 1 (Week 1)**: Deploy new admin token system in parallel
   - New login route issues both old (24h) and new (30m) tokens
   - Admin panel updated to use 30m token with revocation check
   - Old system still works (backward compat)

2. **Phase 2 (Week 2)**: Deploy mobile token system
   - Existing logins keep 24h tokens (no forced logout)
   - New logins issue 90-day tokens
   - Mobile app updated to handle long-lived tokens

3. **Phase 3 (Week 3)**: Deploy API key system
   - Existing JWT integrations still work (backward compat)
   - New integrations use API key system
   - Provide tool for integrations to self-rotate keys

4. **Phase 4 (Week 4)**: Sunset old system
   - Remove 24h token support
   - All clients now use optimized token type

## Response B
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
