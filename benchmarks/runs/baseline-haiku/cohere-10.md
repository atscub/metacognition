# Consistency Review: Three Artifacts

I've identified **7 significant discrepancies** between the artifacts:

## 1. **Pagination Strategy Mismatch** ⚠️ CRITICAL
- **SDK** (`ListUsersParams`): Uses `offset` + `limit` parameters
- **Routes**: Uses `cursor` + `limit` parameters  
- **Changelog**: v2.3.0 explicitly deprecated `offset`/`limit` in favor of cursor-based pagination
- **Problem**: SDK is stuck on deprecated pagination model; clients using the SDK won't have access to cursor-based pagination

## 2. **SDK Still Exports Deleted `deleteWorkspace()` Method** ⚠️ CRITICAL
- **SDK** (`ApiClient`): `deleteWorkspace(workspaceId: string): Promise<void>` exists
- **Routes**: Comment states "DELETE /workspaces/:id removed in v2.2.0"
- **Changelog**: v2.2.0 lists "BREAKING: `DELETE /workspaces/:id` endpoint removed"
- **Problem**: SDK advertises a method that no longer exists on the server

## 3. **SDK Missing `updateWorkspace()` / Workspace PATCH Method**
- **Routes**: `PATCH /workspaces/:workspaceId` endpoint exists (soft-delete support)
- **SDK** (`ApiClient`): No `updateWorkspace()` method to call this endpoint
- **Changelog**: v2.3.0 highlights "New `PATCH /workspaces/:id` endpoint"
- **Problem**: SDK clients cannot perform workspace updates or soft-deletes

## 4. **SDK `ListUsersResponse` Doesn't Match v2.3.0 Changes**
- **SDK**: Response has `offset` + `limit` fields
- **Changelog** (v2.3.0): "Response now includes `nextCursor` field **instead of** `offset`"
- **Problem**: SDK response structure is outdated; missing `nextCursor` for cursor-based pagination

## 5. **Workspace Interface Missing `updatedAt` Field**
- **User** interface: Has `updatedAt`
- **Project** interface: Has `updatedAt`
- **Workspace** interface: Missing `updatedAt`
- **Problem**: Inconsistent schema design; routes likely return `updatedAt` on workspace responses

## 6. **Parameter Naming: `workspace_id` vs `workspaceId`**
- **Routes** (Zod validation): Query param is `workspace_id` (snake_case)
- **Routes** (path params): Uses `workspaceId` (camelCase)
- **Problem**: Query/path param naming inconsistency (minor, but worth standardizing)

## 7. **SDK Doesn't Have Response Pagination Field for New Format**
- **Changelog** (v2.3.0): Mentions `nextCursor` field added to paginated responses
- **SDK** (`ListUsersResponse`): No `nextCursor` field defined
- **Problem**: TypeScript SDK types don't match actual API responses post-v2.3.0

---

## Summary
The **SDK types are significantly out of sync** with the v2.3.0 server implementation and changelog. The SDK appears to reflect an older state (v2.1 era) with v2.2 features partially merged in. Both `deleteWorkspace()` and the pagination model need immediate updates.