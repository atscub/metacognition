# Task: cohere-09 — Internationalization — translation files vs UI vs validation

## Prompt
Review the following four artifacts for consistency. Identify any discrepancies between them.

## Artifact 1: English Locale (locales/en.json)

```json
{
  "common.save": "Save",
  "common.cancel": "Cancel",
  "common.delete": "Delete",
  "common.edit": "Edit",
  "common.loading": "Loading...",
  "common.confirm": "Confirm",
  "common.back": "Back",
  "common.next": "Next",
  "common.submit": "Submit",
  "common.search": "Search",

  "nav.home": "Home",
  "nav.profile": "Profile",
  "nav.settings": "Settings",
  "nav.logout": "Log out",
  "nav.help": "Help",

  "auth.login_title": "Sign In",
  "auth.email_label": "Email Address",
  "auth.password_label": "Password",
  "auth.login_button": "Sign In",
  "auth.forgot_password": "Forgot your password?",
  "auth.register_link": "Create an account",

  "dashboard.title": "Dashboard",
  "dashboard.welcome": "Welcome, {{name}}",
  "dashboard.welcome_back": "Welcome back, {{name}}!",
  "dashboard.recent_activity": "Recent Activity",
  "dashboard.stats_label": "Your Statistics",

  "profile.title": "Your Profile",
  "profile.name_label": "Full Name",
  "profile.email_label": "Email",
  "profile.bio_label": "Bio",
  "profile.avatar_label": "Profile Photo",
  "profile.save_success": "Profile updated successfully",
  "profile.save_error": "Failed to update profile",

  "settings.title": "Settings",
  "settings.notifications": "Notifications",
  "settings.language": "Language",
  "settings.theme": "Theme",
  "settings.danger_zone": "Danger Zone",
  "settings.delete_account": "Delete Account",
  "settings.delete_confirm": "Are you sure? This cannot be undone.",

  "errors.generic": "Something went wrong",
  "errors.not_found": "Page not found",
  "errors.unauthorized": "Please sign in to continue",
  "errors.forbidden": "You don't have permission to do that",
  "errors.network": "Network error. Please check your connection.",
  "errors.rate_limited": "Too many requests. Please wait a moment.",
  "errors.validation": "Please fix the errors below"
}
```

## Artifact 2: Spanish Locale (locales/es.json)

```json
{
  "common.save": "Guardar",
  "common.cancel": "Cancelar",
  "common.delete": "Eliminar",
  "common.edit": "Editar",
  "common.loading": "Cargando...",
  "common.confirm": "Confirmar",
  "common.back": "Atr\u00e1s",
  "common.next": "Siguiente",
  "common.submit": "Enviar",
  "common.search": "Buscar",

  "nav.home": "Inicio",
  "nav.profile": "Perfil",
  "nav.settings": "Configuraci\u00f3n",
  "nav.logout": "Cerrar sesi\u00f3n",
  "nav.help": "Ayuda",

  "auth.login_title": "Iniciar Sesi\u00f3n",
  "auth.email_label": "Correo Electr\u00f3nico",
  "auth.password_label": "Contrase\u00f1a",
  "auth.login_button": "Iniciar Sesi\u00f3n",
  "auth.forgot_password": "\u00bfOlvidaste tu contrase\u00f1a?",
  "auth.register_link": "Crear una cuenta",

  "dashboard.title": "Panel",
  "dashboard.welcome": "Bienvenido, {{name}}",
  "dashboard.recent_activity": "Actividad Reciente",
  "dashboard.stats_label": "Tus Estad\u00edsticas",

  "profile.title": "Tu Perfil",
  "profile.name_label": "Nombre Completo",
  "profile.email_label": "Correo",
  "profile.bio_label": "Biograf\u00eda",
  "profile.avatar_label": "Foto de Perfil",
  "profile.save_success": "Perfil actualizado correctamente",
  "profile.save_error": "Error al actualizar el perfil",

  "settings.title": "Configuraci\u00f3n",
  "settings.notifications": "Notificaciones",
  "settings.language": "Idioma",
  "settings.theme": "Tema",
  "settings.delete_account": "Eliminar Cuenta",
  "settings.delete_confirm": "\u00bfEst\u00e1s seguro? Esto no se puede deshacer.",

  "errors.generic": "Algo sali\u00f3 mal",
  "errors.not_found": "P\u00e1gina no encontrada",
  "errors.unauthorized": "Inicia sesi\u00f3n para continuar",
  "errors.forbidden": "No tienes permiso para hacer eso",
  "errors.network": "Error de red. Verifica tu conexi\u00f3n.",
  "errors.validation": "Corrige los errores a continuaci\u00f3n"
}
```

