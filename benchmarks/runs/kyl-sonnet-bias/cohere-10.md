Running the audit now. I'll compare all three artifacts across all 10 categories systematically.

---

## Coherence Audit: SDK Types vs Routes vs Changelog

### Step 1: Parts Inventory

| Artifact | Version | Date |
|---|---|---|
| `sdk/src/types.ts` | Claims API v2.3.0 | Generated 2024-01-20 |
| `src/routes/index.ts` | No version stated | — |
| `CHANGELOG.md` | Latest: v2.3.0 | Released 2024-01-15 |

---

### Step 2: Findings by Category

#### 1. Factual Accuracy — **4 HIGH-severity breaks**

**Break A — Pagination model mismatch (the biggest one)**

The changelog entry for v2.3.0 is clear:
> Cursor-based pagination for `GET /users`. The `offset`/`limit` pagination is deprecated. Use `cursor` and `limit` instead. Response now includes `nextCursor` field instead of `offset`.

The routes implement this correctly — `listUsersQuery` has `cursor: z.string().optional()` and no `offset`.

The SDK types do not. `ListUsersParams` still has `offset: number` (required, not optional) and no `cursor`. `ListUsersResponse` still has `offset` in the response and no `nextCursor`. The SDK header claims it was generated at `2024-01-20` against API version `2.3.0` — five days *after* v2.3.0 shipped. It did not pick up the breaking change.

**Break B — `deleteWorkspace` in SDK but the endpoint was deleted in v2.2.0**

Changelog v2.2.0:
> BREAKING: `DELETE /workspaces/:id` endpoint removed.

Routes correctly reflect this with a comment: `// DELETE /workspaces/:id removed in v2.2.0`.

SDK ApiClient:
```typescript
deleteWorkspace(workspaceId: string): Promise<void>;  // ← calls an endpoint that doesn't exist
```
The SDK exposes a method that will 404 at runtime.

**Break C — `createProject` exists in routes but not in SDK**

Routes: `router.post('/workspaces/:workspaceId/projects', projects.create)`

SDK ApiClient: no `createProject` method anywhere. `listProjects`, `getProject`, and `updateProject` exist — but creation is absent.

**Break D — `PATCH /workspaces/:workspaceId` exists in routes but not in SDK**

Routes: `router.patch('/workspaces/:workspaceId', workspaces.update)`
Changelog v2.3.0: "New `PATCH /workspaces/:id` endpoint for partial workspace updates."

SDK ApiClient: no `updateWorkspace` or `patchWorkspace` method. The endpoint (and the soft-delete mechanism it enables) is unreachable via the SDK.

---

#### 2. Representational Completeness — **1 MEDIUM break**

The `Workspace` interface has no `status` field, but the changelog describes soft-delete via `PATCH /workspaces/:id` with `{"status": "deleted"}`. If a workspace gets soft-deleted, a `GET /workspaces/:id` response presumably returns `status: "deleted"` — but the TypeScript type has nowhere to put it. The type is incomplete relative to the actual API contract.

---

#### 3. Voice Consistency — **No breaks**

All three artifacts address a developer audience with consistent technical register.

---

#### 4. Naming Coherence — **1 LOW break**

The route query schema uses `workspace_id` (snake_case, conventional for HTTP query params):
```typescript
workspace_id: z.string().uuid(),
```

The SDK type uses `workspaceId` (camelCase):
```typescript
workspaceId: string;
```

This is a common convention difference and may be intentional (SDK normalizes casing). However, it's not documented anywhere, and a developer comparing the two could be confused about whether they're the same parameter. Worth a note in the SDK.

---

#### 5. Framing Precision — **1 HIGH break**

The SDK file header states:
```
// Generated at: 2024-01-20T14:30:00Z
// API version: 2.3.0
```

This claims the file accurately represents v2.3.0. It does not — cursor pagination, `nextCursor` in responses, `PATCH /workspaces`, and `createProject` are all missing. The framing is false. Either the generator is broken, the wrong spec version was used, or the file was edited after generation and the header wasn't updated.

---

#### 6. Origin Fidelity — **No breaks**

The changelog's documented motivations (soft-delete replacing hard-delete, cursor replacing offset) are internally consistent and reflected in the routes. No narrative drift.

---

#### 7. Tone Calibration — **1 LOW note**

The `inviteUser` SDK signature types `role` as `string`:
```typescript
inviteUser(workspaceId: string, email: string, role: string): Promise<User>;
```

Every other occurrence of `role` in the SDK uses the precise union type `'owner' | 'admin' | 'member' | 'guest'`. This isn't a tone issue strictly, but it's a type precision regression — the SDK is less safe here than it is elsewhere without apparent reason.

---

#### 8. Category Accuracy — **1 LOW note**

`UpdateProjectParams` has all-optional fields (partial update semantics), but the route uses `PUT`:
```typescript
router.put('/projects/:projectId', ...)
```

`PUT` conventionally means full replacement; `PATCH` means partial update. The changelog entry for v2.1.0 also says `PUT`. So routes and changelog agree — but the behavior is PATCH-like. This is a semantic mismatch that's consistently wrong across two artifacts rather than an inconsistency between them.

---

#### 9. Cross-Reference Redundancy — **No breaks**

The inline comment in routes about the removed DELETE endpoint is brief and serves as localized documentation. It doesn't duplicate the changelog's detail. Acceptable.

---

#### 10. Scope Discipline — **No breaks**

All three artifacts stay within their own scope. No external ecosystem explanation or scope creep.

---

### Step 3: Findings Summary

| # | Finding | Artifacts | Severity |
|---|---|---|---|
| A | `ListUsersParams` has `offset`, no `cursor`; `ListUsersResponse` has `offset`, no `nextCursor` — despite v2.3.0 adding cursor pagination | SDK ↔ Routes ↔ Changelog | **HIGH** |
| B | `ApiClient.deleteWorkspace()` calls an endpoint removed in v2.2.0 | SDK ↔ Routes ↔ Changelog | **HIGH** |
| C | `createProject` route exists but has no SDK method | SDK ↔ Routes | **HIGH** |
| D | `PATCH /workspaces/:id` route exists (v2.3.0) but has no SDK method | SDK ↔ Routes ↔ Changelog | **HIGH** |
| E | `Workspace` interface missing `status` field despite soft-delete being the documented delete mechanism | SDK ↔ Changelog | **MEDIUM** |
| F | SDK header claims v2.3.0 but doesn't reflect v2.3.0 changes | SDK ↔ Changelog | **HIGH** (framing) |
| G | `workspace_id` (routes) vs `workspaceId` (SDK) — undocumented convention difference | SDK ↔ Routes | **LOW** |
| H | `inviteUser` types `role` as `string` instead of the union used everywhere else | SDK internal | **LOW** |
| I | `PUT /projects/:id` used for partial update (all fields optional) — semantic mismatch consistent across routes + changelog | Routes ↔ Changelog | **LOW** |

---

### Root Cause Assessment

Findings A, B, C, D, E, and F are all consistent with a single root cause: **the SDK type file was not updated when the server was updated for v2.2.0 and v2.3.0.** The server routes correctly reflect both releases. The changelog accurately documents both releases. The SDK is frozen at roughly v2.1.0 behavior while claiming to be at v2.3.0.

The highest-risk consequence is Finding B — `deleteWorkspace()` silently calls a dead endpoint. Any SDK consumer calling it will get a 404 or 405 with no compile-time warning.