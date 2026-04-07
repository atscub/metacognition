## The Problem: Off-by-one in the column definition

The security team is chasing the wrong lead. The bcrypt algorithm prefix is irrelevant. Look at the data:

| System | Hash | Length |
|---|---|---|
| MySQL (source of truth) | `...LJZdL17lhW`**e** | 60 |
| PostgreSQL (broken) | `...LJZdL17lhW` | 59 |

Jane's hash was **truncated by exactly one character** during migration. The last character `e` is gone.

The culprit is in the migration script:

```sql
password_hash VARCHAR(59) NOT NULL,  -- ← BUG: should be VARCHAR(60)
```

A standard bcrypt hash is always exactly **60 characters**:
- `$2b$` (4) + `10` (2) + `$` (1) + 22-char salt + 31-char hash = **60**

The column is one character too short. Jane's hash was silently truncated during the `COPY FROM CSV` import, producing an invalid hash that will never match any password.

The other users' hashes show as 60 characters, which tells you the column was likely altered to `VARCHAR(60)` or larger after the initial migration — but Jane's row was already written with the truncated value and never corrected.

## Fix

Two steps:

**1. Correct the schema (if not already fixed):**
```sql
ALTER TABLE users ALTER COLUMN password_hash TYPE VARCHAR(60);
```

**2. Restore Jane's hash from MySQL:**
```sql
UPDATE users
SET password_hash = '$2b$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWe'
WHERE email = 'jane.doe@example.com';
```

Also check how many other users are affected — anyone whose original MySQL hash was exactly 60 chars and whose PostgreSQL record now shows 59 chars. Given "3 users reported issues," there are likely 2 more in the same situation.

```sql
SELECT email FROM users WHERE length(password_hash) = 59;
```