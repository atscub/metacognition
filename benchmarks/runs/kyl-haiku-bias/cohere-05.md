I'll work through the coherence checklist systematically to identify discrepancies.

## Coherence Audit: GraphQL Schema, Resolvers, Frontend

### 1. **Factual Accuracy** — ❌ Critical Issues

**Issue #1: Undefined Field in Frontend Query**
- **Frontend** queries for `role` field on User:
  ```tsx
  user {
    ...
    role
    ...
  }
  ```
- **Schema** defines NO `role` field on User type
- **Impact**: Query will fail at runtime with "Cannot query field 'role' on type 'User'"

**Issue #2: Database Column Mismatch**
- **Schema** says User has `avatar: String`
- **Resolver** (User type) has NO custom resolver for `avatar` → expects raw `avatar` column from database
- **Mutation** (updateUser) writes to `profile_image` column, not `avatar`
- **Impact**: Unclear which column name is actually in the database. If it's `profile_image`, reading `avatar` fails.

**Issue #3: Non-Nullable Schema vs Nullable Resolver**
- **Schema** defines: `comments: [Comment!]!` (non-nullable array)
- **Resolver** (Post.comments) returns `null` if empty:
  ```javascript
  return comments.length > 0 ? comments : null;
  ```
- **Impact**: Violates schema contract. Should return `[]` for empty arrays.

---

### 2. **Category Accuracy** — ❌ Invalid Schema Declaration

The frontend component is asking for a field that doesn't exist. Either:
- The schema is incomplete (missing `role` field), or
- The frontend query is wrong (should not request `role`)

---

### 3. **Naming Coherence** — ⚠️ Ambiguous

Database column naming is inconsistent:
- `displayName` → `display_name` (mapped correctly in updateUser)
- `avatar` → `profile_image` (NOT mapped in updateUser, causing confusion)
- Should be consistently named throughout, or the mismatch should be explicit

---

## Summary of Discrepancies

| Issue | Severity | Location | Problem |
|-------|----------|----------|---------|
| `role` field undefined | **Critical** | Schema ↔ Frontend | Frontend queries field that doesn't exist in schema |
| `avatar` vs `profile_image` | **Critical** | Schema ↔ Resolvers | Column name mismatch; mutation writes to wrong column |
| `comments` nullability | **High** | Resolvers ↔ Schema | Resolver violates non-nullable array constraint |

---

## Required Fixes

1. **Add `role` field to User type in schema**, or **remove it from frontend query**
2. **Decide on avatar column name**: Either rename all `profile_image` → `avatar` or all `avatar` → `profile_image`, then update all references
3. **Change Post.comments resolver** to return `[]` instead of `null` for empty arrays