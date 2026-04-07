Here are the discrepancies I found across the three artifacts:

---

## Discrepancy 1: Wrong permission name for billing (authorize.js vs roles.yaml)

**authorize.js** guards billing routes with `billing_admin`:
```js
app.get('/api/billing', requirePermission('billing_admin'));
app.put('/api/billing/plan', requirePermission('billing_admin'));
app.post('/api/billing/payment-method', requirePermission('billing_admin'));
```

**roles.yaml** defines the permission as `manage_billing`. No role grants `billing_admin`, so **all billing API routes are permanently inaccessible** — even to admins. The correct string should be `'manage_billing'`.

---

## Discrepancy 2: Undefined role `super_admin` gates the Roles tab (AdminPanel.tsx vs roles.yaml)

**AdminPanel.tsx** requires `super_admin` to view the Roles tab:
```tsx
{ id: 'roles', label: 'Roles', component: RoleManager, requiredRole: 'super_admin' },
```

`super_admin` does not exist in **roles.yaml** (only `admin`, `editor`, `viewer`). Since no user can ever have `super_admin`, **the Roles tab is unreachable for anyone**. Meanwhile, `manage_roles` is already granted to `admin` in roles.yaml — the tab should use `requiredRole: 'admin'`.

---

## Discrepancy 3: Editor shown a "Delete User" button they cannot use (AdminPanel.tsx vs roles.yaml + authorize.js)

**AdminPanel.tsx** renders a "Delete User" button for editors:
```tsx
{user.role === 'editor' && (
  <div className="editor-actions">
    <button className="btn-danger" onClick={() => handleDeleteUser()}>
      Delete User
    </button>
  </div>
)}
```

This calls `DELETE /api/users/selected`, which **authorize.js** guards with `manage_users`. **roles.yaml** grants `manage_users` only to `admin` — editors don't have it. Every click results in a 403. The UI exposes a non-functional (and misleading) destructive action to the wrong role.

---

## Summary table

| # | What | Where | Expected | Actual |
|---|------|-------|----------|--------|
| 1 | Billing permission name | authorize.js | `manage_billing` | `billing_admin` |
| 2 | Role required for Roles tab | AdminPanel.tsx | `admin` | `super_admin` (nonexistent) |
| 3 | Delete User button visibility | AdminPanel.tsx | admin only | shown to editors |