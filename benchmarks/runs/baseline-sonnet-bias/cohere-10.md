Here are the discrepancies I found across the three artifacts:

---

## 1. Pagination: SDK types don't reflect v2.3.0 changes (major)

The SDK claims to be **API version 2.3.0**, but its types still reflect the old offset-based pagination that the changelog says was deprecated in that same version.

| | SDK Types | Routes | Changelog (v2.3.0) |
|---|---|---|---|
| Request param | `offset: number` | `cursor` (string, optional) | cursor replaces offset |
| Response fields | `total`, `offset`, `limit` | — | adds `nextCursor`, no mention of removing `total` |

`ListUsersParams.offset` should be replaced with `cursor?: string`, and `ListUsersResponse` should include `nextCursor?: string`.

---

## 2. `deleteWorkspace` exists in SDK but was removed in v2.2.0

The `ApiClient` interface declares `deleteWorkspace(workspaceId: string): Promise<void>`. The routes comment it out explicitly ("removed in v2.2.0"), and the changelog confirms it as a **breaking removal** in v2.2.0. An SDK generated at API v2.3.0 should not expose this method.

---

## 3. `Workspace` interface missing `status` field

The changelog (v2.2.0) introduced soft-delete via `PATCH /workspaces/:id` with `{"status": "deleted"}`. The routes expose `PATCH /workspaces/:workspaceId`. But the `Workspace` interface has no `status` field, and there's no `UpdateWorkspaceParams` type — nor an `updateWorkspace` method on `ApiClient`.

---

## 4. `createProject` and `updateWorkspace` missing from `ApiClient`

Two routes have no corresponding SDK client methods:
- `POST /workspaces/:workspaceId/projects` → no `createProject()` on `ApiClient`
- `PATCH /workspaces/:workspaceId` → no `updateWorkspace()` on `ApiClient`

---

## Summary table

| Issue | SDK | Routes | Changelog |
|---|---|---|---|
| Pagination style | offset/limit | cursor/limit | cursor added in 2.3.0 ✓ |
| `deleteWorkspace` | present | removed | removed in 2.2.0 ✓ |
| `Workspace.status` | missing | PATCH exists | soft-delete exists ✓ |
| `createProject` | missing | route exists | — |
| `updateWorkspace` | missing | route exists | PATCH added ✓ |
| `nextCursor` in response | missing | — | added in 2.3.0 ✓ |

The routes and changelog are largely in agreement with each other. The SDK types are the primary source of drift — they appear to have been generated against an older spec despite the version header claiming 2.3.0.