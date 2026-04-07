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
Now I'll systematically audit these four artifacts against the 10 coherence categories:

## 1. **Factual Accuracy** — Do references and claims match reality?

**DISCREPANCY FOUND:**
- **ProfileForm.tsx** references `t('profile.bio_placeholder')` but this key **does not exist** in either locale file (en.json or es.json).
- **Missing keys in Spanish locale**: The Spanish locale is missing `"dashboard.welcome_back"` and `"settings.danger_zone"` which exist in English.

---

## 2. **Representational Completeness** — Are all parts represented fairly?

**DISCREPANCY FOUND:**
- **Spanish locale is incomplete**: It drops 2 keys that exist in English without explanation:
  - `dashboard.welcome_back` (exists in en.json, missing in es.json)
  - `settings.danger_zone` (exists in en.json, missing in es.json)

---

## 3. **Voice Consistency** — Same audience and tone throughout?

**✓ Consistent:** Both locales use formal "you" (Spanish: "tu" informal). English is professional and clear. Spanish translations match in tone.

---

## 4. **Naming Coherence** — Do names describe their scope accurately?

**✓ Mostly consistent:** Translation keys follow `domain.concept` pattern throughout. However:
- **Minor issue**: `profile.bio_placeholder` is referenced in code but defined nowhere, suggesting incomplete naming scheme.

---

## 5. **Framing Precision** — Does scope match content?

**✓ Consistent:** Both locales frame the same functional areas (auth, profile, settings, errors).

---

## 6. **Origin Fidelity** — Does the stated motivation match actual design?

**Unclear — not directly applicable** to these artifacts, but the validation schema and form component don't seem to fully align with the localization strategy (see next issues).

---

## 7. **Tone Calibration** — Is confidence level appropriate?

**✓ Consistent:** Both locales use appropriately measured language. No overselling.

---

## 8. **Category Accuracy** — Are things classified correctly?

**DISCREPANCY FOUND:**
- **Validation schema error messages vs. locale messages**: 
  - Zod schema has hardcoded English error messages (e.g., `'Name is required'`, `'Bio must be 500 characters or less'`)
  - These hardcoded messages **will never be localized** and will always appear in English regardless of locale selection
  - The form component uses `t()` for UI labels but validation errors bypass localization entirely

---

## 9. **Cross-Reference Redundancy** — Does each location add new value?

**DISCREPANCY FOUND:**
- **Duplicate validation logic**: `profileSchema` and `updateProfileBodySchema` in the same file have overlapping rules with slightly different error messages:
  - `profileSchema.name`: `'Name must be 100 characters or less'`
  - `updateProfileBodySchema.name`: (no message provided, uses Zod default)
  - These should be unified or clearly separated

---

## 10. **Scope Discipline** — Is everything about the project itself?

**✓ Appropriate:** All locales are project-specific UI strings, not explaining i18n concepts.

---

## Summary of Critical Issues

| Issue | Severity | Location |
|-------|----------|----------|
| Missing translation key | **High** | `profile.bio_placeholder` in ProfileForm.tsx (line 61) but not defined in any locale |
| Incomplete Spanish locale | **High** | es.json missing `dashboard.welcome_back` and `settings.danger_zone` |
| Hardcoded validation messages | **High** | profileSchema.ts — all error messages bypass i18n system |
| Duplicate validation schemas | **Medium** | profileSchema.ts — overlapping rules with inconsistent messaging |

**Recommendation**: Before proceeding, fix the missing translation keys and restructure validation schemas to use localized error messages from the locale files.

## Response B
I found **4 critical discrepancies** across these artifacts:

## 1. **Missing Spanish Translations** (Artifact 2)

Three keys exist in English but are absent from Spanish:
- `dashboard.welcome_back` — English has this, Spanish doesn't
- `settings.danger_zone` — English has this, Spanish doesn't  
- `errors.rate_limited` — English has this, Spanish doesn't

If your app supports Spanish, these will cause runtime errors or fallback to English.

## 2. **Undefined Translation Key in Component** (Artifact 3)

The ProfileForm references:
```tsx
placeholder={t('profile.bio_placeholder')}
```

But `profile.bio_placeholder` is **not defined in either locale file**. This will display a missing key warning.

## 3. **Hardcoded Validation Error Messages** (Artifact 4)

The Zod schema has hardcoded English error messages:
```typescript
.min(1, 'Name is required')
.email('Please enter a valid email address')
```

These bypass i18n entirely. Spanish users will see English validation errors. The messages should be:
- Either moved to locale files and referenced dynamically
- Or generated as translatable keys the component can look up

Currently there's a mismatch: the component uses `t()` for UI labels, but validation errors come back in hardcoded English.

## 4. **Incomplete Feature** (Artifact 3)

The English locale has `profile.avatar_label`, but the ProfileForm component never renders an input field for it—only name, email, and bio. Either remove the unused key or add the avatar upload UI.

---

**To fix:**
1. Add missing Spanish translations (3 keys)
2. Add `profile.bio_placeholder` to both locales
3. Refactor validation to use locale keys or a shared i18n-aware validator
4. Either add avatar upload to form or remove the locale key

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
