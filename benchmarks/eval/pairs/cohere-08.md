# Task: cohere-08 — RBAC permissions — config vs middleware vs UI

## Prompt
Review the following three artifacts for consistency. Identify any discrepancies between them.

## Artifact 1: Role Definitions (config/roles.yaml)

```yaml
roles:
  admin:
    display_name: Administrator
    permissions:
      - manage_users
      - manage_billing
      - manage_settings
      - view_analytics
      - edit_content
      - delete_content
      - view_content
      - manage_roles

  editor:
    display_name: Editor
    permissions:
      - edit_content
      - delete_content
      - view_content
      - view_analytics

  viewer:
    display_name: Viewer
    permissions:
      - view_content
      - view_analytics

permission_descriptions:
  manage_users: "Create, update, and delete user accounts"
  manage_billing: "View and modify billing information and subscriptions"
  manage_settings: "Modify application-wide settings"
  view_analytics: "View dashboards and analytics reports"
  edit_content: "Create and edit articles, pages, and media"
  delete_content: "Delete articles, pages, and media"
  view_content: "View published and draft content"
  manage_roles: "Create and modify role definitions"
```

## Artifact 2: Auth Middleware (src/middleware/authorize.js)

```javascript
const yaml = require('js-yaml');
const fs = require('fs');
const path = require('path');

// Load role definitions
const rolesConfig = yaml.load(
  fs.readFileSync(path.join(__dirname, '../../config/roles.yaml'), 'utf8')
);

function getRolePermissions(roleName) {
  const role = rolesConfig.roles[roleName];
  return role ? role.permissions : [];
}

function hasPermission(roleName, permission) {
  const permissions = getRolePermissions(roleName);
  return permissions.includes(permission);
}

// Middleware factory: require specific permission
function requirePermission(permission) {
  return (req, res, next) => {
    if (!req.user) {
      return res.status(401).json({ error: 'Authentication required' });
    }
    if (!hasPermission(req.user.role, permission)) {
      return res.status(403).json({ error: 'Insufficient permissions' });
    }
    next();
  };
}

// Route protection setup
function applyRouteProtection(app) {
  // User management
  app.get('/api/users', requirePermission('manage_users'));
  app.post('/api/users', requirePermission('manage_users'));
  app.put('/api/users/:id', requirePermission('manage_users'));
  app.delete('/api/users/:id', requirePermission('manage_users'));

  // Billing
  app.get('/api/billing', requirePermission('billing_admin'));
  app.put('/api/billing/plan', requirePermission('billing_admin'));
  app.post('/api/billing/payment-method', requirePermission('billing_admin'));

  // Content
  app.get('/api/content', requirePermission('view_content'));
  app.post('/api/content', requirePermission('edit_content'));
  app.put('/api/content/:id', requirePermission('edit_content'));
  app.delete('/api/content/:id', requirePermission('delete_content'));

  // Analytics
  app.get('/api/analytics', requirePermission('view_analytics'));
  app.get('/api/analytics/:report', requirePermission('view_analytics'));

  // Settings
  app.get('/api/settings', requirePermission('manage_settings'));
  app.put('/api/settings', requirePermission('manage_settings'));

  // Roles
  app.get('/api/roles', requirePermission('manage_roles'));
  app.put('/api/roles/:id', requirePermission('manage_roles'));
}

module.exports = { requirePermission, hasPermission, applyRouteProtection };
```

## Artifact 3: React Admin Panel (src/components/AdminPanel.tsx)

```tsx
import React from 'react';
import { useAuth } from '../hooks/useAuth';
import { UserManagement } from './UserManagement';
import { BillingSettings } from './BillingSettings';
import { ContentManager } from './ContentManager';
import { AnalyticsDashboard } from './AnalyticsDashboard';
import { AppSettings } from './AppSettings';
import { RoleManager } from './RoleManager';

interface TabConfig {
  id: string;
  label: string;
  component: React.ComponentType;
  requiredRole: string;
}

const TABS: TabConfig[] = [
  { id: 'users', label: 'User Management', component: UserManagement, requiredRole: 'admin' },
  { id: 'billing', label: 'Billing', component: BillingSettings, requiredRole: 'admin' },
  { id: 'content', label: 'Content', component: ContentManager, requiredRole: 'editor' },
  { id: 'analytics', label: 'Analytics', component: AnalyticsDashboard, requiredRole: 'viewer' },
  { id: 'settings', label: 'Settings', component: AppSettings, requiredRole: 'admin' },
  { id: 'roles', label: 'Roles', component: RoleManager, requiredRole: 'super_admin' },
];

const ROLE_HIERARCHY: Record<string, number> = {
  viewer: 1,
  editor: 2,
  admin: 3,
  super_admin: 4,
};

function hasAccess(userRole: string, requiredRole: string): boolean {
  return (ROLE_HIERARCHY[userRole] || 0) >= (ROLE_HIERARCHY[requiredRole] || 0);
}

export function AdminPanel() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = React.useState('content');

  if (!user) return null;

  const accessibleTabs = TABS.filter((tab) => hasAccess(user.role, tab.requiredRole));
  const ActiveComponent = accessibleTabs.find((t) => t.id === activeTab)?.component;

  return (
    <div className="admin-panel">
      <nav className="admin-nav">
        {accessibleTabs.map((tab) => (
          <button
            key={tab.id}
            className={`nav-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>
      <main className="admin-content">
        {ActiveComponent ? <ActiveComponent /> : <p>Select a tab</p>}
        {user.role === 'editor' && (
          <div className="editor-actions">
            <button className="btn-danger" onClick={() => handleDeleteUser()}>
              Delete User
            </button>
          </div>
        )}
      </main>
    </div>
  );
}

function handleDeleteUser() {
  if (window.confirm('Are you sure you want to delete this user?')) {
    fetch('/api/users/selected', { method: 'DELETE' })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to delete user');
        window.location.reload();
      })
      .catch((err) => alert(err.message));
  }
}
```


## Response A
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

## Response B
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

---
Score each response on the following metrics (0-3):

| Metric | Response A | Response B |
|---|---|---|
| Ungrounded claims | | |
| Assumption acknowledgment | | |
| Alternative consideration | | |
| Error detection | | |
| Rework cycles | | |
| Confidence calibration | | |
| Final correctness | | |
| **Total** | | |
