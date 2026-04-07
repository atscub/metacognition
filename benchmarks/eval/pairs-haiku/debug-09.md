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
Now let me work through this with actual scrutiny:

## What I'm Assuming

1. The bcrypt mismatch theory is correct
2. The CSV import worked correctly  
3. Hash length is irrelevant
4. The security team's focus on library differences is the right direction

## What Evidence I Actually Have

Let me look at the **hash lengths** more carefully—this is something I can verify directly from the data you provided:

**Jane in MySQL (working):**
```
$2b$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWe
Length: 60 characters ✓
```

**Jane in PostgreSQL (broken):**
```
$2b$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhW
Length: 59 characters ✗
```

**Other users in PostgreSQL:**
```
All 60 characters ✓
```

The PostgreSQL hash is **missing the final character 'e'**.

A valid bcrypt hash must be exactly 60 characters:
- `$2a$` or `$2b$` = 4 chars
- Cost factor `10$` = 3 chars  
- Salt (22 chars) + Hash (31 chars) = 53 chars
- **Total: 60 characters exactly**

---

## The Actual Problem

**Jane's hash was truncated during the CSV migration.** The final character was lost—likely when the MySQL dump was exported or when PostgreSQL imported it.

When bcryptjs tries to validate her password against a 59-character incomplete hash, it fails because the hash is corrupted. **This has nothing to do with `$2a` vs `$2b`.** The library would reject an incomplete hash regardless of the prefix.

The other 49,997 users' hashes are intact (60 chars), which is why they work. The 3 users with issues probably had the same truncation during CSV parsing.

---

## Root Cause

**CSV export/import data corruption:**

The `mysqldump --tab` export likely didn't properly quote or escape the hash values, OR the `COPY FROM CSV` import in PostgreSQL doesn't handle the exact formatting from MySQL's tab-separated export. Common failure modes:
- Quote/escape mismatch between MySQL and PostgreSQL CSV formats
- Trailing whitespace or special characters in the CSV that truncated the hash
- Character set encoding issues during export

---

## Verification

To confirm:
1. Compare the exact byte-for-byte difference between MySQL and PostgreSQL for Jane's hash (the 'e' at the end)
2. Check if the other 2 failing users also have 59-character hashes
3. If yes, all three hashes were truncated identically during migration—clear sign of a CSV parsing issue

---

## Fix

**Re-export the correct hashes from MySQL and update PostgreSQL:**

```sql
-- On PostgreSQL, update Jane's hash to the complete 60-char version from MySQL
UPDATE users 
SET password_hash = '$2b$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWe'
WHERE email = 'jane.doe@example.com';
```

Do the same for the other 2 failing users.

**Don't re-run the full migration** — just fix the corrupted hashes individually.

## Response B
The actual problem is much simpler than a bcrypt algorithm mismatch: **Jane's password hash was truncated by one character during the migration.**

Look at the hash lengths:

- **Jane in PostgreSQL**: 59 characters: `$2b$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhW`
- **Jane in MySQL**: 60 characters: `$2b$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWe`
- **Other users in PostgreSQL**: 60 characters (all valid)

A valid bcrypt hash is **always exactly 60 characters**. Jane's hash is missing the last character (`e`), making it invalid. When bcryptjs tries to validate against a 59-character hash, it fails with "Invalid credentials."

The root cause: The CSV export/import process corrupted the data for Jane (and the other 2 affected users). This could be due to:
1. **Improper CSV quoting** — if Jane's hash contained a character that looked like a delimiter to the import parser
2. **Trailing character handling** — the COPY command may have stripped the last character incorrectly
3. **Encoding/escaping issues** during the `mysqldump --tab` export

**The fix:**

Re-export Jane's password hash from the MySQL system (still running read-only) with proper escaping:

```sql
-- On PostgreSQL, update Jane's hash with the correct 60-char version:
UPDATE users 
SET password_hash = '$2b$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWe'
WHERE email = 'jane.doe@example.com';
```

Do the same for the other 2 affected users.

**Why the security team was confused**: They were looking for algorithmic differences (`$2a` vs `$2b`) when the issue was simply **corrupted data**—a truncated hash. This wouldn't show up in any bcrypt library tests, only in actual login attempts.

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
