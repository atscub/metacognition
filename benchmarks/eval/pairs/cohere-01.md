# Task: cohere-01 — REST API spec vs implementation vs docs

## Prompt
Review the following three artifacts for consistency. Identify any discrepancies between them.

## Artifact 1: OpenAPI 3.0 Spec (openapi/users.yaml)

```yaml
openapi: "3.0.3"
info:
  title: User Management API
  version: "1.4.0"
paths:
  /users:
    get:
      summary: List all users
      operationId: listUsers
      parameters:
        - name: limit
          in: query
          schema:
            type: integer
            default: 20
        - name: offset
          in: query
          schema:
            type: integer
            default: 0
      responses:
        "200":
          description: A paginated list of users
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: array
                    items:
                      $ref: "#/components/schemas/User"
                  total:
                    type: integer
    post:
      summary: Create a new user
      operationId: createUser
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateUserRequest"
      responses:
        "201":
          description: User created
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/User"
  /users/{user_id}:
    get:
      summary: Get user by ID
      operationId: getUser
      parameters:
        - name: user_id
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        "200":
          description: User details
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/User"
    put:
      summary: Update a user
      operationId: updateUser
      parameters:
        - name: user_id
          in: path
          required: true
          schema:
            type: string
            format: uuid
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/UpdateUserRequest"
      responses:
        "200":
          description: User updated
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/User"
components:
  schemas:
    User:
      type: object
      properties:
        user_id:
          type: string
          format: uuid
        name:
          type: string
        email:
          type: string
          format: email
        role:
          type: string
          enum: [admin, member, guest]
        created_at:
          type: string
          format: date-time
    CreateUserRequest:
      type: object
      required:
        - name
        - email
        - role
      properties:
        name:
          type: string
        email:
          type: string
          format: email
        role:
          type: string
          enum: [admin, member, guest]
    UpdateUserRequest:
      type: object
      properties:
        name:
          type: string
        email:
          type: string
          format: email
        role:
          type: string
          enum: [admin, member, guest]
```

## Artifact 2: Express.js Route Handlers (src/routes/users.js)

```javascript
const express = require('express');
const router = express.Router();
const { v4: uuidv4 } = require('uuid');
const db = require('../db');

// GET /users - List all users
router.get('/', async (req, res) => {
  const limit = parseInt(req.query.limit) || 20;
  const offset = parseInt(req.query.offset) || 0;
  const [users, total] = await Promise.all([
    db.query('SELECT * FROM users LIMIT $1 OFFSET $2', [limit, offset]),
    db.query('SELECT COUNT(*) FROM users'),
  ]);
  res.json({ data: users.rows, total: parseInt(total.rows[0].count) });
});

// POST /users - Create a new user
router.post('/', async (req, res) => {
  const { name, role } = req.body;
  const email = req.body.email || `${name.toLowerCase().replace(/\s/g, '.')}@placeholder.local`;
  const userId = uuidv4();
  const result = await db.query(
    'INSERT INTO users (userId, name, email, role, created_at) VALUES ($1, $2, $3, $4, NOW()) RETURNING *',
    [userId, name, email, role]
  );
  res.status(201).json(result.rows[0]);
});

// GET /users/:userId - Get user by ID
router.get('/:userId', async (req, res) => {
  const result = await db.query('SELECT * FROM users WHERE userId = $1', [req.params.userId]);
  if (result.rows.length === 0) {
    return res.status(404).json({ error: 'User not found' });
  }
  res.json(result.rows[0]);
});

// PUT /users/:userId - Update a user
router.put('/:userId', async (req, res) => {
  const { name, email, role } = req.body;
  const result = await db.query(
    'UPDATE users SET name = COALESCE($1, name), email = COALESCE($2, email), role = COALESCE($3, role) WHERE userId = $4 RETURNING *',
    [name, email, role, req.params.userId]
  );
  if (result.rows.length === 0) {
    return res.status(404).json({ error: 'User not found' });
  }
  res.json(result.rows[0]);
});

module.exports = router;
```

## Artifact 3: API Documentation (docs/api/users.md)

```markdown
# Users API

Base URL: `https://api.example.com/v1`

## Endpoints

### List Users
`GET /users`

Returns a paginated list of users.

**Query Parameters:**
| Param  | Type    | Default | Description               |
|--------|---------|---------|---------------------------|
| limit  | integer | 20      | Max users per page        |
| offset | integer | 0       | Number of users to skip   |

**Response (200):**
```json
{
  "data": [{ "user_id": "...", "name": "...", "email": "...", "role": "...", "created_at": "..." }],
  "total": 42
}
```

### Create User
`POST /users`

Creates a new user account.

**Request Body:**
| Field | Type   | Required | Description         |
|-------|--------|----------|---------------------|
| name  | string | Yes      | Full name           |
| email | string | Yes      | Email address       |
| role  | string | Yes      | One of: admin, member, guest |

**Response (201):** Returns the created user object.

### Get User
`GET /users/:user_id`

Returns a single user by ID.

**Response (200):** Returns the user object.

### Update User
`PUT /users/:user_id`

Updates fields on an existing user.

**Request Body:** Same fields as Create User, all optional.

**Response (200):** Returns the updated user object.

### Delete User
`DELETE /users/:user_id`

Permanently deletes a user account. This action cannot be undone.

**Response (204):** No content.
```


## Response A
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

## Response B
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

---
Score each response on the following metrics (0-3):

| Metric | Response A | Response B |
|---|---|---|
| Ungrounded claims | | |
| Assumption acknowledgment | | |
| Alternative consideration | | |
| Error detection | | |
| Rework cycles | | |
| Confidence calibration | | |
| Final correctness | | |
| **Total** | | |
