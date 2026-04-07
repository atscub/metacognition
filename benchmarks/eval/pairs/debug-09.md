# Task: debug-09 — One user cannot log in after database migration

## Prompt
We recently migrated our user database from MySQL to PostgreSQL. Everything went
smoothly — 50,000+ users migrated, all verified. But one user, `jane.doe@example.com`,
reports she can't log in. She's entering the correct password (confirmed via password
reset flow on the old system which is still running read-only). Her account exists in
the new database. The security team suspects a bcrypt algorithm mismatch ($2a vs $2b)
since MySQL used an older bcrypt library.

Migration script (scripts/migrate-users.sql):

```sql
-- Migration: MySQL → PostgreSQL
-- Run via: psql -f migrate-users.sql target_db

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(59) NOT NULL,
    display_name VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT true
);

-- Import from MySQL dump (generated via mysqldump --tab)
-- Data loaded via: COPY users FROM '/tmp/mysql_export/users.csv' WITH CSV HEADER;
```

Authentication code (src/auth/login.ts):

```typescript
import bcrypt from 'bcryptjs';
import { db } from '../database';

export async function authenticateUser(email: string, password: string) {
  const result = await db.query(
    'SELECT id, email, password_hash, is_active FROM users WHERE email = $1',
    [email.toLowerCase()]
  );

  if (result.rows.length === 0) {
    throw new AuthError('Invalid credentials');
  }

  const user = result.rows[0];

  if (!user.is_active) {
    throw new AuthError('Account disabled');
  }

  const isValid = await bcrypt.compare(password, user.password_hash);

  if (!isValid) {
    throw new AuthError('Invalid credentials');
  }

  return { id: user.id, email: user.email };
}
```

Jane's record in the NEW PostgreSQL database:

```sql
SELECT email, password_hash, length(password_hash) as hash_len, is_active
FROM users WHERE email = 'jane.doe@example.com';

 email                  | password_hash                                               | hash_len | is_active
------------------------+-------------------------------------------------------------+----------+-----------
 jane.doe@example.com   | $2b$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhW | 59       | t
```

A few other users for comparison (all can log in fine):

```sql
SELECT email, password_hash, length(password_hash) as hash_len
FROM users WHERE email IN ('john.smith@example.com', 'alice.wong@example.com', 'bob.jones@example.com');

 email                  | password_hash                                                | hash_len
------------------------+--------------------------------------------------------------+----------
 john.smith@example.com | $2b$10$YR2.VFKdGMAqEJL5L4Of3uH5dCxT2fW.yeaYGDLwFo8k4K3fgDCC | 60
 alice.wong@example.com | $2b$10$WApznUPhDubN0.MXpBj3Ceq0TSwSLqEFrFkNP8vR1JzFH/x1dL0F | 60
 bob.jones@example.com  | $2b$10$H5bR3kEq1JzFLqWpN9X.X.TY3FkNP8vR1JzFH/1dL0FqWpN9X.Xe | 60
```

Verification on the OLD MySQL system (still running read-only):

```sql
SELECT email, password_hash, LENGTH(password_hash) as hash_len
FROM users WHERE email = 'jane.doe@example.com';

+------------------------+--------------------------------------------------------------+----------+
| email                  | password_hash                                                | hash_len |
+------------------------+--------------------------------------------------------------+----------+
| jane.doe@example.com   | $2b$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWe | 60       |
+------------------------+--------------------------------------------------------------+----------+
```

bcrypt library investigation by the security team:

```
$ node -e "const bcrypt = require('bcryptjs');
console.log('$2a support:', bcrypt.compareSync('test', '\$2a\$10\$abcdef...'));
console.log('$2b support:', bcrypt.compareSync('test', '\$2b\$10\$abcdef...'));"

# bcryptjs supports both $2a and $2b prefixes — they are treated identically.
# The library normalizes $2a to $2b internally.
```

The team also verified:
- Jane's email matches exactly (no case issues, no whitespace)
- Her `is_active` flag is `true`
- She's using the correct password (verified on old system)
- The bcryptjs library handles both `$2a` and `$2b` hashes correctly
- 49,997 other users can log in fine, only 3 users reported issues