## Artifact 3: React Form Component (src/components/ProfileForm.tsx)

```tsx
import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../hooks/useAuth';
import { profileSchema } from '../validation/profileSchema';
import { Avatar } from './Avatar';
import { toast } from '../utils/toast';

export function ProfileForm() {
  const { t } = useTranslation();
  const { user, updateProfile } = useAuth();
  const [formData, setFormData] = useState({
    name: user?.name || '',
    email: user?.email || '',
    bio: user?.bio || '',
  });
  const [errors, setErrors] = useState<Record<string, string>>({});

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    // Clear field error on change
    if (errors[name]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[name];
        return next;
      });
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors({});

    const result = profileSchema.safeParse(formData);
    if (!result.success) {
      const fieldErrors: Record<string, string> = {};
      result.error.issues.forEach((issue) => {
        const field = issue.path[0] as string;
        fieldErrors[field] = issue.message;
      });
      setErrors(fieldErrors);
      return;
    }

    try {
      await updateProfile(result.data);
      toast.success(t('profile.save_success'));
    } catch {
      toast.error(t('profile.save_error'));
    }
  };

  return (
    <form onSubmit={handleSubmit} className="profile-form">
      <h2>{t('profile.title')}</h2>

      <div className="form-group">
        <label htmlFor="name">{t('profile.name_label')}</label>
        <input
          id="name"
          name="name"
          type="text"
          value={formData.name}
          onChange={handleChange}
        />
        {errors.name && <span className="error">{errors.name}</span>}
      </div>

      <div className="form-group">
        <label htmlFor="email">{t('profile.email_label')}</label>
        <input
          id="email"
          name="email"
          type="email"
          value={formData.email}
          onChange={handleChange}
        />
        {errors.email && <span className="error">{errors.email}</span>}
      </div>

      <div className="form-group">
        <label htmlFor="bio">{t('profile.bio_label')}</label>
        <textarea
          id="bio"
          name="bio"
          value={formData.bio}
          onChange={handleChange}
          placeholder={t('profile.bio_placeholder')}
          rows={4}
        />
        {errors.bio && <span className="error">{errors.bio}</span>}
      </div>

      <div className="form-actions">
        <button type="submit" className="btn-primary">
          {t('common.save')}
        </button>
        <button type="button" className="btn-secondary">
          {t('common.cancel')}
        </button>
      </div>
    </form>
  );
}
```

## Artifact 4: Zod Validation Schema (src/validation/profileSchema.ts)

```typescript
import { z } from 'zod';

export const profileSchema = z.object({
  name: z
    .string()
    .min(1, 'Name is required')
    .max(100, 'Name must be 100 characters or less')
    .regex(/^[a-zA-Z\s'-]+$/, 'Name contains invalid characters'),

  email: z
    .string()
    .min(1, 'Email is required')
    .email('Please enter a valid email address'),

  bio: z
    .string()
    .max(500, 'Bio must be 500 characters or less')
    .optional()
    .transform((val) => val?.trim() || ''),
});

export type ProfileFormData = z.infer<typeof profileSchema>;

// Re-export for use in API routes
export const updateProfileBodySchema = z.object({
  name: z
    .string()
    .min(1, 'Name is required')
    .max(100, 'Name must be 100 characters or less'),

  email: z
    .string()
    .min(1, 'Email is required')
    .email('Invalid email format'),

  bio: z
    .string()
    .max(500, 'Bio too long')
    .optional(),
});
```


## Response A
Here are all discrepancies found across the four artifacts:

---

## 1. Keys present in `en.json` but missing from `es.json`

| Key | en.json value |
|-----|--------------|
| `dashboard.welcome_back` | `"Welcome back, {{name}}!"` |
| `settings.danger_zone` | `"Danger Zone"` |
| `errors.rate_limited` | `"Too many requests. Please wait a moment."` |

---

## 2. Key used in component but absent from both locale files

`ProfileForm.tsx:63` references `t('profile.bio_placeholder')` as the textarea placeholder, but `profile.bio_placeholder` is defined in neither `en.json` nor `es.json`. This will silently render the raw key string at runtime.

---

## 3. Key defined in both locales but unused in the component

`profile.avatar_label` exists in both locale files. The `Avatar` component is imported in `ProfileForm.tsx:6` but never rendered — so `profile.avatar_label` has no consumer. Either the avatar field was dropped without cleaning up, or it was accidentally omitted from the form.

---

## 4. Validation error messages bypass i18n

