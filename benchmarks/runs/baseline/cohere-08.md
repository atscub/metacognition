Here are the discrepancies I found:

---

## Discrepancy 1: `billing_admin` vs `manage_billing` (Critical)

**authorize.js** uses the permission string `billing_admin` for all billing routes:
```js
app.get('/api/billing', requirePermission('billing_admin'));
app.put('/api/billing/plan', requirePermission('billing_admin'));
app.post('/api/billing/payment-method', requirePermission('billing_admin'));
```

**roles.yaml** defines `manage_billing` — no role has `billing_admin`. Result: billing routes always return 403, even for admins.

---

## Discrepancy 2: `super_admin` role doesn't exist (Critical)

**AdminPanel.tsx** requires `super_admin` to access the Roles tab and includes it in `ROLE_HIERARCHY` at level 4. **roles.yaml** defines only `admin`, `editor`, and `viewer`. No user can ever have role `super_admin`, so the Roles tab is permanently inaccessible to everyone.

---

## Discrepancy 3: Who can manage roles is contradictory

**roles.yaml** grants `manage_roles` to `admin`. **authorize.js** correctly guards `/api/roles` with `manage_roles` — so admins can call the API. But **AdminPanel.tsx** requires `super_admin` (a non-existent role) for the UI tab. Admins have the backend permission but are blocked by the frontend gate.

---

## Discrepancy 4: Editor can see "Delete User" button — but lacks permission (Security Bug)

**AdminPanel.tsx** renders a "Delete User" button when `user.role === 'editor'`:
```tsx
{user.role === 'editor' && (
  <div className="editor-actions">
    <button className="btn-danger" onClick={() => handleDeleteUser()}>
      Delete User
    </button>
  </div>
)}
```

`handleDeleteUser()` calls `DELETE /api/users/selected`. **roles.yaml** only gives `manage_users` (which covers user deletion) to `admin`. **authorize.js** protects `DELETE /api/users/:id` with `manage_users`. The request will always 403, but the button is still a misleading UX issue and suggests the author intended editors to delete users — a privilege escalation design intent that conflicts with the role definitions.

---

## Discrepancy 5: Missing `POST /api/roles` route

**authorize.js** defines only `GET /api/roles` and `PUT /api/roles/:id`, but **roles.yaml** describes `manage_roles` as "Create and modify role definitions." Creating a new role has no route.

---

## Summary Table

| # | Location A | Location B | Issue |
|---|---|---|---|
| 1 | `authorize.js` uses `billing_admin` | `roles.yaml` defines `manage_billing` | Billing always 403 |
| 2 | `AdminPanel.tsx` references `super_admin` | `roles.yaml` has no `super_admin` | Roles tab inaccessible |
| 3 | `roles.yaml` grants `manage_roles` to `admin` | `AdminPanel.tsx` requires `super_admin` for Roles tab | Backend/frontend gate mismatch |
| 4 | `AdminPanel.tsx` shows Delete User to editors | `roles.yaml` only grants `manage_users` to admin | Confusing/broken UX, implied privilege escalation |
| 5 | `roles.yaml` says manage_roles = create + modify | `authorize.js` has no `POST /api/roles` | Create role has no route |