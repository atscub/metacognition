## Coherence Audit: Role/Auth System

Working through all 10 categories, comparing every artifact against every other.

---

### 1. Factual Accuracy — **3 critical failures**

**A. `billing_admin` vs `manage_billing` (authorize.js vs roles.yaml)**

`roles.yaml` defines the permission as `manage_billing`. `authorize.js` protects billing routes with `billing_admin`:

```javascript
// authorize.js:38-40
app.get('/api/billing', requirePermission('billing_admin'));
app.put('/api/billing/plan', requirePermission('billing_admin'));
app.post('/api/billing/payment-method', requirePermission('billing_admin'));
```

No role has `billing_admin`. Every billing API call returns **403 for everyone**, including admins.

**B. `super_admin` role doesn't exist (AdminPanel.tsx vs roles.yaml)**

`AdminPanel.tsx` gates the Roles tab on `super_admin`:
```tsx
{ id: 'roles', label: 'Roles', component: RoleManager, requiredRole: 'super_admin' },
```

`roles.yaml` defines exactly three roles: `admin`, `editor`, `viewer`. `super_admin` is absent. The Roles tab is **permanently invisible** to every user.

**C. `manage_roles` — API reachable, UI unreachable (all three artifacts)**

`roles.yaml` grants `admin` the `manage_roles` permission. `authorize.js` correctly protects `/api/roles` with `manage_roles`. But `AdminPanel.tsx` requires `super_admin` to see the tab. The backend is correctly configured; the frontend blocks all access to it. The three artifacts disagree on who can manage roles.

---

### 2. Representational Completeness — **1 gap**

`permission_descriptions` in `roles.yaml` says `manage_roles` covers "Create and modify role definitions." `authorize.js` only registers GET and PUT routes for roles — no POST:

```javascript
app.get('/api/roles', requirePermission('manage_roles'));
app.put('/api/roles/:id', requirePermission('manage_roles'));
// No app.post('/api/roles', ...)
```

Creation is described but not implemented in the middleware.

---

### 3. Voice Consistency — **Pass**

All three are code artifacts, not prose. Not applicable.

---

### 4. Naming Coherence — **1 failure** (same as #1-A above)

`billing_admin` (authorize.js) and `manage_billing` (roles.yaml) are two names for the same concept. Every other permission name is consistent across all three artifacts (`manage_users`, `edit_content`, `view_analytics`, etc.). Billing is the sole outlier.

---

### 5. Framing Precision — **Pass**

No documentation framing to audit.

---

### 6. Origin Fidelity — **Pass**

No stated motivation to audit.

---

### 7. Tone Calibration — **Pass**

---

### 8. Category Accuracy — **1 architectural incoherence**

The three artifacts use **two different authorization models** that are never reconciled:

| Artifact | Model |
|---|---|
| `roles.yaml` + `authorize.js` | **Permission-based**: `hasPermission(role, permission)` |
| `AdminPanel.tsx` | **Role-hierarchy-based**: `ROLE_HIERARCHY[userRole] >= ROLE_HIERARCHY[requiredRole]` |

These models produce different answers. A user with a custom role could be granted `view_analytics` in the YAML and the API would serve them — but the UI would hide the Analytics tab because that role isn't in `ROLE_HIERARCHY`. The two systems can diverge silently.

---

### 9. Cross-Reference Redundancy — **1 failure**

The Editor "Delete User" button in `AdminPanel.tsx` is a redundancy that contradicts itself:

```tsx
{user.role === 'editor' && (
  <div className="editor-actions">
    <button className="btn-danger" onClick={() => handleDeleteUser()}>
      Delete User
    </button>
  </div>
)}
```

`roles.yaml` gives `editor` these permissions: `edit_content`, `delete_content`, `view_content`, `view_analytics`. No `manage_users`. `authorize.js` protects `DELETE /api/users/:id` with `manage_users`. The button renders for editors but the API call **always returns 403**. The UI claims a capability the permission model explicitly denies.

---

### 10. Scope Discipline — **Pass**

---

## Summary

| # | Finding | Severity | Location |
|---|---|---|---|
| 1 | `billing_admin` permission in middleware doesn't match `manage_billing` in YAML — billing API is permanently broken | **Critical** | authorize.js:38-40 vs roles.yaml |
| 2 | `super_admin` role used in UI doesn't exist in YAML — Roles tab unreachable | **Critical** | AdminPanel.tsx:9,30 vs roles.yaml |
| 3 | Editor "Delete User" button calls an API endpoint editors are forbidden from | **High** | AdminPanel.tsx:50-58 vs roles.yaml + authorize.js |
| 4 | Frontend uses role-hierarchy auth model; backend uses permission model — no reconciliation | **High** | AdminPanel.tsx vs authorize.js |
| 5 | No POST `/api/roles` route despite permission description covering "Create" | **Medium** | authorize.js vs roles.yaml permission_descriptions |

**Fixes in priority order:**
1. Rename `billing_admin` → `manage_billing` in `authorize.js` (lines 38–40)
2. Change `super_admin` → `admin` for the Roles tab in `AdminPanel.tsx` (line 9)
3. Remove the editor Delete User button, or gate it on `manage_users` permission
4. Pick one auth model for the frontend — either mirror the permission check via an API or a `hasPermission(user, permission)` hook, rather than a separate role hierarchy
5. Add `app.post('/api/roles', requirePermission('manage_roles'))` to the middleware