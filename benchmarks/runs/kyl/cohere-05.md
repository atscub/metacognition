## Coherence Audit: GraphQL Schema, Resolvers, Frontend Component

Working through all 10 categories, comparing each artifact against the other two.

---

### 1. Factual Accuracy — 3 findings

**Finding A (High): `role` field queried but not defined**

The frontend queries `role` on `User`:
```graphql
# UserProfile.tsx
user { ..., role, ... }
```
The schema has no `role` field on `User`. This query will fail or return `null`/error at runtime. The component also conditionally renders a `<span className="role-badge">` on it — dead UI.

---

**Finding B (High): `Post.comments` nullability violation**

Schema declares comments as non-nullable list with non-nullable items:
```graphql
comments: [Comment!]!   # can never be null; always returns a list
```
Resolver returns `null` when there are no comments:
```javascript
return comments.length > 0 ? comments : null;  // violates [Comment!]!
```
Should return `[]`. This will cause a GraphQL runtime error for any post with zero comments.

---

**Finding C (High): `avatar` / `profile_image` column mismatch**

`updateUser` writes `input.avatar` to the DB column `profile_image`:
```javascript
.update({ display_name: input.displayName, bio: input.bio, profile_image: input.avatar })
```
But the `User` resolver block has no field resolver for `avatar`. Default resolution will look for `user.avatar` on the raw DB row. If the DB column is `profile_image` (as the update implies), `user.avatar` will always be `undefined` — writes succeed but reads return nothing. The frontend queries `avatar` on both `user` and post `author`, so this breaks avatar display site-wide.

---

### 2. Representational Completeness — 1 finding

**Finding D (Low): `createPost` mutation has no frontend representation**

`createPost` exists in both the schema and resolvers but the frontend component doesn't surface it. Not necessarily a bug — it may live in another component — but worth noting for a completeness audit.

---

### 3. Voice Consistency — Clean

All three artifacts are consistent in their technical register. N/A for prose voice.

---

### 4. Naming Coherence — 1 finding

**Finding E (Medium): `feed` describes user's own posts, not a feed**

The resolver filters by `author_id: userId`, returning a user's *own* posts:
```javascript
feed: async (_, { userId, limit }) => {
  return db('posts').where({ author_id: userId })...
```
A "feed" conventionally means posts from followed users or a timeline of others' content. The frontend's own section header agrees with the resolver's *behavior* ("Recent Posts") but the query name `feed` misrepresents it. This naming mismatch will confuse anyone implementing a real feed later, and the frontend component reinforces the confusion by using the `feed` query to populate "Recent Posts."

---

### 5. Framing Precision — same as Finding E above

`feed` is scoped narrower than its name implies.

---

### 6–10. (Origin Fidelity, Tone, Category Accuracy, Redundancy, Scope Discipline) — Clean

No findings in these categories for code artifacts of this type.

---

## Summary Table

| # | Severity | Location | Issue |
|---|----------|----------|-------|
| A | **High** | Schema ↔ Frontend | `role` field queried in component, not in schema |
| B | **High** | Schema ↔ Resolvers | `comments: [Comment!]!` can never be null per schema; resolver returns `null` for empty lists |
| C | **High** | Resolvers (write vs. read path) | `avatar` written to `profile_image` DB column; no resolver maps it back; reads always return undefined |
| D | Low | Schema/Resolvers ↔ Frontend | `createPost` mutation has no frontend counterpart (may be in another component) |
| E | **Medium** | All three | `feed` field name implies social timeline; behavior is user's own posts; frontend label ("Recent Posts") agrees with behavior but not the query name |

---

**Priority fixes:** A and B are runtime errors (will crash). C is a silent data bug (saves succeed, reads silently fail). E is a semantic debt that will cause confusion when a real feed is needed.