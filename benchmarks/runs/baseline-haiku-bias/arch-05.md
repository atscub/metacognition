I'll design a **differentiated authentication system** where the architecture is optimized per client type, not unified. The key insight is that the tech lead and security engineer are both right—but they're solving for different clients.

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    CloudDash Auth System                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Mobile          │  Admin Panel      │  Integrations       │
│  ─────────────   │  ─────────────    │  ──────────────     │
│  Long-lived      │  Revocable        │  Stateless          │
│  Offline-first   │  Server-session   │  API Key + JWT      │
│  Hybrid tokens   │  Short-lived      │  Scoped permissions │
│                  │                    │                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 1️⃣ Mobile App: Hybrid Token System (JWT + Session Cache)

**Problem this solves:** 24-hour forced logout during incidents; offline access.

### Token Format
```python
# Access token (JWT) — short-lived, offline-friendly
{
    'iss': 'clouddash',
    'sub': 'user_12345',
    'aud': 'mobile',
    'exp': unix_time + 15_minutes,
    'iat': unix_time,
    'device_id': 'device_abc123',  # Bind to device
    'session_version': 42,           # Revocation via version bump (explained below)
}

# Refresh token (opaque, server-side) — long-lived
{
    'type': 'refresh',
    'user_id': 'user_12345',
    'device_id': 'device_abc123',
    'issued_at': unix_time,
    'expires_at': unix_time + 30_days,
    'session_version': 42,
}
```

### Storage & Revocation
```python
# Redis (primary), backed by Postgres for durability
mobile_sessions:{device_id} = {
    'user_id': 'user_12345',
    'session_version': 42,
    'created_at': unix_time,
    'last_activity': unix_time,
    'refresh_token_hash': 'sha256(...)',
    'ttl': 30_days,  # Auto-evict after 30 days
}

# Session version is the revocation lever:
# - Increment on logout, password change, or admin revoke
# - Old JWTs with session_version=41 are rejected instantly
# - No token introspection needed—version is in JWT payload
```

### Flow
```
1. User logs in from mobile
   → POST /auth/login (username, password, device_id)
   → Issue 15-min JWT (session_version=42) + 30-day refresh token
   → Store refresh token in Redis

2. Access token expires
   → Use refresh token to get new JWT
   → Check: device_id matches? session_version == 42? Last activity < 30 days?
   → If session_version was incremented → reject, force re-login

3. User goes offline
   → JWT is still valid for 15 minutes after last sync
   → API calls cached locally; sync when reconnected
   → No round-trip to auth server needed

4. Admin needs to revoke this device
   → UPDATE mobile_sessions SET session_version = 43
   → Next refresh token attempt fails (version mismatch)
   → Next JWT use fails (version mismatch)
   → Takes <100ms to fully revoke
```

### Key Properties
- **Offline capability:** 15-min JWT is valid locally without network
- **Long sessions:** 30-day refresh token keeps user logged in weeks
- **Instant revocation:** Version bump revokes all tokens of a session instantly
- **Scalable:** Auth server doesn't need to check every request; JWT has version built in

---

## 2️⃣ Admin Panel: Server-Side Sessions (Stateful)

**Problem this solves:** Compliance requirement for 5-second revocation; sensitive operations.

### Session Format
```python
# Server-side session in Postgres + Redis cache
admin_sessions:{session_id} = {
    'user_id': 'admin_50001',
    'issued_at': unix_time,
    'last_activity': unix_time,
    'ip_address': '203.0.113.1',
    'user_agent': 'Mozilla/5.0...',
    'mfa_verified': True,
    'permissions': ['delete_users', 'view_audit_logs', 'manage_billing'],
    'expiry': unix_time + 30_minutes,  # Inactivity timeout
}

# Browser receives opaque session cookie
Set-Cookie: __admin_session=abc123def456; HttpOnly; Secure; SameSite=Strict; Max-Age=1800
```

