Three discrepancies found:

---

**1. `role` field queried by frontend but absent from schema**

`UserProfile.tsx` queries `role` on `User` and renders a badge for it. The schema's `User` type has no `role` field. This will fail GraphQL validation at query time.

---

**2. `Post.comments` resolver returns `null` on empty list, violating schema**

Schema declares `comments: [Comment!]!` — the field itself is non-nullable (the `!` after `]`).

The resolver does:
```js
return comments.length > 0 ? comments : null;  // ← returns null
```

Returning `null` for a non-nullable field causes a GraphQL runtime error that nulls out the parent `Post`. It should return `[]` for the empty case.

---

**3. `avatar` stored as `profile_image` in DB but no field resolver maps it back**

In `updateUser`, the resolver writes:
```js
profile_image: input.avatar,
```

But the `User` field resolvers only map `display_name → displayName` and `created_at → createdAt`. There's no resolver for `avatar`, so Apollo falls back to reading `user.avatar` from the raw DB row — which is always `undefined` since the column is named `profile_image`. Every user's avatar will silently return `null`.

Fix: add to the `User` resolver block:
```js
avatar: (user) => user.profile_image,
```

---

**Summary table**

| # | Location | Field | Issue |
|---|----------|-------|-------|
| 1 | Frontend query | `User.role` | Field doesn't exist in schema |
| 2 | Resolver `Post.comments` | return value | Returns `null` for non-nullable `[Comment!]!` |
| 3 | Resolver `User` | `avatar` | No mapping from `profile_image` DB column |