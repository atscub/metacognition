## Coherence Audit: Role/Permission System

Working through all 10 categories, comparing each artifact against the others.

---

### 1. Factual Accuracy — FAIL (2 critical bugs)

**Bug A: `billing_admin` vs `manage_billing`**

| Artifact | What it says |
|---|---|
| `roles.yaml` | Permission is named `manage_billing` |
| `authorize.js` | Billing routes require `billing_admin` |

`billing_admin` doesn't exist in any role's permission list. `hasPermission()` will return `false` for every billing route. **All billing API endpoints are permanently inaccessible to all users.**

**Bug B: `super_admin` role doesn't exist in `roles.yaml`**

| Artifact | What it says |
|---|---|
| `roles.yaml` | Defines 3 roles: `admin`, `editor`, `viewer` |
| `AdminPanel.tsx` | ROLE_HIERARCHY includes `super_admin: 4`; Roles tab requires it |

No user can ever have `super_admin` as their role (it's not in the config). The Roles tab is permanently hidden from everyone.

---

### 2. Representational Completeness — FAIL

`authorize.js` protects GET and PUT on `/api/roles`, meaning admins can hit those endpoints (they have `manage_roles`). But `AdminPanel.tsx` gates the Roles tab to `super_admin`. **Admins have API access but no UI access** — a capability that exists in the backend is invisible in the frontend.

---

### 3. Voice Consistency — PASS

All three artifacts speak to developers consistently. No audience drift.

---

### 4. Naming Coherence — FAIL

Two names for the same concept:

- `manage_billing` (roles.yaml, the source of truth)
- `billing_admin` (authorize.js, the consumer)

These should be identical. They aren't, which is why billing is broken.

---

### 5. Framing Precision — FAIL

`AdminPanel.tsx` frames the system as having 4 roles (viewer, editor, admin, super_admin). `roles.yaml` defines 3. The frontend's mental model of the authorization domain is broader than the actual domain.

---

### 6. Origin Fidelity — PASS

No stated motivation to check against here.

---

### 7. Tone Calibration — N/A

Code artifacts, not prose.

---

### 8. Category Accuracy — FAIL (authorization model mismatch)

The two enforcement layers use different access control models:

| Layer | Model |
|---|---|
| `authorize.js` | Permission-based: "does this role have permission X?" |
| `AdminPanel.tsx` | Role-hierarchy: "is user's role rank ≥ required rank?" |

These can produce divergent results. Example: the `editor` role has `delete_content` permission in `roles.yaml`. The content tab correctly requires role `editor` (level 2). But if a future permission is added to `editor` that shouldn't be visible to `viewer`, the hierarchy model would still show it — because viewer (level 1) < editor (level 2), the model is an approximation of the permission model, not the same thing.

More concretely: **the Roles tab** is gated to `super_admin` (level 4) in the UI but to `manage_roles` (which `admin` holds) in the API. This is a direct category mismatch — the same resource is classified differently by each layer.

---

### 9. Cross-Reference Redundancy — FAIL (privilege escalation bug)

`AdminPanel.tsx` lines 49–54:

```tsx
{user.role === 'editor' && (
  <div className="editor-actions">
    <button className="btn-danger" onClick={() => handleDeleteUser()}>
      Delete User
    </button>
  </div>
)}
```

`handleDeleteUser()` calls `DELETE /api/users/selected`, which is protected by `manage_users`. Editors do **not** have `manage_users` (verified in `roles.yaml`). The middleware will return `403`. The UI shows a button that always fails. This is a redundant/incorrect cross-reference between what the UI believes editors can do and what the permission system actually grants them.

---

### 10. Scope Discipline — PASS

No out-of-scope content.

---

## Summary of Findings

| # | Finding | Severity | Location |
|---|---|---|---|
| 1 | `billing_admin` used instead of `manage_billing` — all billing routes broken | **Critical** | `authorize.js` |
| 2 | `super_admin` role referenced but never defined — Roles tab permanently hidden | **Critical** | `AdminPanel.tsx` vs `roles.yaml` |
| 3 | Roles tab hidden from admins in UI but accessible to admins via API | **High** | `AdminPanel.tsx` vs `authorize.js` |
| 4 | Editor shown "Delete User" button — will always 403 | **High** | `AdminPanel.tsx` vs `roles.yaml` + `authorize.js` |
| 5 | Authorization model mismatch: permission-based in middleware, hierarchy-based in UI | **Medium** | `authorize.js` vs `AdminPanel.tsx` |
| 6 | `manage_roles` described as "Create and modify" but no `POST /api/roles` exists | **Low** | `roles.yaml` vs `authorize.js` |