### Flow
```
1. Admin logs in
   → POST /admin/login (username, password, MFA code)
   → Verify MFA
   → Create session in Postgres + Redis
   → Issue HttpOnly cookie (cannot be accessed by JavaScript)

2. Admin performs sensitive operation (e.g., delete user)
   → GET /admin/users/user_xyz/delete
   → Middleware checks: session_id in Redis? Last activity < 30 min? IP unchanged?
   → Log action: (user_50001, action_type='delete_user', user_xyz, timestamp)
   → Execute if authorized

3. Security event detected (e.g., compromised password)
   → Security team clicks "Revoke All Sessions" for admin_50001
   → DELETE FROM admin_sessions WHERE user_id = 'admin_50001'
   → Redis eviction propagates in <1 second
   → Next admin request → session_id not found → force re-login
   → ✅ Compliant with 5-second revocation requirement

4. Inactivity timeout
   → Cron job: DELETE FROM admin_sessions WHERE last_activity < now() - 30 minutes
   → Alternatively: check expiry on every request
```

### Key Properties
- **Instant revocation:** Delete from Postgres/Redis, immediately takes effect
- **Audit trail:** Every admin action logged with session context
- **IP pinning:** Can detect and flag cross-geo logins
- **Inactivity timeout:** 30 minutes, with refresh on activity
- **MFA-verified:** Admin must re-verify MFA for sensitive ops

---

## 3️⃣ Third-Party Integrations: API Keys + Scoped JWT

**Problem this solves:** Stateless scalability; no broken pipelines at 3 AM; rotation without downtime.

### Key Format
```python
# API key (stored by partner, shown once at creation)
sk_live_aAbBcCdDeEfFgGhHiIjJkKlMmNnOoPpQqRrSsTtUuVvWwXxYyZz

# In our Postgres:
api_keys:{api_key_hash} = {
    'partner_id': 'partner_cloudci',
    'key_id': 'key_5003',
    'name': 'CloudCI Production Deployment',
    'scopes': ['infra:read', 'infra:deploy', 'runs:write'],
    'created_at': unix_time,
    'last_rotated': unix_time,
    'rate_limit_qps': 500,
    'status': 'active',  # 'active' or 'revoked'
}

# JWT issued at request time (short-lived bearer token)
POST /api/v1/auth/issue-token
Authorization: ApiKey sk_live_...
→ Returns:
{
    'iss': 'clouddash',
    'sub': 'partner_cloudci:key_5003',
    'aud': 'api',
    'exp': unix_time + 5_minutes,
    'iat': unix_time,
    'scopes': ['infra:read', 'infra:deploy', 'runs:write'],
    'rate_limit_qps': 500,
}
```

### Flow
```
1. Partner implements token exchange in their deployment script
   POST /api/v1/auth/issue-token
   Headers: Authorization: ApiKey sk_live_...
   → Returns JWT valid for 5 minutes
   → Partner caches JWT for duration

2. Partner makes API calls
   Authorization: Bearer eyJhbGc...
   → Middleware verifies JWT (stateless check)
   → Enforces scopes: can they call DELETE /infra/12345?
   → Rate limiting: have they exceeded 500 qps?
   → Request proceeds or returns 429

3. Partner rotates key (e.g., quarterly, or emergency)
   POST /api/v1/keys/key_5003/rotate
   → Create new key with status='pending_active'
   → Partner updates CI config with new key (dual-run or blue-green)
   → Once confirmed working: update old key status='revoked'
   → No downtime: old JWTs still work until expiry (5 min grace period)

4. Emergency key revocation (compromised)
   POST /api/v1/keys/key_5003/revoke
   → Set status='revoked'
   → Check in Redis: 'revoked_keys:key_5003' = True
   → Next token exchange request → rejected immediately
   → Next API call with old JWT → rejected when we verify 'key_5003' is revoked
```

### Key Properties
- **Stateless:** JWT is self-contained, no session lookup
- **Scalable:** API servers can verify JWTs without consulting auth service
- **Scoped permissions:** Can grant minimal permissions per key
- **Rotation without downtime:** Dual-key period allows migration
- **Rate limiting:** Built into JWT payload, enforced at API gateway

---

## 📊 Comparison: How Each System Addresses the Problems

| Problem | Mobile | Admin | Integration |
|---------|--------|-------|-------------|
| **24-hr forced logout** | ✅ 30-day refresh tokens | N/A | ✅ No expiry on API keys |
| **5-sec revocation** | ✅ Session version (100ms) | ✅ Delete session (1s) | ✅ Redis revoked keys (50ms) |
| **Offline access** | ✅ 15-min JWT valid offline | ❌ (not applicable) | ❌ (not applicable) |
| **Pipeline at 3 AM** | N/A | N/A | ✅ 5-min JWT buffer + no hard expiry on key |
| **Scalability** | ✅ (mostly stateless) | ⚠️ (stateful, but 200 users) | ✅ (fully stateless) |
| **Audit trail** | ⚠️ (device-level logging) | ✅ (every action) | ✅ (every API call) |

