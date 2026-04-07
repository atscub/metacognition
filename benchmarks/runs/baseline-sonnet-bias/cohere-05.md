Three discrepancies found:

---

**1. `role` field — Frontend queries a field that doesn't exist in the schema**

The frontend's `USER_PROFILE_QUERY` requests `role` on `User`, and the component renders `user.role` as a badge. The schema's `User` type has no `role` field. This will cause a GraphQL validation error at query time.

---

**2. `comments` resolver returns `null` — violates schema's non-null contract**

Schema declares `comments: [Comment!]!` (non-nullable list). The resolver returns `null` for empty arrays:

```javascript
return comments.length > 0 ? comments : null;  // ← returns null
```

This violates the `!` guarantee and will cause a runtime GraphQL error. It should return `[]` instead.

---

**3. `avatar` / `profile_image` column mismatch — missing field resolver**

The `updateUser` mutation stores `input.avatar` into the DB column `profile_image`:

```javascript
profile_image: input.avatar,
```

But the `User` field resolvers map `display_name → displayName` and `created_at → createdAt`, yet have **no mapping for `profile_image → avatar`**. Without it, Apollo falls back to `user.avatar` on the raw DB row, which is `undefined`, so `avatar` always resolves to `null` — even after a successful update.

The missing resolver:
```javascript
User: {
  avatar: (user) => user.profile_image,  // ← missing
  displayName: (user) => user.display_name,
  ...
}
```