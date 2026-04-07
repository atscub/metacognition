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