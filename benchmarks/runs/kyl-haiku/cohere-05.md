## Discrepancies Found

I've systematically checked all three artifacts against the 10 coherence categories. Here are the **critical inconsistencies**:

### 🔴 **CRITICAL: Missing `role` Field**
- **Frontend queries:** `role` on User type
- **Schema defines:** No `role` field exists
- **Impact:** This query will fail at runtime with GraphQL validation error
- **Location:** Frontend component, line ~23 in the USER_PROFILE_QUERY

### 🔴 **CRITICAL: Avatar Field Mapping Broken**
- **Schema:** Defines `avatar: String` on User type
- **Resolver (createPost/updateUser):** Updates `profile_image` column, not `avatar`
- **No mapping resolver:** User type has no resolver to map `profile_image` → `avatar`
- **Impact:** Avatar will be `null` or undefined when queried, even though data exists in database
- **Location:** Resolver updateUser, line ~48; schema User type, line ~13

### 🔴 **HIGH: Comments Return Type Violation**
- **Schema:** `comments: [Comment!]!` — non-null list guarantee
- **Resolver:** `return comments.length > 0 ? comments : null` — returns `null`
- **Impact:** Violates GraphQL contract, breaks client type safety
- **Location:** Resolver Post.comments, line ~73

### 🟡 **MEDIUM: Inconsistent Avatar Naming Pattern**
- All other fields follow `camelCase (schema) ↔ snake_case (database)` pattern
- **Exception:** `avatar` ↔ `profile_image` — completely different names
- **Breaks:** Implicit field mapping conventions
- **Should be:** Both `avatar` or acknowledge the semantic difference

### 🟡 **MEDIUM: Misleading `feed` Query Name**
- **Name suggests:** A social feed (posts the user would see)
- **Actually returns:** Only posts authored by that userId
- **Correct name:** `userPosts` (reflects actual semantics)
- **Note:** Frontend uses it correctly, but the API contract is imprecisely named

---

## Quick Fixes Needed

1. **Remove `role` from frontend query** OR **add `role: String` to User schema**
2. **Add User field resolver** to map `profile_image` → `avatar`
3. **Fix Post.comments** to return `[]` instead of `null`
4. **Rename `feed`** to `userPosts` or change resolver to return actual social feed
5. **Standardize avatar column** name (use `avatar` consistently)