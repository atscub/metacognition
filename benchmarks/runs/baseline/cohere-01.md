Here are the discrepancies I found:

---

**1. `DELETE /users/:user_id` exists only in the docs**

The Markdown docs (Artifact 3) describe a `DELETE /users/:user_id` endpoint returning `204 No Content`. Neither the OpenAPI spec nor the Express routes implement it. Either the endpoint needs to be built and specced, or the docs section needs to be removed.

---

**2. `email` is required in the spec and docs, but optional in the code**

- OpenAPI `CreateUserRequest`: `required: [name, email, role]`
- Docs table: email Required = Yes
- Express `POST /` handler: `const email = req.body.email || \`${name}...@placeholder.local\``

The code silently accepts a missing `email` and synthesizes a placeholder. The contract says it's required. One of these needs to change.

---

**3. Path parameter name mismatch: `user_id` vs `userId`**

- OpenAPI spec path: `/users/{user_id}` → parameter name `user_id`
- Docs: `:user_id`
- Express routes: `/:userId` → `req.params.userId`

The route param name doesn't affect routing behavior, but it's inconsistent and creates confusion when reading across artifacts.

---

**4. SQL column name `userId` (camelCase) vs API field `user_id` (snake_case)**

The Express queries insert and filter on `userId` (e.g., `WHERE userId = $1`, `INSERT INTO users (userId, ...)`), but the OpenAPI `User` schema returns `user_id`. If the DB column is literally `userId`, then `RETURNING *` would return `userid` or `userId` depending on the DB driver — not `user_id` as the spec documents. This could be a silent contract violation in the API responses.

---

**5. `404` responses not documented in spec**

The Express handlers for `GET /:userId` and `PUT /:userId` both return `404` if the user isn't found. Neither the OpenAPI spec nor the docs mention this response code for those endpoints.

---

**Summary table:**

| # | Issue | Spec | Code | Docs |
|---|-------|------|------|------|
| 1 | DELETE endpoint | Missing | Missing | Present |
| 2 | email required? | Yes | No (optional fallback) | Yes |
| 3 | Path param name | `user_id` | `userId` | `user_id` |
| 4 | DB column vs API field | `user_id` | `userId` | `user_id` |
| 5 | 404 responses | Missing | Present | Missing |