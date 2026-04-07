## Coherence Audit: User Management API

Checking all three artifacts against each other across the 10 categories.

---

### Findings

**Discrepancy 1 — DELETE endpoint (Factual Accuracy / Representational Completeness) — HIGH**

The docs describe a `DELETE /users/:user_id` endpoint with a 204 response. Neither the OpenAPI spec nor the Express code contain any DELETE route. The docs are documenting functionality that does not exist.

| Artifact | DELETE endpoint |
|----------|----------------|
| OpenAPI spec | Absent |
| Express code | Absent |
| Docs | Present (204 No Content) |

**Discrepancy 2 — `email` field requirement (Factual Accuracy) — HIGH**

The OpenAPI spec lists `email` in `CreateUserRequest.required`. The docs mark email as `Required: Yes`. The Express code silently generates a placeholder email if none is provided:

```js
const email = req.body.email || `${name.toLowerCase().replace(/\s/g, '.')}@placeholder.local`;
```

The implementation contradicts the contract: a valid `POST /users` with no `email` field will succeed in production, violating the spec.

| Artifact | `email` on create |
|----------|------------------|
| OpenAPI spec | Required |
| Docs | Required |
| Express code | Optional (auto-generated fallback) |

**Discrepancy 3 — Field naming: `user_id` vs `userId` (Naming Coherence) — HIGH**

The spec and docs use snake_case `user_id` throughout — as the path parameter name, as the property key in the `User` schema, and in example responses. The Express code uses camelCase `userId` for the route parameter (`:userId`), the DB column name, and the INSERT statement. Since the code reads directly from DB rows (`result.rows[0]`), the JSON responses likely return `{ "userId": "..." }` rather than `{ "user_id": "..." }`, making actual API responses non-conformant with the spec.

| Artifact | Field name |
|----------|-----------|
| OpenAPI spec | `user_id` (path param + schema property) |
| Docs | `user_id` (path + example JSON) |
| Express code | `userId` (route param + DB column) |

**Discrepancy 4 — 404 responses undocumented (Representational Completeness) — MEDIUM**

The Express handlers for `GET /users/:userId` and `PUT /users/:userId` both return `404 { error: 'User not found' }` when no row is found. Neither the OpenAPI spec nor the docs document a 404 response for either endpoint. Callers have no contract to code against for the not-found case.

| Artifact | 404 on missing user |
|----------|-------------------|
| OpenAPI spec | Absent for both GET and PUT |
| Docs | Absent |
| Express code | Returned by both handlers |

---

### Summary Table

| # | Category | Issue | Severity |
|---|----------|-------|----------|
| 1 | Factual Accuracy / Completeness | DELETE endpoint in docs only | High |
| 2 | Factual Accuracy | `email` required in spec/docs, optional in code | High |
| 3 | Naming Coherence | `user_id` (spec/docs) vs `userId` (code) — likely breaks response format | High |
| 4 | Representational Completeness | 404 responses implemented but not documented anywhere | Medium |

---

### Fix Order

1. **`user_id` / `userId`** — Decide on one casing and update all three artifacts. The spec/docs are the contract; rename the DB column and route param to `user_id`, or update the spec/docs to use `userId`. Don't leave them split — actual JSON responses currently won't match the spec.
2. **DELETE endpoint** — Either add it to the spec and implement it in Express, or remove it from the docs.
3. **`email` requirement** — Either remove `email` from `required` in the spec (and update docs), or remove the fallback from the Express handler.
4. **404 responses** — Add 404 response definitions to the spec and a note to the docs for the GET and PUT endpoints.