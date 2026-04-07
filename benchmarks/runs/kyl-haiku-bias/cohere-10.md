Now I'll apply the coherence checklist systematically to identify discrepancies:

## **COHERENCE AUDIT: SDK Types, Routes & Changelog**

### **1. Factual Accuracy** ⚠️ CRITICAL ISSUES

| Finding | Evidence | Severity |
|---------|----------|----------|
| **Pagination API mismatch** | SDK types (Artifact 1) define `ListUsersParams` with `offset`/`limit`, but routes (Artifact 2) use `cursor`/`limit`. Changelog v2.3.0 says offset is deprecated. | HIGH |
| **deleteWorkspace still in SDK** | Artifact 1 includes `deleteWorkspace(workspaceId: string)` method, but Artifact 2 comment & Changelog v2.2.0 explicitly removed `DELETE /workspaces/:id`. | HIGH |
| **inviteUser role parameter type** | SDK shows `role: string`, but should match the enum `'owner' \| 'admin' \| 'member' \| 'guest'` (as defined in User interface). | MEDIUM |
| **API version timestamp mismatch** | SDK header says "Generated at: 2024-01-20T14:30:00Z" but Changelog v2.3.0 is dated 2024-01-15. SDK should be older. | MEDIUM |

### **2. Naming Coherence** ⚠️ INCONSISTENCY

| Concept | Artifact 1 | Artifact 2 | Artifact 3 | Status |
|---------|-----------|-----------|-----------|--------|
| Pagination approach | `offset`/`limit` | `cursor`/`limit` | cursor (v2.3.0), offset (deprecated v2.3.0) | **INCOHERENT** |
| Delete workspace | `deleteWorkspace()` method | REMOVED (comment: v2.2.0) | REMOVED (v2.2.0 entry) | **SDK outdated** |
| Update project | `updateProject()` | `PUT /projects/:projectId` | `PUT /projects/:id` (v2.1.0) | Consistent ✓ |

### **3. Representational Completeness** ⚠️ MISSING OPERATIONS

**Artifact 1 is missing:**
- `PATCH /workspaces/:workspaceId` (workspace soft updates) — exists in Artifact 2 & mentioned in Changelog v2.3.0
- **No SDK method for workspace updates at all** — only `deleteWorkspace()` which no longer exists

**Artifact 2 adds:**
- Zod schema validation not reflected in SDK type definitions
- Rate limiting headers (mentioned in Changelog v2.3.0) with no SDK types for response metadata

### **4. Framing Precision** ⚠️ VERSION MISMATCH

| Artifact | Claims | Reality |
|----------|--------|---------|
| SDK header | "API version: 2.3.0" | But implements 2.2.0 or earlier (has offset/limit, has deleteWorkspace) |
| Routes | No version claim | Implements v2.3.0 (cursor-based, no delete) |
| Changelog | v2.3.0 = current | Contradicted by SDK |

The SDK header says it's current (v2.3.0) but contains v2.1.0/v2.2.0 implementation.

---

## **Summary of Discrepancies**

| Issue | Type | Fix |
|-------|------|-----|
| SDK types use deprecated `offset`/`limit` pagination | Factual accuracy | Update `ListUsersParams` to use `cursor`/`limit` and add `nextCursor` to response |
| `deleteWorkspace()` method exists in SDK but endpoint was removed v2.2.0 | Factual accuracy | Remove method from SDK types |
| SDK missing `updateWorkspace()` or workspace PATCH support | Representational completeness | Add workspace update methods/types |
| `inviteUser(role: string)` lacks proper typing | Factual accuracy | Change to `role: 'owner' \| 'admin' \| 'member' \| 'guest'` |
| SDK header says v2.3.0 but implements v2.1.0 API surface | Framing precision | Update generation timestamp or rollback version claim |
| Routes have `workspace_id` (snake_case) but SDK uses `workspaceId` (camelCase) | Naming coherence | Normalize—likely routes should match SDK convention or vice versa |
| Changelog mentions rate limit headers but no SDK types for them | Representational completeness | Either add rate limit metadata types to SDK or remove from changelog |

**Root cause:** The SDK types appear to have been generated from an older OpenAPI spec (v2.1–2.2) but the header was updated to claim v2.3.0, while the Express routes were updated to match the actual v2.3.0 spec.