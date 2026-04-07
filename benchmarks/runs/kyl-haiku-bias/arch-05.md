## Working Through the Decomposition

Let me strip this to fundamentals and rebuild.

### Step 1: Restate Without Jargon

You have three groups accessing the same API in completely different ways:
- Phones that need to work for weeks without asking the user to log in again
- Admins who need to be kicked out instantly if there's a security emergency  
- Automated systems that make thousands of requests per hour with a token embedded in a config file

Right now everyone uses the same token type, which doesn't work for any of them properly. The debate is framed as "JWTs vs sessions," but that's a false binary—it's really asking: *which one thing should we use for all three groups?*

### Step 2: Atomic Components

**What must actually happen on every request?**
- Server: "Who is this?"
- Server: "Are they still allowed to be here?"

**Why is it hard?**
- Mobile + third-party: Can't round-trip to server on every request (too slow, offline, or too high volume)
- Admin: *Must* round-trip to check revocation status instantly
- These are **opposite constraints**.

### Step 3: Question the Binary

**"Do all three groups actually need the same token mechanism?"**

No. The false binary collapses if you stop assuming one answer.

**"What's the simplest thing for mobile?"** A self-contained proof of identity (JWT signature) that the phone can verify offline. Expiry: 7–30 days. No revocation check—users are revoked by logging out locally. This is proven and simple.

**"What's the simplest thing for admin?"** Server checks a revocation list on every request. Revocation is instant because it's checked synchronously. 200 users is negligible load.

**"What's the simplest thing for API keys?"** A lookup key (not a time-expiring token) in the database. No expiry mechanic. Rotation happens explicitly. Server does a fast lookup on every request—but 10K/hour is ~3 req/sec, which is nothing.

**"What if the current system is broken because it's trying to solve three different problems with one mechanism?"** That's the actual root cause.

---

## The Redesigned System

### Architecture: Three Parallel Token Types

| Client | Token Type | Validation | Revocation | Expiry | Why |
|--------|-----------|------------|-----------|--------|-----|
| **Mobile** | JWT (7 days) | Client-side signature check | Local logout only | 7 days | Stateless, offline-capable, no server roundtrip. Users don't get randomly logged out. |
| **Admin** | JWT (30 min) + revocation list | Server checks both on every request | Instant (list lookup) | 30 min | Short TTL + server-side validation handles the 5-second revocation requirement. |
| **API Keys** | Persistent secret (no JWT) | Server-side lookup + HMAC | Explicit key rotation | None (explicit) | No time-based expiry (prevents silent pipeline breaks). Rotation is intentional, not automatic. |

---

### Implementation Details

#### 1. Mobile JWT Flow

```python
# Issued at login
def mobile_login(username, password):
    user = verify_credentials(username, password)
    token = jwt.encode({
        'sub': user.id,
        'type': 'mobile',
        'roles': user.roles,
        'exp': datetime.utcnow() + timedelta(days=7),
    }, MOBILE_SECRET, algorithm='HS256')
    return {'access_token': token}

# Validated on client (offline, no server roundtrip)
# Client app verifies signature using MOBILE_SECRET_PUBLIC
# If invalid or expired, prompt user to login again

# Revocation: user taps "logout" → deletes token from device
```

**Why this works for mobile:**
- No server hit per request (stateless)
- Works offline
- 7-day expiry is long enough that users don't get booted during infrastructure incidents
- Local logout is instant for the user

---

#### 2. Admin JWT + Revocation List Flow

```python
# Issued at login
def admin_login(username, password):
    user = verify_admin(username, password)
    session_id = generate_session_id()
    
    # Store in Redis: {session_id: {user_id, login_time, ip}}
    redis.setex(
        f"admin_session:{session_id}",
        timedelta(minutes=30),
        json.dumps({
            'user_id': user.id,
            'login_time': time.time(),
            'ip': request.remote_addr,
        })
    )
    
    token = jwt.encode({
        'sid': session_id,  # Reference to server state
        'type': 'admin',
        'exp': datetime.utcnow() + timedelta(minutes=30),
    }, ADMIN_SECRET, algorithm='HS256')
    
    return {'access_token': token}

# Middleware on every admin request
def authenticate_admin(request):
    token = parse_bearer_token(request)
    try:
        payload = jwt.decode(token, ADMIN_SECRET, algorithms=['HS256'])
        session_id = payload['sid']
        
        # Server-side check: is this session still valid?
        session = redis.get(f"admin_session:{session_id}")
        if not session:
            raise Unauthorized("Session revoked or expired")
        
        session_data = json.loads(session)
        return AdminUser(id=session_data['user_id'])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        raise Unauthorized()

# Instant revocation (security event)
def revoke_admin_session(user_id):
    # Revoke all sessions for this user
    pattern = f"admin_session:*"
    for key in redis.scan_iter(match=pattern):
        session_data = json.loads(redis.get(key))
        if session_data['user_id'] == user_id:
            redis.delete(key)
    # Session is revoked. Next request will fail.
```

**Why this works for admin:**
- Token itself is small/fast (just a session ID reference)
- Server validates on every request (acceptable for 200 users)
- Revocation is instant—next request sees the deleted session
- 30-minute inactivity timeout is enforced (Redis TTL)
- Compliance requirement met: "revoke within 5 seconds" ✓

---

#### 3. API Key Flow