The security team is now investigating whether the MySQL bcrypt library used a
non-standard salt encoding that PostgreSQL's bcrypt can't parse. They've spent
two days on this.

What's the actual problem?


## Response A
## Applying Epistemic Humility Before Diagnosing

**Before accepting the security team's theory, let me actively try to disconfirm it.**

---

### The Security Team's Hypothesis: $2a/$2b Mismatch

**Steelmanning it:** Older MySQL bcrypt libraries often used `$2a`, and `$2b` was introduced to fix a bug in the OpenBSD implementation. Some libraries are strict about prefix compatibility.

**Disconfirming evidence already in the case file:** The team's own test shows bcryptjs treats `$2a` and `$2b` identically. Jane's hash already has a `$2b` prefix anyway. This hypothesis is **already ruled out by the provided evidence**. The team spent two days chasing a ghost.

**Bias at work:** They anchored on a migration-plausible explanation and then stopped looking. Classic premature closure.

---

### What Does the Evidence Actually Show?

Let me apply the checklist: *What am I assuming? What evidence do I actually have?*

**Direct comparison of the hashes (observation, not inference):**

| System | Hash | Length |
|--------|------|--------|
| MySQL (source of truth) | `...L17lhW`**`e`** | **60** |
| PostgreSQL (new) | `...L17lhW` | **59** |
| john.smith (PostgreSQL, works) | `...fgDCC` | **60** |
| alice.wong (PostgreSQL, works) | `...dL0F` | **60** |
| bob.jones (PostgreSQL, works) | `...Xe` | **60** |

The final character `e` is **missing from Jane's PostgreSQL record**. Every working user has a 60-character hash. Jane has a 59-character hash.

**Assumption check:** Am I pattern-matching "migration = encoding issue"? Yes. Is there a simpler explanation visible in the raw data? Also yes — the hash is just shorter.

---

### The Actual Problem

Jane's bcrypt hash was **truncated by one character during migration**. Her PostgreSQL record stores `...L17lhW` (59 chars) when the correct hash is `...L17lhWe` (60 chars).

`bcrypt.compare()` does a full string comparison of the recomputed hash against the stored hash. A 59-character stored hash will **never match** a correctly computed 60-character hash, no matter how correct the password.

---

### Root Cause: The Schema

Look at the migration script:

```sql
password_hash VARCHAR(59) NOT NULL,
```

**Standard bcrypt hashes are exactly 60 characters.** The column is one character too narrow.

**"But why do 49,997 other users work?"** — this is the check that would disprove my theory. Two possibilities:

1. PostgreSQL doesn't silently truncate VARCHARs — it errors. So the column width constraint may have been caught and corrected *after* some rows were already loaded, leaving Jane's row (and 2 others) permanently truncated with no re-import.
2. The column was later `ALTER TABLE`'d to `VARCHAR(60)` or wider, but the already-corrupted rows weren't re-migrated.

Either way, the `VARCHAR(59)` definition is a landmine for exactly 60-char values.

---

### The Fix

**Immediate:** Copy Jane's correct hash from MySQL and patch the PostgreSQL row:

```sql
UPDATE users
SET password_hash = '$2b$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWe'
WHERE email = 'jane.doe@example.com';
```

**Systemic:** Find all other affected users (the other 2 reporters, and likely more who haven't complained):

```sql
-- Truncated bcrypt hashes are exactly 59 chars; valid ones are 60
SELECT email, length(password_hash)
FROM users
WHERE length(password_hash) != 60 AND password_hash LIKE '$2%';
```

Re-import those rows from MySQL, or prompt affected users to reset passwords.

**Schema fix:**

```sql
ALTER TABLE users ALTER COLUMN password_hash TYPE VARCHAR(60);
```

---

### Why the Team Missed It

| Their focus | Why it failed |
|-------------|---------------|
| `$2a` vs `$2b` prefix | Already ruled out by their own test; they didn't stop |
| Library normalization | Correct analysis, wrong problem |
| Salt encoding | Plausible-sounding, zero evidence |

They never compared the **raw hash values** side-by-side between MySQL and PostgreSQL. The answer was in the `hash_len` column the whole time — it's right there in the query output they presumably ran.

## Response B
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
