## Coherence Audit Results

Working through the 10 coherence categories, I found **5 significant discrepancies**:

### 🔴 HIGH SEVERITY

#### 1. **Field Naming Mismatch** (Category 4: Naming Coherence)
| Artifact | Field Name |
|----------|-----------|
| OpenAPI Spec | `user_id` (snake_case) |
| Express Implementation | `userId` (camelCase) |
| Documentation | `user_id` (snake_case) |

**Impact**: The Express implementation stores and returns `userId` from the database, but the spec and docs expect `user_id`. API responses will not match the documented schema.

---

#### 2. **Email Not Actually Required** (Category 1: Factual Accuracy)
- **Spec claim**: `CreateUserRequest` lists `email` as required
- **Implementation reality**: Email is optional — auto-generated to `name.lowercase@placeholder.local` if missing
- **Impact**: Clients following the spec will fail when email is optional. Implementation violates its contract.

---

#### 3. **DELETE Endpoint Exists Only in Docs** (Category 2: Representational Completeness)
| Artifact | Has DELETE? |
|----------|-----------|
| OpenAPI Spec | ❌ No |
| Express Routes | ❌ No |
| Documentation | ✅ Yes (fully described) |

**Impact**: Users reading docs will attempt a DELETE that doesn't exist. Spec is incomplete.

---

#### 4. **URL Path Parameter Naming** (Category 4: Naming Coherence)
- **Spec & Express**: Parameter defined as `user_id` in path (`/users/{user_id}`, `/users/:userId` in code)
- **Documentation**: Shows `/users/:user_id` 
- **Implementation mismatch**: Express uses `req.params.userId` but the path variable is actually `userId` in the router, not matching the spec/docs `user_id`

**Impact**: Confusion about what the actual parameter name is.

---

### 🟡 MEDIUM SEVERITY

#### 5. **Incomplete OpenAPI Spec** (Category 1: Factual Accuracy)
The spec is missing:
- DELETE operation
- 404 error responses (documented in implementation and docs, not in spec)
- Response structure for DELETE (documented as 204 No Content in docs)

---

## Recommended Fixes (Priority Order)

1. **Standardize field naming**: Pick one convention (snake_case or camelCase) and apply everywhere
   - Database schema affects implementation — likely should be `user_id` in the API response
   
2. **Fix email validation**: Either make email required or update spec to mark it optional with default behavior documented

3. **Add DELETE endpoint**: Implement in Express or remove from documentation

4. **Complete OpenAPI spec**: Add DELETE operation, error responses (400, 404, 500)

5. **Sync URL parameters**: Ensure spec, implementation, and docs use identical parameter names

Would you like me to fix these discrepancies in the artifacts?