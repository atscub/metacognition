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