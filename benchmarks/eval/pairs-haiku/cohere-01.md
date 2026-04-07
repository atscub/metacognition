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
Now I'll systematically check these three artifacts against the 10 coherence categories:

## Coherence Audit: Users API Artifacts

### **1. Factual Accuracy** ⚠️ CRITICAL ISSUES

| Discrepancy | Impact |
|---|---|
| **Parameter naming mismatch** | Spec/Docs use `user_id` (snake_case); Code uses `userId` (camelCase) in route params and responses |
| **Field naming in User object** | Spec/Docs define `user_id`, `created_at`; Code returns `userId` (mixed case). Inconsistent serialization. |
| **Email field requirement** | Spec: "required" in CreateUserRequest; Docs: "required"; Code: auto-generates a placeholder if missing (`email = req.body.email \|\| \`${name}@placeholder.local\``) |
| **DELETE endpoint exists only in Docs** | Docs describe `DELETE /users/:user_id` with 204 response; Spec makes no mention; Code doesn't implement it. |

**Verification needed**: Check actual database column names and response serialization.

---

### **2. Representational Completeness** ⚠️ INCOMPLETE

- Spec + Code: 4 endpoints (GET /users, POST /users, GET /{id}, PUT /{id})
- Docs: 5 endpoints (same 4 + DELETE)
- **Issue**: Docs overstate the API surface.

---

### **3. Voice Consistency** ✅ GOOD

Each artifact uses appropriate voice for its format (OpenAPI formal, code comments, markdown tables). No conflicts.

---

### **4. Naming Coherence** ⚠️ CRITICAL INCONSISTENCY

| Concept | Spec | Code | Docs |
|---|---|---|---|
| Path param | `user_id` | `:userId` | `:user_id` |
| Response field | `user_id` | `userId` | `user_id` |
| Timestamp field | `created_at` | `created_at` | `created_at` ✓ |
| Role enum | admin, member, guest | admin, member, guest | admin, member, guest ✓ |

**Issue**: Spec and Docs agree on snake_case; Code uses camelCase. This will confuse API consumers who read the spec, write snake_case, then get back camelCase.

---

### **5. Framing Precision** ⚠️ MISLEADING

- Spec frames: "User Management API, version 1.4.0" with 4 operations
- Docs frame: Full user management including delete capability
- Code frames: 4 operations only (no delete)
- **Issue**: Docs promise delete; Spec doesn't define it; Code doesn't implement it. Docs have broken contract.

---

### **6. Origin Fidelity** ✅ CONSISTENT

All three describe the same logical service. No narrative drift.

---

### **7. Tone Calibration** ⚠️ OVER-PROMISED

Docs confidently describe DELETE as a first-class operation ("Permanently deletes a user account. This action cannot be undone.") without any hedging or caveat. The spec and code don't support this promise.

---

### **8. Category Accuracy** ⚠️ MISCLASSIFICATION

Docs classify DELETE as an implemented endpoint. It's actually unimplemented.

---

### **9. Cross-Reference Redundancy** ✅ GOOD

Each artifact serves a distinct purpose:
- Spec = implementation contract
- Code = working implementation
- Docs = user-facing reference

Minimal redundancy; each adds value. However, redundancy alone won't help if they contradict each other.

---

### **10. Scope Discipline** ✅ GOOD

All three stay focused on the User API. No scope creep.

---

## Summary: Discrepancies Found

| Severity | Issue | Locations |
|---|---|---|
| 🔴 **HIGH** | Path parameter naming: `user_id` (spec/docs) vs `userId` (code) | All three artifacts disagree |
| 🔴 **HIGH** | Response field naming: Spec/Docs define `user_id`; Code returns `userId` | Spec vs Code vs Docs |
| 🔴 **HIGH** | Email field requirement: Spec/Docs required; Code optional with auto-generation | CreateUserRequest schema mismatch |
| 🔴 **HIGH** | DELETE endpoint: Described in Docs, missing from Spec, unimplemented in Code | Docs makes promise; reality doesn't support it |
| 🟡 **MEDIUM** | API version: Spec claims v1.4.0; Code/Docs never reference it | Spec only |

**Recommendation**: Before this API goes to production, resolve the parameter naming mismatch and clarify whether DELETE should be: (a) added, (b) removed from docs, or (c) documented as "coming soon".

## Response B
I found several significant discrepancies between these artifacts:

## 🔴 Critical Discrepancies

### 1. **Parameter Naming Mismatch** (user_id vs userId)
- **OpenAPI spec**: Uses `user_id` (snake_case) in path parameters and all schema properties
- **Code**: Uses `userId` (camelCase) in route parameters and database columns
- **Documentation**: Uses `user_id` (snake_case) in examples
- **Impact**: API contract mismatch — client code following the spec will break

### 2. **Email Field Requirement**
- **OpenAPI spec**: `email` is required in `CreateUserRequest`
- **Code**: `email` is OPTIONAL — defaults to generated placeholder if missing:
  ```javascript
  const email = req.body.email || `${name.toLowerCase().replace(/\s/g, '.')}@placeholder.local`;
  ```
- **Documentation**: Shows email as Required (Yes)
- **Impact**: Code accepts requests that violate the spec

### 3. **Missing DELETE Endpoint**
- **OpenAPI spec**: ❌ No DELETE operation defined
- **Code**: ❌ Not implemented
- **Documentation**: ✅ DELETE endpoint is fully documented with description and 204 response
- **Impact**: Documentation promises functionality that doesn't exist

### 4. **Response Field Names**
- **OpenAPI schema**: Defines `user_id` as the field name
- **Code**: Likely returns database rows with `userId` from the INSERT/UPDATE queries
- **Documentation**: Shows `user_id` in examples
- **Impact**: Clients will receive different field names than documented

### 5. **Created_at Field Handling**
- **OpenAPI**: `created_at` is part of the User schema response
- **Code**: Sets `created_at` via `NOW()` in database, but unclear if returned consistently
- **Documentation**: Shows `created_at` in response examples

## Priority Fixes

1. **Standardize on one naming convention** (recommend `user_id` to match OpenAPI/docs)
2. **Make email required** in code or remove from spec/docs
3. **Either implement DELETE** or remove from documentation
4. **Verify response field names** match OpenAPI schema definition

Would you like me to align these artifacts?

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
