## Coherence Audit: GraphQL Schema + Resolvers + Frontend

Working through all 10 categories, comparing each artifact against the others.

---

### Category 1: Factual Accuracy — Do all field references resolve to real things?

**Finding 1 — CRITICAL: `role` field queried but does not exist in the schema**

Frontend (`UserProfile.tsx:13`) queries:
```graphql
role
```

Schema `User` type fields: `id`, `username`, `displayName`, `email`, `avatar`, `bio`, `postCount`, `createdAt`. No `role` field exists. This would fail GraphQL validation at query time.

The frontend also conditionally renders it (`user.role && <span className="role-badge">{user.role}</span>`), so this isn't a typo — it's a real intended field that was never added to the schema or resolver.

**Finding 2 — CRITICAL: `Post.comments` resolver returns `null` but schema declares `[Comment!]!`**

Schema:
```graphql
comments: [Comment!]!
```

Resolver (`resolvers/index.js:60`):
```javascript
comments: async (post) => {
  const comments = await db('comments').where({ post_id: post.id });
  return comments.length > 0 ? comments : null;  // ← returns null
},
```

The schema says the field is non-nullable (`!`) — returning `null` will propagate as a resolver error up the tree at runtime. It should return `[]` (empty array), not `null`.

---

### Category 4: Naming Coherence — Do the same concepts use the same names everywhere?

**Finding 3 — HIGH: `avatar` vs `profile_image` — broken field mapping in `updateUser`**

Schema defines:
```graphql
type User { avatar: String }
input UpdateUserInput { avatar: String }
```

The `updateUser` resolver (`resolvers/index.js:48`) writes to the DB using:
```javascript
profile_image: input.avatar,
```

But the `User` field resolver block has no mapping for `avatar` → `profile_image`. Compare with how `displayName` is handled — it has an explicit resolver:
```javascript
User: {
  displayName: (user) => user.display_name,  // ← explicit mapping
  // ...no avatar: (user) => user.profile_image
}
```

This means `avatar` is read directly as `user.avatar` from the DB row, but updates are written to `profile_image`. If the DB column is `profile_image`, reads will always return `null`/`undefined`. If the DB column is `avatar`, the update silently writes to a nonexistent column.

---

### Category 5: Framing Precision — Does described behavior match actual behavior?

**Finding 4 — MEDIUM: `feed` is semantically misrepresented**

Schema names the query `feed(userId: ID!, limit: Int = 10)`, which implies a social feed (posts from followed accounts, curated content, etc.).

Resolver implementation:
```javascript
feed: async (_, { userId, limit }) => {
  return db('posts').where({ author_id: userId }).orderBy('created_at', 'desc').limit(limit);
},
```

This returns "posts authored by userId" — which is a user's post history, not a feed. The naming creates an expectation mismatch. The frontend uses it as a "Recent Posts" section, which is the correct semantic, but the query name `feed` misleads anyone reading the schema.

---

### Category 8: Category Accuracy — Are things classified as what they actually are?

**Finding 5 — LOW: Frontend assumes `user` is non-null without guarding**

Schema:
```graphql
user(id: ID!): User  # nullable — returns null if not found
```

Frontend (`UserProfile.tsx:38`):
```javascript
const { user, feed } = data;
// ...
<Avatar src={user.avatar} alt={user.displayName} ...
```

If the user ID doesn't exist, the resolver returns `null`, `data.user` is `null`, and `user.avatar` throws a runtime TypeError. The component handles `loading` and `error` states but not the `user === null` case.

---

### Categories 2, 3, 6, 7, 9, 10 — No significant findings

- **Representational Completeness**: All schema types (`User`, `Post`, `Comment`, `UserConnection`) are covered by resolvers. No orphaned types.
- **Voice Consistency**: N/A (code artifacts, not prose).
- **Origin Fidelity**: N/A.
- **Tone Calibration**: N/A.
- **Cross-Reference Redundancy**: No duplicate definitions.
- **Scope Discipline**: Each artifact covers its own layer cleanly.

---

## Summary

| # | Finding | Artifacts | Severity |
|---|---------|-----------|----------|
| 1 | `role` field queried in frontend, absent from schema and resolvers | Frontend ↔ Schema | Critical |
| 2 | `comments` resolver returns `null`; schema declares `[Comment!]!` | Resolver ↔ Schema | Critical |
| 3 | `avatar` in schema/input maps to `profile_image` in DB write, no read-side resolver | Schema ↔ Resolver | High |
| 4 | `feed` query returns author's own posts, not a social feed | Schema ↔ Resolver | Medium |
| 5 | Frontend doesn't null-check `user` before accessing fields | Frontend ↔ Schema | Low |