`profileSchema.ts` hardcodes English strings (e.g., `'Name is required'`, `'Please enter a valid email address'`). These are surfaced directly into the form via `fieldErrors` in `ProfileForm.tsx:36-41`, bypassing `t()`. Spanish users will see English validation errors while all other UI text is in Spanish.

---

## 5. Schema duplication with diverging constraints

`profileSchema.ts` defines `name` and `email` twice — once in `profileSchema` and again in `updateProfileBodySchema`. The `name` field in `updateProfileBodySchema` drops the regex constraint (`/^[a-zA-Z\s'-]+$/`) present in `profileSchema`. If the API route uses `updateProfileBodySchema`, it will accept characters the frontend rejects (and vice versa), creating inconsistent validation behavior.

## Response B
## Coherence Audit: Four Locale/Component Artifacts

Checking all parts against each other across the 10 categories.

---

### 1. Factual Accuracy — **3 issues found**

**es.json is missing 3 keys that exist in en.json:**
- `dashboard.welcome_back` — present in en.json, absent in es.json
- `settings.danger_zone` — present in en.json, absent in es.json
- `errors.rate_limited` — present in en.json, absent in es.json

Any code that calls `t('dashboard.welcome_back')` etc. will fall back to the key string in Spanish.

**ProfileForm.tsx references a key that exists in neither locale:**
```tsx
placeholder={t('profile.bio_placeholder')}  // line ~67
```
`profile.bio_placeholder` is not in `en.json` or `es.json`. The bio textarea will display the raw key string as its placeholder in all locales.

---

### 2. Representational Completeness — **1 issue**

`profile.avatar_label` exists in both locale files, but `ProfileForm.tsx` never references `t('profile.avatar_label')` and never renders anything related to avatar upload. The `Avatar` component is imported but never used. The locale advertises a feature the form doesn't implement.

---

### 4. Naming Coherence — **1 issue**

`Avatar` is imported in ProfileForm.tsx:
```tsx
import { Avatar } from './Avatar';
```
It appears nowhere in the JSX. Either a dead import (feature removed but not cleaned up) or an incomplete implementation — either way, it disagrees with the locale keys that suggest avatar management is part of the profile form.

---

### 7. Tone Calibration — **1 issue (cross-system)**

Zod validation error messages are hardcoded English strings:
```typescript
.min(1, 'Name is required')
.max(100, 'Name must be 100 characters or less')
.email('Please enter a valid email address')
```

These are displayed via `setErrors(fieldErrors)` and rendered inline in the form. A Spanish-speaking user will see English validation errors even with `es.json` loaded. The i18n system is bypassed entirely for validation feedback.

---

### 8. Category Accuracy — **1 issue**

`profileSchema` and `updateProfileBodySchema` are described as serving different roles (form vs. API), but they have **divergent validation rules with no acknowledged reason:**

| Rule | `profileSchema` | `updateProfileBodySchema` |
|------|----------------|--------------------------|
| Name regex (`/^[a-zA-Z\s'-]+$/`) | Yes | **No** |
| Bio `.transform()` (trim/empty→`''`) | Yes | **No** |
| Email error message | "Please enter a valid email address" | "Invalid email format" |
| Bio error message | "Bio must be 500 characters or less" | "Bio too long" |

A name like `"João123"` passes the API schema but fails the form schema. This creates a split where the API accepts data the UI would reject, or vice versa after a direct API call.

---

### 9. Cross-Reference Redundancy — **1 issue**

The two schemas share the same field structure and constraints, but are duplicated rather than composed. The comment says `// Re-export for use in API routes`, but the divergence means they are not actually the same contract. If the intent was to share validation, the implementation contradicts it; if the intent was to have different rules, the comment is misleading.

---

## Summary Table

| # | Artifact(s) | Issue | Severity |
|---|-------------|-------|----------|
| 1 | en.json ↔ es.json | `dashboard.welcome_back`, `settings.danger_zone`, `errors.rate_limited` missing from es.json | High |
| 2 | en.json / es.json ↔ ProfileForm.tsx | `profile.bio_placeholder` used in component, defined nowhere | High |
| 3 | profileSchema.ts ↔ en.json / es.json | Validation errors are hardcoded English strings, bypassing i18n | High |
| 4 | profileSchema ↔ updateProfileBodySchema | Divergent rules (name regex, bio transform, error messages) with no acknowledged reason | Medium |
| 5 | ProfileForm.tsx ↔ en.json / es.json | `Avatar` imported but unused; `profile.avatar_label` defined but never called | Medium |

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
