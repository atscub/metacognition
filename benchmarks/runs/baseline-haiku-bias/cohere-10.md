I've identified **four significant discrepancies** between these artifacts:

## 1. **Pagination API Mismatch** (Critical)
- **Artifact 1 (SDK)**: `ListUsersParams` uses `offset` and `limit` (no cursor support)
- **Artifact 2 (Routes)**: `listUsersQuery` validates `cursor` and `limit` (offset removed)
- **Artifact 3 (Changelog)**: v2.3.0 deprecates offset/limit, introduces cursor-based pagination

**Issue**: The SDK types haven't been updated to match the v2.3.0 API changes.

---

## 2. **ListUsersResponse Missing `nextCursor` Field**
- **Artifact 1 (SDK)**: `ListUsersResponse` has `offset`, `limit`, `total`, but no `nextCursor`
- **Artifact 3 (Changelog)**: v2.3.0 states "GET /users response now includes `nextCursor` field instead of `offset`"

**Issue**: SDK response type is outdated; missing the field that the API now returns.

---

## 3. **`deleteWorkspace()` Method Still in SDK (Breaking Change)**
- **Artifact 1 (SDK)**: `ApiClient.deleteWorkspace()` exists as a method
- **Artifact 2 (Routes)**: Comment explicitly states "DELETE /workspaces/:id removed in v2.2.0"
- **Artifact 3 (Changelog)**: v2.2.0 marked as **BREAKING**: DELETE endpoint removed

**Issue**: The SDK exposes a method for an endpoint that no longer exists.

---

## 4. **Missing `updateWorkspace()` Method in SDK**
- **Artifact 1 (SDK)**: No `updateWorkspace()` method in `ApiClient`
- **Artifact 2 (Routes)**: `PATCH /workspaces/:workspaceId` endpoint exists with `workspaces.update` handler
- **Artifact 3 (Changelog)**: v2.3.0 added "New `PATCH /workspaces/:id` endpoint for partial workspace updates"

**Issue**: SDK lacks a method to call the workspace update endpoint that the server now provides.

---

## Summary
The SDK types (Artifact 1) appear to be out of sync with v2.3.0. It needs to:
- ✅ Replace offset/limit pagination with cursor-based pagination
- ✅ Add `nextCursor` to `ListUsersResponse`
- ✅ Remove `deleteWorkspace()` method
- ✅ Add `updateWorkspace()` method