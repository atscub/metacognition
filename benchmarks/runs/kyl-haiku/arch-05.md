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