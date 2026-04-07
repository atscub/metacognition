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

## Response B
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