```python
# Create a persistent API key (not time-expiring)
def create_api_key(partner_id, scope):
    key_id = generate_key_id()  # e.g., "ck_live_abc123"
    key_secret = secrets.token_urlsafe(32)
    key_hash = sha256(key_secret).hexdigest()
    
    db.insert('api_keys', {
        'key_id': key_id,
        'key_hash': key_hash,
        'partner_id': partner_id,
        'scope': scope,
        'created_at': now(),
        'rotated_at': None,
        'revoked_at': None,  # NULL = active
    })
    
    # Return secret only once
    return {'key_id': key_id, 'key_secret': key_secret}

# Validation on every request (via API Gateway or middleware)
def authenticate_api_key(request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        raise Unauthorized()
    
    key_id, key_secret = parse_api_key(auth_header)
    
    # Fast lookup: {key_id -> hash}
    row = db.query(
        'SELECT key_hash, partner_id, scope, revoked_at '
        'FROM api_keys WHERE key_id = ?',
        [key_id]
    )
    
    if not row or row['revoked_at'] is not None:
        raise Unauthorized("Key not found or revoked")
    
    # Verify secret
    if sha256(key_secret).hexdigest() != row['key_hash']:
        raise Unauthorized("Invalid key")
    
    return APIClient(partner_id=row['partner_id'], scope=row['scope'])

# Rotation (new key, old key valid for 24h window)
def rotate_api_key(old_key_id):
    old_key = db.query('SELECT * FROM api_keys WHERE key_id = ?', [old_key_id])
    new_key_id = generate_key_id()
    new_key_secret = secrets.token_urlsafe(32)
    
    db.insert('api_keys', {
        'key_id': new_key_id,
        'key_hash': sha256(new_key_secret).hexdigest(),
        'partner_id': old_key['partner_id'],
        'scope': old_key['scope'],
        'created_at': now(),
        'rotated_at': None,
    })
    
    # Mark old key for deprecation (keep valid for 24h)
    db.update('api_keys', {'deprecated_at': now()}, where_id=old_key_id)
    
    return {'new_key_id': new_key_id, 'new_key_secret': new_key_secret}

# Explicit revocation (operator-initiated)
def revoke_api_key(key_id):
    db.update('api_keys', {'revoked_at': now()}, where_id=key_id)
```

**Why this works for API keys:**
- No time-based expiry (won't silently break at 3 AM)
- Rotation is explicit and non-disruptive (old key stays valid during transition)
- Revocation is explicit and immediate
- Scope is enforced per-key (better than roles embedded in tokens)

---

### Request Flow Diagram

```
Mobile Request            Admin Request           API Key Request
    ↓                         ↓                           ↓
Has JWT?              Has JWT + session?        Has key_id + secret?
    ↓                         ↓                           ↓
Verify                  ✓ Check JWT sig              ✓ Look up key
signature              ✓ Check Redis               ✓ Hash secret
locally                  session exists            ✓ Compare hash
    ↓                         ↓                           ↓
Valid?                 Valid?                      Valid?
↓ Yes: Pass        ↓ Yes: Pass               ↓ Yes: Pass
↓ No: Deny         ↓ No: Deny               ↓ No: Deny
```

---

### Why This Solves All the Problems

| Problem | Solution |
|---------|----------|
| Admin compromise took 24h to revoke | Admin JWT validated against live Redis session; revocation is instant |
| Mobile users logged out after 24h during incidents | Mobile JWT is 7 days; can work offline |
| Third-party pipelines break at 3 AM | API keys don't expire; rotation is explicit |
| Can't apply different policies to different clients | Each client type has its own token format and validation logic |
| High request volume | Mobile uses stateless JWTs (no server hit). Admin/API have acceptable overhead for their user counts. |

---

### Trade-Offs

| Aspect | Cost | Why Worth It |
|--------|------|-------------|
| Mobile tokens are longer-lived | Slightly more window if credentials compromised | User stays logged in during critical incidents; this is a business requirement |
| Admin requires Redis lookup on every request | Small server overhead (200 users, ~10ms per query) | Enables 5-second revocation; compliance-critical |
| Three separate code paths | More to maintain | Each path is simpler and better-suited to its use case than one universal path |
| API key management is manual | Operators must explicitly rotate/revoke | Prevents silent outages; gives partners predictability |

---

### Implementation Checklist

1. **Mobile:** Publish `MOBILE_SECRET_PUBLIC` in your app. Client verifies signatures locally.
2. **Admin:** Set up Redis for session storage. Middleware checks both JWT and session.
3. **API Keys:** Database table with `(key_id, key_hash, scope, revoked_at)`. Lookup on every request.
4. **Logging:** Log failed auth attempts, successful revocations, rotations.
5. **Monitoring:** Alert if admin revocation latency exceeds 1 second or API key lookups timeout.

---

### Why the Original Debate Was a False Binary

**Tech lead:** "JWTs scale better, just shorten the TTL."
- Shorter TTL doesn't help admin revocation (still have to wait for expiry). And it breaks mobile (users get logged out).

**Security engineer:** "Servers-side sessions are the only way to revoke."
- Correct for admin. Wrong for mobile and API keys, where statefulness adds load without benefit.

**The real answer:** Use the right tool for each use case. JWTs are great for mobile. Server-side sessions are necessary for admin. API keys are right for third-party. They're not competing solutions—they're complementary.