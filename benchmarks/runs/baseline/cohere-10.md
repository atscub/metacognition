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