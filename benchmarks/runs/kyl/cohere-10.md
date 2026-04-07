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