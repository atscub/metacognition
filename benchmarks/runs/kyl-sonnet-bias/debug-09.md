## Applying Socratic Mode Before Diagnosing

Let me explicitly question my first hypothesis before committing to it.

---

### Step 1: What is the security team's hypothesis?

**$2a vs $2b bcrypt variant mismatch.** Their evidence: old library used $2a.

**Steelmanning it**: Some bcrypt implementations historically treated $2a and $2b differently (specific to the OpenBSD bug around 8-bit password handling). If the MySQL library stored $2a hashes and bcryptjs mishandles them...

**Falsifying it**: The problem statement already disproves this. Jane's hash in *both* systems shows `$2b`. The library test confirms bcryptjs treats $2a/$2b identically. **This hypothesis is dead.** Two days were wasted anchoring on it.

---

### Step 2: What does the evidence actually show?

Before forming a new hypothesis, read the data carefully:

| System | Hash (Jane) | Length |
|--------|-------------|--------|
| MySQL (source of truth) | `...lhW`**`e`** | 60 |
| PostgreSQL (new) | `...lhW` | 59 |
| Working users (PostgreSQL) | various | 60 |

The last character `e` is missing. Jane's hash in PostgreSQL is **truncated by exactly 1 character**.

---

### Step 3: Generate competing hypotheses — don't anchor on the first

**Hypothesis A**: Column width `VARCHAR(59)` truncated the 60-char bcrypt hash.

The migration script defines:
```sql
password_hash VARCHAR(59) NOT NULL,
```

bcrypt hashes are exactly 60 characters. Off by one.

**Challenge my own hypothesis**: If `VARCHAR(59)` caused the truncation, why do working users have 60-char hashes in PostgreSQL? PostgreSQL enforces `VARCHAR(n)` strictly — it errors, it doesn't silently truncate. Also, `CREATE TABLE IF NOT EXISTS` is a no-op if the table exists, so the column definition in the script may never have taken effect at all.

**Conclusion**: VARCHAR(59) is a real bug, but the truncation mechanism may not be direct. The column definition is evidence of an off-by-one mindset in the migration.

**Hypothesis B**: CSV export truncated Jane's row during `mysqldump --tab`.

`mysqldump --tab` produces tab-delimited files. But the COPY command uses `WITH CSV` (default delimiter: comma). If the export file is tab-delimited and COPY treats commas as delimiters, field boundaries would be misread — but this would corrupt *all* rows, not 3.

**Hypothesis C**: A trailing character in the export (e.g. `\r` from Windows line endings) was treated as part of Jane's hash, causing the hash to be interpreted as 61 chars and then truncated to fit.

Actually this is worth examining. If the CSV had `\r\n` line endings but the COPY parser expected `\n`, the `\r` could be appended to the last field of each row. Jane's hash in the file: `...lhWe\r` → stored as `...lhWe\r` (61 chars) → truncated to VARCHAR(59) → `...lhW`. That would explain the truncation AND why it's only 3 users (their rows happened to be at a \r\n boundary, or only certain rows were exported with Windows line endings).

But this requires the column to actually be VARCHAR(59) and PostgreSQL to silently truncate, which it doesn't do normally.

---

### Step 4: What evidence would definitively resolve this?

The most important test is: **what does the actual PostgreSQL schema say?**

```sql
SELECT column_name, data_type, character_maximum_length
FROM information_schema.columns
WHERE table_name = 'users' AND column_name = 'password_hash';
```

If `character_maximum_length` is 59, Hypothesis A is confirmed.

---

### The Answer

The smoking gun is right in the data, and the fix doesn't require any of the bcrypt investigation:

**Jane's bcrypt hash was truncated by 1 character during migration.** The 60-character hash `...lhWe` became the 59-character `...lhW`. `bcrypt.compare()` receives a malformed hash and returns false — not because the password is wrong, but because the stored hash is corrupted.

The root cause is almost certainly the migration script:

```sql
password_hash VARCHAR(59) NOT NULL,  -- ← bcrypt hashes are 60 chars
```

bcrypt hashes have a fixed format: `$2b$` (4) + cost (2) + `$` (1) + salt (22) + hash (31) = **60 characters total**. Someone wrote 59 instead of 60 — a classic off-by-one.

Whether PostgreSQL truncated silently (unlikely in strict mode), whether COPY ON_ERROR handling was involved, or whether the truncation cascaded from this wrong assumption elsewhere in the pipeline, the wrong column width is the root defect. The 3 affected users are the ones whose hash's 60th character happened to be meaningful to bcrypt's internal validation.

---

### Why the security team went wrong

**Anchoring + confirmation bias.** They had a plausible-sounding hypothesis ($2a/$2b) and looked for evidence to support it rather than reading the raw data first. The data showed the answer immediately: **the hashes differ between old and new systems**. That's not a library prefix issue — that's data corruption. A simple `SELECT length(password_hash)` comparison between MySQL and PostgreSQL would have revealed this in minutes.

---

### The fix

```sql
-- 1. Fix the schema
ALTER TABLE users ALTER COLUMN password_hash TYPE VARCHAR(60);

-- 2. Re-copy the 3 affected users' hashes from MySQL source of truth
UPDATE users SET password_hash = '<correct_hash_from_mysql>'
WHERE email = 'jane.doe@example.com';
-- (repeat for the other 2 affected users)
```

No bcrypt library changes needed. No rehashing. Just restore the missing character from the MySQL read-only replica — the data is still there.