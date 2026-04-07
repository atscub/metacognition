# Consistency Review

Found **4 discrepancies** between the artifacts:

## 1. **Missing Schema Field: `user.role`** ⚠️ **Critical**
- **Frontend queries**: `user.role` in UserProfile component
- **Schema defines**: No `role` field in User type
- **Impact**: GraphQL will reject this query with "Cannot query field 'role' on type 'User'"
- **Fix**: Add `role: String` to User type in schema, or remove from frontend query

## 2. **Post.comments Nullability Violation** ⚠️ **Critical**
- **Schema defines**: `comments: [Comment!]!` (non-nullable list)
- **Resolver returns**: `null` when comments.length is 0
  ```javascript
  return comments.length > 0 ? comments : null;  // ← violates schema
  ```
- **Impact**: Breaks schema contract; should return empty array `[]` instead
- **Fix**: Change to `return comments || []`

## 3. **Feed Query Semantics Mismatch**
- **Schema intent**: Appears to be a generic "feed" query
- **Resolver implementation**: Returns posts WHERE `author_id: userId` (user's own posts only)
- **Frontend expectation**: Uses it to show "Recent Posts" from the user
- **Issue**: "Feed" typically means posts from followed users, not a user's own posts. Consider renaming to `userPosts` for clarity, or document the actual behavior

## 4. **Pagination Inconsistency**
- **users query**: Supports pagination with `limit` + `offset` and returns paginated `UserConnection`
- **feed query**: Accepts `limit` but no `offset` parameter (no pagination support)
- **Impact**: Frontend can only fetch the first N posts from a feed, can't get more without refetching
- **Fix**: Add `offset: Int = 0` parameter to feed query, or return a paginated type like `PostConnection`

---

**Priority fixes**: #1 and #2 will cause runtime errors. #3 and #4 are design consistency issues.