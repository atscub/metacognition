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
Running the full 10-category coherence audit across the three artifacts now.

---

## Coherence Audit Results

### Parts Inventory
- **A1**: SDK types (`sdk/src/types.ts`) — claims API version 2.3.0, generated 2024-01-20
- **A2**: Routes (`src/routes/index.ts`) — current server implementation
- **A3**: Changelog (`CHANGELOG.md`) — v2.1.0 through v2.3.0 history

---

### Category 1: Factual Accuracy — 4 violations

**1a. `deleteWorkspace` exposes a removed endpoint** (High)

| Artifact | Says |
|----------|------|
| A1 `ApiClient` | `deleteWorkspace(workspaceId: string): Promise<void>` — method exists |
| A2 routes | `// DELETE /workspaces/:id removed in v2.2.0` — no route registered |
| A3 changelog v2.2.0 | "BREAKING: `DELETE /workspaces/:id` endpoint removed" |

The SDK offers a method that calls an endpoint that hasn't existed since v2.2.0. Clients calling it will get a 404.

---

**1b. Pagination type is cursor in routes, offset in SDK** (High)

| Artifact | Says |
|----------|------|
| A1 `ListUsersParams` | `offset: number` (required), no `cursor` field |
| A1 `ListUsersResponse` | has `offset` field, no `nextCursor` field |
| A2 routes | `cursor: z.string().optional()`, no `offset` in schema |
| A3 changelog v2.3.0 | "offset/limit pagination is deprecated — use cursor"; "response now includes `nextCursor` instead of `offset`" |

The SDK types are stamped "API version: 2.3.0" but don't reflect the 2.3.0 pagination change. `offset` is required in `ListUsersParams` — meaning the SDK actively prevents use of the current pagination mechanism.

---

**1c. `createProject` exists in routes, absent from SDK** (High)

| Artifact | Says |
|----------|------|
| A1 `ApiClient` | No `createProject` method |
| A2 routes | `router.post('/workspaces/:workspaceId/projects', projects.create)` |

The SDK can list and get projects but cannot create them, despite the endpoint existing.

---

**1d. `PATCH /workspaces/:id` exists in routes, absent from SDK** (Medium)

| Artifact | Says |
|----------|------|
| A1 `ApiClient` | No `updateWorkspace` or `patchWorkspace` method |
| A2 routes | `router.patch('/workspaces/:workspaceId', workspaces.update)` |
| A3 changelog v2.3.0 | "New `PATCH /workspaces/:id` endpoint for partial workspace updates" |

Added in v2.3.0, documented in changelog, registered in routes — missing entirely from the SDK client interface.

---

### Category 2: Representational Completeness — 2 violations

**2a. `Workspace` has no `status` field despite soft-delete via status**

A3 (v2.2.0) and A2 (route comment) both state workspaces are soft-deleted by sending `{"status": "deleted"}`. The `Workspace` interface has no `status` field. There's also no `UpdateWorkspaceParams` type despite the PATCH endpoint existing.

**2b. SDK `ApiClient` covers only ~7 of the ~10 registered routes**