---

## 🔐 Implementation Details

### Revocation Strategy Summary
```python
# Mobile: Session version in JWT (checked at refresh token exchange)
# Admin: Delete from Postgres + Redis (checked at every request)
# Integration: Redis blacklist for compromised keys (checked at token exchange)

# Common layer: All three can coexist
def authenticate(request):
    auth_header = request.headers.get('Authorization', '')
    
    if auth_header.startswith('Bearer '):
        token = auth_header.replace('Bearer ', '')
        payload = jwt.decode(token, PUBLIC_KEY)
        
        if payload['aud'] == 'mobile':
            # Mobile JWT: check session_version
            session = redis.get(f"mobile_sessions:{payload['device_id']}")
            if session['session_version'] != payload['session_version']:
                raise Unauthorized("Session revoked")
            return User.from_mobile_jwt(payload)
        
        elif payload['aud'] == 'api':
            # Integration JWT: check if key is revoked
            if redis.exists(f"revoked_keys:{payload['sub'].split(':')[1]}"):
                raise Unauthorized("API key revoked")
            return ServiceAccount.from_api_jwt(payload)
    
    elif 'admin_session' in request.cookies:
        session_id = request.cookies['admin_session']
        session = redis.get(f"admin_sessions:{session_id}")
        if not session or session['expiry'] < time.time():
            raise Unauthorized("Session expired")
        redis.expire(f"admin_sessions:{session_id}", 1800)  # Extend on activity
        return Admin.from_session(session)
    
    raise Unauthorized("No valid credentials")
```

### Database Schema
```sql
-- Mobile refresh tokens
CREATE TABLE mobile_sessions (
    device_id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    session_version INT DEFAULT 1,
    refresh_token_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP,
    last_activity TIMESTAMP,
    ttl_seconds INT DEFAULT 2592000,  -- 30 days
    INDEX (user_id)
);

-- Admin sessions
CREATE TABLE admin_sessions (
    session_id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    mfa_verified BOOLEAN,
    permissions JSON,
    created_at TIMESTAMP,
    last_activity TIMESTAMP,
    expiry TIMESTAMP,
    INDEX (user_id),
    INDEX (expiry)  -- For cleanup query
);

-- API keys
CREATE TABLE api_keys (
    key_id VARCHAR(255) PRIMARY KEY,
    partner_id VARCHAR(255) NOT NULL,
    key_hash VARCHAR(255) NOT NULL UNIQUE,
    scopes JSON,
    rate_limit_qps INT,
    status ENUM('active', 'revoked', 'pending_rotation'),
    created_at TIMESTAMP,
    last_rotated TIMESTAMP,
    rotated_to_key_id VARCHAR(255),  -- For rotation tracking
    INDEX (partner_id, status)
);

-- Audit log (for compliance)
CREATE TABLE audit_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    admin_session_id VARCHAR(255),
    action_type VARCHAR(255),
    resource_id VARCHAR(255),
    result ENUM('success', 'denied'),
    timestamp TIMESTAMP,
    details JSON,
    INDEX (admin_session_id),
    INDEX (timestamp)
);
```

---

## 🎯 Why This Resolves the Debate

**The tech lead was right:** JWTs scale better for stateless operations (integrations).  
**The security engineer was right:** Stateful sessions enable instant revocation (admin).  
**The solution:** Use both, with different semantics per client type.

- **Mobile**: Hybrid (JWT + session state) = long sessions + instant revocation via version
- **Admin**: Stateful sessions = no JWT escapes security policy + 5-sec revocation
- **Integration**: Stateless JWT = scales indefinitely + key rotation for revocation

---

## 🚀 Deployment Checklist

1. **Phase 1 (2 weeks):** Implement integration API key system; no breaking changes
2. **Phase 2 (1 month):** Migrate admin panel to server sessions; old JWT support deprecated
3. **Phase 3 (2 months):** Deploy mobile hybrid tokens; optional upgrade (backwards compatible)
4. **Phase 4:** Deprecate unified JWT approach; monitor for failures

Each phase can ship independently and be rolled back without affecting other clients.