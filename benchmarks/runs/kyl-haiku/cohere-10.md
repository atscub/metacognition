## Coherence Audit Results

I've systematically checked all 10 categories. Here are the **critical discrepancies**:

### 1. **Factual Accuracy — Pagination Mismatch** ⚠️ HIGH

**Discrepancy:** The SDK types (Artifact 1) define pagination using `offset`/`limit`, but the Changelog (Artifact 3) and Express routes (Artifact 2) show a different story.

| Artifact | Pagination Model |
|----------|------------------|
| **SDK Types** | `offset`, `limit` in ListUsersParams; `offset`, `limit`, `total` in ListUsersResponse |
| **Express Routes** | `cursor`, `limit` in Zod schema |
| **Changelog v2.3.0** | "Cursor-based pagination for `GET /users`... offset/limit is deprecated... response now includes `nextCursor`" |

**The SDK types are outdated.** They reflect the deprecated pagination model, not the current v2.3.0 API. ListUsersResponse should have `nextCursor` and `limit`, not `offset`.

---

### 2. **Factual Accuracy — Broken SDK Method** ⚠️ CRITICAL

**Discrepancy:** The SDK types (Artifact 1) include `deleteWorkspace()`, but the Changelog (Artifact 3) explicitly states this was removed in v2.2.0.

```typescript
// Artifact 1 (SDK) claims this exists:
deleteWorkspace(workspaceId: string): Promise<void>;
```

```markdown
// Artifact 3 (Changelog v2.2.0) states:
### Removed
- **BREAKING:** `DELETE /workspaces/:id` endpoint removed.
```

**The SDK includes a method for an endpoint that no longer exists.** This will cause SDK users to call a non-existent API.

---

### 3. **Naming Coherence — Parameter Case Mismatch** ⚠️ MEDIUM

**Discrepancy:** Parameter naming is inconsistent between the SDK and routes.

| Location | Parameter Name |
|----------|----------------|
| **SDK Types** | `workspaceId` (camelCase) |
| **Express Routes** | `workspace_id` (snake_case in Zod schema) |

The Express route uses `workspace_id` in the query validation, but the SDK expects `workspaceId`. This creates a protocol mismatch if the routes actually accept `workspace_id`.

---

### 4. **Framing Precision — Auto-Generated Claim** ⚠️ MEDIUM

**Discrepancy:** Artifact 1 claims to be "Auto-generated from OpenAPI spec" dated 2024-01-20, but:
- It doesn't reflect the current Changelog (v2.3.0 changes)
- It doesn't match the Express routes (cursor vs. offset/limit)
- Manual fixes would break the "auto-generated" contract

**Either the SDK types are manually maintained (and the auto-generated claim is false), or the generation pipeline is broken and out of sync.**

---

## Priority Fixes

| Issue | Action | Severity |
|-------|--------|----------|
| Remove `deleteWorkspace()` | Delete from SDK types | **CRITICAL** |
| Update pagination in SDK | Change to cursor-based, update ListUsersResponse | **CRITICAL** |
| Fix parameter naming | Align workspaceId/workspace_id (pick one consistently) | **HIGH** |
| Update SDK header comment | Remove or fix "auto-generated" claim, update generated date | **MEDIUM** |

Would you like me to create beads issues for these fixes or help you understand which version is the source of truth?