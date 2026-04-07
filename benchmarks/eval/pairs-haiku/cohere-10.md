# Task: cohere-10 — API client SDK vs server vs changelog

## Prompt
Review the following three artifacts for consistency. Identify any discrepancies between them.

## Artifact 1: TypeScript SDK Types (sdk/src/types.ts)

```typescript
// Auto-generated from OpenAPI spec — do not edit manually
// Generated at: 2024-01-20T14:30:00Z
// API version: 2.3.0

export interface User {
  id: string;
  email: string;
  displayName: string;
  avatarUrl: string | null;
  role: 'owner' | 'admin' | 'member' | 'guest';
  createdAt: string;
  updatedAt: string;
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  ownerId: string;
  plan: 'free' | 'pro' | 'enterprise';
  memberCount: number;
  createdAt: string;
}

export interface Project {
  id: string;
  workspaceId: string;
  name: string;
  description: string | null;
  status: 'active' | 'archived';
  createdAt: string;
  updatedAt: string;
}

export interface ListUsersParams {
  workspaceId: string;
  role?: 'owner' | 'admin' | 'member' | 'guest';
  offset: number;
  limit: number;
}

export interface ListUsersResponse {
  data: User[];
  total: number;
  offset: number;
  limit: number;
}

export interface CreateWorkspaceParams {
  name: string;
  slug: string;
  plan?: 'free' | 'pro' | 'enterprise';
}

export interface UpdateProjectParams {
  name?: string;
  description?: string | null;
  status?: 'active' | 'archived';
}

// SDK client methods
export interface ApiClient {
  // Users
  listUsers(params: ListUsersParams): Promise<ListUsersResponse>;
  getUser(userId: string): Promise<User>;
  inviteUser(workspaceId: string, email: string, role: string): Promise<User>;

  // Workspaces
  listWorkspaces(): Promise<Workspace[]>;
  getWorkspace(workspaceId: string): Promise<Workspace>;
  createWorkspace(params: CreateWorkspaceParams): Promise<Workspace>;
  deleteWorkspace(workspaceId: string): Promise<void>;

  // Projects
  listProjects(workspaceId: string): Promise<Project[]>;
  getProject(projectId: string): Promise<Project>;
  updateProject(projectId: string, params: UpdateProjectParams): Promise<Project>;
}
```

## Artifact 2: Express.js Server Routes (src/routes/index.ts)

```typescript
import { Router } from 'express';
import { authenticate } from '../middleware/auth';
import { validate } from '../middleware/validate';
import * as users from '../handlers/users';
import * as workspaces from '../handlers/workspaces';
import * as projects from '../handlers/projects';
import { z } from 'zod';

const router = Router();

// All routes require authentication
router.use(authenticate);

// --- Users ---

const listUsersQuery = z.object({
  workspace_id: z.string().uuid(),
  role: z.enum(['owner', 'admin', 'member', 'guest']).optional(),
  cursor: z.string().optional(),
  limit: z.coerce.number().int().min(1).max(100).default(20),
});

router.get('/users', validate({ query: listUsersQuery }), users.list);
router.get('/users/:userId', users.getById);
router.post('/users/invite', users.invite);

// --- Workspaces ---

const createWorkspaceBody = z.object({
  name: z.string().min(1).max(100),
  slug: z.string().min(1).max(50).regex(/^[a-z0-9-]+$/),
  plan: z.enum(['free', 'pro', 'enterprise']).default('free'),
});

router.get('/workspaces', workspaces.list);
router.get('/workspaces/:workspaceId', workspaces.getById);
router.post('/workspaces', validate({ body: createWorkspaceBody }), workspaces.create);
// DELETE /workspaces/:id removed in v2.2.0 — workspaces are now soft-deleted via PATCH
router.patch('/workspaces/:workspaceId', workspaces.update);

// --- Projects ---

const updateProjectBody = z.object({
  name: z.string().min(1).max(200).optional(),
  description: z.string().max(2000).nullable().optional(),
  status: z.enum(['active', 'archived']).optional(),
});

router.get('/workspaces/:workspaceId/projects', projects.list);
router.get('/projects/:projectId', projects.getById);
router.post('/workspaces/:workspaceId/projects', projects.create);
router.put('/projects/:projectId', validate({ body: updateProjectBody }), projects.update);

export default router;
```

## Artifact 3: Changelog (CHANGELOG.md)

```markdown
# Changelog

All notable changes to this project will be documented in this file.

## [2.3.0] — 2024-01-15

### Added
- Cursor-based pagination for `GET /users` endpoint. The `offset`/`limit`
  pagination is deprecated and will be removed in v3.0. Use `cursor` and
  `limit` parameters instead.
- New `PATCH /workspaces/:id` endpoint for partial workspace updates
  (including soft-delete via `{"status": "deleted"}`).
- Rate limiting headers (`X-RateLimit-Remaining`, `X-RateLimit-Reset`)
  on all endpoints.

### Changed
- `GET /users` response now includes `nextCursor` field instead of
  `offset` for pagination.

### Deprecated
- `offset` parameter on `GET /users` — use `cursor` instead.

## [2.2.0] — 2023-12-01

### Removed
- **BREAKING:** `DELETE /workspaces/:id` endpoint removed. Workspaces
  are now soft-deleted via `PATCH /workspaces/:id` with
  `{"status": "deleted"}`. Direct deletion is no longer supported.

### Added
- Workspace `plan` field now accepts `enterprise` tier.
- `GET /workspaces/:id` response includes new `memberCount` field.

### Fixed
- Fixed race condition in project creation that could result in
  duplicate slugs within a workspace.

## [2.1.0] — 2023-10-15

### Added
- Project archival: `PUT /projects/:id` now accepts
  `{"status": "archived"}` to archive a project.
- User invite endpoint: `POST /users/invite` sends an email invitation.

### Changed
- `User.role` now includes `guest` as a valid value.

### Fixed
- Fixed incorrect `total` count in paginated user list when role
  filter was applied.
```


## Response A
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

## Response B
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
