## Coherence Audit: User Management API

Working through the 10 categories, comparing each artifact against the others:

---

### Findings

#### 1. Factual Accuracy — 3 discrepancies

**[HIGH] `email` marked required in spec/docs, but optional in code**

- **Spec** (`CreateUserRequest`): `required: [name, email, role]`
- **Docs**: `email | Required | Yes`
- **Code**: `const email = req.body.email || \`${name...}@placeholder.local\``

The implementation silently accepts requests without an email and auto-generates a placeholder. Clients following the spec contract would never know this fallback exists, and data with synthetic emails could silently enter the database.

**[HIGH] `user_id` vs `userId` naming mismatch**

- **Spec** path: `/users/{user_id}`, schema field: `user_id`
- **Docs** path: `/users/:user_id`
- **Code** route: `/:userId`, SQL: `WHERE userId = $1`, INSERT column: `userId`

The DB rows will return `userId` (camelCase), but the spec contract promises `user_id` (snake_case). Clients parsing responses by field name will fail to find `user_id`. This mismatch runs through every endpoint.

**[HIGH] 404 responses implemented but not specified**

- **Code**: Both `GET /users/:userId` and `PUT /users/:userId` return `404 { error: "User not found" }`
- **Spec**: Neither endpoint declares a `404` response
- **Docs**: Neither endpoint documents a `404` response

Clients have no contract for handling missing-user errors.

---

#### 2. Representational Completeness — 1 discrepancy

**[HIGH] DELETE endpoint exists only in docs**

- **Docs**: Documents `DELETE /users/:user_id` → 204 No Content, with the note "This action cannot be undone"
- **Spec**: No `DELETE` operation on `/users/{user_id}`
- **Code**: No `router.delete()` handler

One of four documented endpoints is entirely phantom — specified nowhere and implemented nowhere. Either the docs are aspirational and ahead of implementation, or the endpoint was removed from spec/code but not from docs.

---

#### 4. Naming Coherence — 1 additional observation

The `user_id` / `userId` split identified above is also a naming coherence failure. Across the three artifacts there is no single canonical name for the primary key. The spec and docs agree with each other (`user_id`) but the code disagrees with both (`userId`). Since the code drives actual DB column names and JSON serialization, what clients receive at runtime contradicts what both the spec and docs promise.

---

#### 5. Framing Precision — 1 discrepancy

**[LOW] Base URL in docs adds a `/v1` prefix absent from the spec**

- **Docs**: `Base URL: https://api.example.com/v1`
- **Spec**: Paths are `/users`, `/users/{user_id}` — no `/v1` prefix, no `servers` block

If the service is actually mounted at `/v1`, the spec is missing a `servers` entry. If it is not, the docs have an incorrect base URL.

---

### Summary Table

| # | Location | Severity | Issue |
|---|----------|----------|-------|
| 1 | Spec + Docs vs Code | **High** | `email` is required per contract, silently optional in implementation |
| 2 | Spec + Docs vs Code | **High** | `user_id` (spec/docs) vs `userId` (code/DB) — runtime responses break the contract |
| 3 | Code vs Spec + Docs | **High** | 404 responses are implemented but undocumented |
| 4 | Docs vs Spec + Code | **High** | `DELETE /users/:user_id` documented but not in spec or implemented |
| 5 | Docs vs Spec | **Low** | `/v1` base path in docs not reflected in spec |

The two most likely root causes: (1) the DELETE endpoint was planned/drafted in docs but not yet implemented, and (2) the codebase uses camelCase DB conventions that were never reconciled with the snake_case API surface defined in the spec.