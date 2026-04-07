Now I'll systematically check these three artifacts against the 10 coherence categories:

## Coherence Audit Results

### 1. **Factual Accuracy** ⚠️ CRITICAL

**Discrepancy: Permission Name Mismatch**
- `roles.yaml` defines: `manage_billing`
- `authorize.js` line 30-32 requires: `billing_admin`
```javascript
app.get('/api/billing', requirePermission('billing_admin'));  // ❌ Wrong permission name
```
This permission doesn't exist in the role definitions. Any call to `/api/billing` will fail because `billing_admin` is not in any role's permissions list.

**Discrepancy: Undefined Role Reference**
- `roles.yaml` defines: `admin`, `editor`, `viewer` (3 roles)
- `AdminPanel.tsx` line 15 requires: `super_admin` (doesn't exist)
```tsx
{ id: 'roles', label: 'Roles', component: RoleManager, requiredRole: 'super_admin' },
```
No user will ever have `super_admin` role, so this tab is unreachable.

---

### 2. **Representational Completeness** ⚠️ HIGH

**Inconsistent Role Count:**
- `roles.yaml` defines: 3 roles
- `AdminPanel.tsx` ROLE_HIERARCHY: 4 roles (adds `super_admin`)
- This mismatch means the frontend has a role that the backend doesn't recognize

---

### 3. **Naming Coherence** ⚠️ HIGH

| Concept | roles.yaml | authorize.js | AdminPanel.tsx |
|---------|-----------|--------------|-----------------|
| Billing permission | `manage_billing` | `billing_admin` | (implicit in Billing tab) |
| Role manager permission | `manage_roles` | `manage_roles` | `super_admin` |

**The naming is inconsistent and the role doesn't exist.**

---

### 4. **Framing Precision** ⚠️ MEDIUM

**Authorization Model Mismatch:**
- `authorize.js` (backend): Permission-based access control
  ```javascript
  hasPermission(req.user.role, permission)  // Checks if user's role has this permission
  ```
- `AdminPanel.tsx` (frontend): Role hierarchy-based access control
  ```javascript
  ROLE_HIERARCHY[userRole] >= ROLE_HIERARCHY[requiredRole]  // Role level comparison
  ```

These are fundamentally different models. Backend checks exact permissions; frontend assumes a strict hierarchy where higher roles inherit all lower-role permissions. This assumption isn't enforced in the backend.

---

### 5. **Category Accuracy** ⚠️ HIGH

**Editor Role Permission Inconsistency:**

In `roles.yaml`:
```yaml
editor:
  permissions:
    - edit_content
    - delete_content      # ✓ Editor CAN delete content
    - view_content
    - view_analytics
```

In `AdminPanel.tsx` lines 41-47:
```tsx
{user.role === 'editor' && (
  <div className="editor-actions">
    <button className="btn-danger" onClick={() => handleDeleteUser()}>
      Delete User              // ❌ Deleting USERS, not CONTENT
    </button>
  </div>
)}
```

**The button allows editors to delete *users* (requires `manage_users` permission), but they only have `delete_content` permission.** The backend will reject this request with 403 Forbidden.

---

### 6. **Cross-Reference Redundancy** ⚠️ MEDIUM

The `TABS` configuration in `AdminPanel.tsx` duplicates role information that's already defined in `roles.yaml`. When a permission changes, you must update both places. Example: if you move `view_analytics` from viewer to editor, you'd need to update:
- The role definition (roles.yaml)
- The tab filtering logic (AdminPanel.tsx)

Currently these are separate and can drift.

---

## Summary of Defects

| Severity | Issue | Location |
|----------|-------|----------|
| 🔴 CRITICAL | Permission name doesn't exist: `billing_admin` vs `manage_billing` | authorize.js:30-32 |
| 🔴 CRITICAL | Role doesn't exist: `super_admin` referenced but never defined | AdminPanel.tsx:15, 18 |
| 🔴 CRITICAL | Editor can delete users but only has `delete_content` permission | AdminPanel.tsx:41-47 + authorize.js:DELETE /api/users |
| 🟡 HIGH | Authorization models conflict: backend is permission-based, frontend is role-hierarchy-based | authorize.js vs AdminPanel.tsx:28-30 |
| 🟡 MEDIUM | Role count mismatch: 3 roles defined, 4 roles used in hierarchy | roles.yaml vs AdminPanel.tsx:17 |
| 🟡 MEDIUM | Duplicate role specifications create drift risk | roles.yaml + AdminPanel.tsx:TABS |

**The system is incoherent and will fail at runtime when editors attempt certain actions.**