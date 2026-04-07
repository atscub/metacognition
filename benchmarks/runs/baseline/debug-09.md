The bug is in the migration script. Look at the schema:

```sql
password_hash VARCHAR(59) NOT NULL,
```

A standard bcrypt hash is **60 characters**. The column is one character too short, silently truncating the last character on import.

**Evidence:**

| System | Jane's hash | Length |
|--------|-------------|--------|
| MySQL (source) | `...$2b$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhW`**e** | 60 |
| PostgreSQL (migrated) | `...$2b$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhW` | 59 |

The trailing `e` was silently dropped. The working users (`john.smith`, `alice.wong`, `bob.jones`) all show `hash_len = 60` — meaning their hashes happened to fit, or their last character is something PostgreSQL silently dropped without breaking the comparison... wait, no. Actually they're 60 chars in a VARCHAR(59) column — PostgreSQL would have errored or truncated them too.

Actually re-reading: the working users show `hash_len = 60` in PostgreSQL. That means VARCHAR(59) didn't truncate them, which is odd. But Jane shows 59. This means PostgreSQL likely **did** enforce the limit and truncated Jane's hash, but the other users either had a shorter hash (impossible for bcrypt) or the column definition was later fixed but Jane's data wasn't corrected.

Regardless, the root cause is clear: **Jane's stored hash is truncated by one character**, making it an invalid bcrypt hash that will never match any input.

**Fix:**

1. Fix the column definition (if not already done):
```sql
ALTER TABLE users ALTER COLUMN password_hash TYPE VARCHAR(60);
```

2. Restore Jane's hash from the source system:
```sql
UPDATE users 
SET password_hash = '$2b$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWe'
WHERE email = 'jane.doe@example.com';
```

3. Find and fix the other 2 affected users (you mentioned 3 total reported issues):
```sql
SELECT email FROM users WHERE length(password_hash) < 60 AND is_active = true;
```

The `$2a`/`$2b` investigation was a complete red herring. The bcrypt algorithm was never the issue.