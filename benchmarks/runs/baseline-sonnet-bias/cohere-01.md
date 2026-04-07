Here are the discrepancies across the three artifacts:

---

## 1. `email` is required in the spec/docs but optional in the code

**Spec** (`CreateUserRequest.required`): `[name, email, role]`  
**Docs**: email marked `Required: Yes`  
**Code**: `const email = req.body.email || \`${name...}@placeholder.local\``

The code silently generates a placeholder email if none is provided. This contradicts both the spec and docs, and could silently corrupt data.

---

## 2. `DELETE /users/:user_id` exists only in the docs

**Docs**: Documents `DELETE /users/:user_id` returning `204 No Content`  
**Spec**: No `DELETE` operation defined  
**Code**: No `DELETE` route handler

Either the endpoint was planned but not implemented, or the docs describe a feature that doesn't exist.

---

## 3. Path parameter name is inconsistent

**Spec**: `/users/{user_id}` (snake\_case)  
**Docs**: `/users/:user_id` (snake\_case)  
**Code**: `/:userId` and `req.params.userId` (camelCase)

The SQL column is also `userId` (camelCase): `INSERT INTO users (userId, ...)`. This means the database rows likely return `userId`, but the spec declares the response field as `user_id`.

---

## 4. `404` responses not documented in the spec

**Code**: Returns `404 { error: 'User not found' }` for `GET /users/:userId` and `PUT /users/:userId`  
**Spec**: Neither endpoint defines a `404` response  
**Docs**: No mention of 404 for any endpoint

---

## Summary table

| Issue | Spec | Docs | Code |
|---|---|---|---|
| `email` on create | required | required | optional (fallback) |
| DELETE endpoint | missing | documented | missing |
| Path param name | `user_id` | `user_id` | `userId` |
| 404 on not found | undocumented | undocumented | returned |

The highest-risk issue is **#1** (silent placeholder email), since it will produce bad data in production without any visible error. **#2** (phantom DELETE) is also high-risk — clients reading the docs will call an endpoint that returns 404.