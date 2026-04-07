I found **3 significant discrepancies** between these artifacts:

## Discrepancy 1: Permission Name Mismatch (Artifact 1 ↔ Artifact 2)

**Location**: `authorize.js` billing routes vs `roles.yaml`

```javascript
// authorize.js uses:
app.get('/api/billing', requirePermission('billing_admin'));
app.put('/api/billing/plan', requirePermission('billing_admin'));
app.post('/api/billing/payment-method', requirePermission('billing_admin'));
```

**But** `roles.yaml` defines the permission as `manage_billing`, not `billing_admin`. This will cause all billing endpoints to fail permission checks because `hasPermission()` won't find a `billing_admin` permission.

---

## Discrepancy 2: Undefined Role Reference (Artifact 1 ↔ Artifact 3)

**Location**: `AdminPanel.tsx` TABS and ROLE_HIERARCHY vs `roles.yaml`

```typescript
// AdminPanel.tsx references:
const ROLE_HIERARCHY: Record<string, number> = {
  viewer: 1,
  editor: 2,
  admin: 3,
  super_admin: 4,  // ← Not defined in roles.yaml
};

{ id: 'roles', label: 'Roles', component: RoleManager, requiredRole: 'super_admin' },
```

**But** `roles.yaml` only defines three roles: `admin`, `editor`, and `viewer`. There is no `super_admin` role. This tab will be inaccessible to all users, even admins.

---

## Discrepancy 3: Permission-Role Mismatch (Artifact 1 ↔ Artifact 3)

**Location**: `AdminPanel.tsx` editor actions vs `roles.yaml`

```typescript
// AdminPanel.tsx shows delete user button to editors:
{user.role === 'editor' && (
  <div className="editor-actions">
    <button className="btn-danger" onClick={() => handleDeleteUser()}>
      Delete User
    </button>
  </div>
)}
```

**But** the `editor` role in `roles.yaml` does NOT have the `manage_users` permission. The backend will reject this request with a 403. Either editors need `manage_users` permission, or this UI element should only show for `admin` users.

---

**Recommended fixes:**
1. Change `'billing_admin'` → `'manage_billing'` in authorize.js
2. Remove `super_admin` from AdminPanel.tsx or add it to roles.yaml
3. Change editor condition to `admin` or add `manage_users` to editor permissions