Routes not represented in `ApiClient`: `POST /workspaces/:workspaceId/projects`, `PATCH /workspaces/:workspaceId`, and the now-dead `DELETE /workspaces/:id` (present but shouldn't be).

---

### Category 4: Naming Coherence — 1 violation

**`deleteWorkspace` implies hard delete; actual behavior is soft-delete via PATCH**

Even if the SDK kept a delete affordance, the name `deleteWorkspace` is incoherent with a world where deletion is a PATCH operation setting `{"status": "deleted"}`. The name misleads about both the HTTP method and the semantics.

---

### Category 5: Framing Precision — 1 violation

**"Auto-generated from OpenAPI spec — API version: 2.3.0" is contradicted by the content**

If the file were actually auto-generated at v2.3.0, it would reflect cursor pagination and the absence of `deleteWorkspace`. Either:
- The OpenAPI spec itself was not updated when v2.3.0 shipped, or
- The generation is stale and the header comment is misleading

The comment "do not edit manually" combined with outdated types creates a false sense of authoritative accuracy.

---

### Category 7: Tone Calibration — 1 violation

**`inviteUser` loses the type safety established elsewhere** (Low)

```typescript
// A1 User.role:
role: 'owner' | 'admin' | 'member' | 'guest'

// A1 ApiClient.inviteUser:
inviteUser(workspaceId: string, email: string, role: string): Promise<User>
```

Every other role parameter in the SDK is the precise union type. `inviteUser` silently accepts any string, inconsistent with the type discipline the file otherwise maintains.

---

## Consolidated Finding Table

| # | Category | Severity | Violation |
|---|----------|----------|-----------|
| 1a | Factual accuracy | **High** | `deleteWorkspace` in SDK → endpoint removed in v2.2.0 |
| 1b | Factual accuracy | **High** | SDK pagination is `offset`-based; routes + changelog say cursor-based since v2.3.0 |
| 1c | Factual accuracy | **High** | `createProject` missing from `ApiClient` despite POST route existing |
| 1d | Factual accuracy | **Medium** | `updateWorkspace` missing from `ApiClient` despite PATCH route + changelog entry |
| 2a | Completeness | **Medium** | `Workspace` has no `status` field; no `UpdateWorkspaceParams` type |
| 2b | Completeness | **Medium** | SDK covers ~70% of registered routes |
| 4  | Naming | **Medium** | `deleteWorkspace` name implies hard delete; reality is soft-delete via PATCH |
| 5  | Framing | **Medium** | "Auto-generated at v2.3.0" claim contradicted by v2.3.0 content being absent |
| 7  | Tone | **Low** | `inviteUser(role: string)` — untyped against the union type used everywhere else |

---

## Root Cause

All high-severity findings have the same root cause: the SDK types were not regenerated (or manually updated) after v2.3.0 shipped. The changelog and routes both reflect the v2.3.0 state correctly and agree with each other on every point. The SDK is the sole out-of-sync artifact, despite its header claiming to be at v2.3.0.

## Response B
Here are the discrepancies I found across the three artifacts:

---

## 1. Pagination: SDK is stale relative to its claimed version

The SDK header says **API version: 2.3.0**, but its types reflect the old offset-based pagination that v2.3.0 deprecated.

| Artifact | Behavior |
|---|---|
| SDK `ListUsersParams` | `offset: number` (required), `limit: number` — no `cursor` |
| SDK `ListUsersResponse` | `total`, `offset`, `limit` — **no `nextCursor`** |
| Routes `listUsersQuery` | `cursor` field, no `offset` |
| Changelog v2.3.0 | cursor added, `offset` deprecated, response now has `nextCursor` |

The SDK needs `cursor?: string` in params and `nextCursor?: string` in the response, and `offset` should be marked optional/deprecated.

---

## 2. `deleteWorkspace` exists in SDK but was removed in v2.2.0

| Artifact | Behavior |
|---|---|
| SDK `ApiClient` | `deleteWorkspace(workspaceId: string): Promise<void>` |
| Routes | `DELETE` endpoint commented out: *"removed in v2.2.0"* |
| Changelog v2.2.0 | **BREAKING**: `DELETE /workspaces/:id` removed |

The SDK exposes a method that has no corresponding endpoint. Should be removed from `ApiClient`.

---

## 3. `Workspace` interface missing `status` field

The changelog v2.2.0 introduced soft-delete via `PATCH /workspaces/:id` with `{"status": "deleted"}`, and the routes include `router.patch('/workspaces/:workspaceId', ...)`. But the `Workspace` interface has no `status` field, so callers can't read the soft-delete state from a returned workspace.

---

## 4. `createProject` missing from `ApiClient`

The routes define `POST /workspaces/:workspaceId/projects` handled by `projects.create`, but `ApiClient` has no `createProject` method.

---

## 5. `inviteUser` role parameter typed as `string` instead of the union

```typescript
inviteUser(workspaceId: string, email: string, role: string): Promise<User>;
//                                                     ^^^^^^
```

`User.role` is `'owner' | 'admin' | 'member' | 'guest'`. The `role` parameter here should use the same union type (or a subset — guests probably can't invite owners).

---

## Summary table

| # | Issue | SDK | Routes | Changelog |
|---|---|---|---|---|
| 1 | Pagination style | offset-based | cursor-based | cursor added in 2.3.0 |
| 2 | `deleteWorkspace` | present | removed | removed in 2.2.0 |
| 3 | `Workspace.status` | missing | PATCH implies it exists | soft-delete via status field |
| 4 | `createProject` | missing | route exists | — |
| 5 | `inviteUser` role type | `string` | — | role union defined in 2.1.0 |

The SDK is the primary source of inconsistency — it claims to be generated for v2.3.0 but reflects pre-v2.2.0 behavior in two of the five issues.

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
