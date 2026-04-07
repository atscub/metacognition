Here are the discrepancies found across the four artifacts:

---

## 1. Missing keys in `es.json` (present in `en.json`, absent in Spanish)

| Key | English value |
|-----|--------------|
| `dashboard.welcome_back` | "Welcome back, {{name}}!" |
| `settings.danger_zone` | "Danger Zone" |
| `errors.rate_limited` | "Too many requests. Please wait a moment." |

---

## 2. Missing key in both locales (used in component)

`ProfileForm.tsx:68` references `profile.bio_placeholder` in the textarea's `placeholder` attribute, but this key does not exist in either `en.json` or `es.json`. This will silently render an empty placeholder or the raw key string, depending on the i18n library's fallback behavior.

---

## 3. `Avatar` imported but never rendered; `profile.avatar_label` never used

`ProfileForm.tsx:6` imports `Avatar`, and both locales define `profile.avatar_label`, but the form never renders an avatar field or uses `t('profile.avatar_label')`. Either the avatar UI was removed without cleaning up the import/translation keys, or it was never implemented.

---

## 4. Zod error messages are hardcoded English strings (not i18n-aware)

`profileSchema.ts` uses hardcoded strings like `'Name is required'`, `'Please enter a valid email address'`, etc. These will appear in English regardless of locale. Since `ProfileForm.tsx:37` maps Zod `issue.message` directly to `fieldErrors[field]` and renders them via `{errors.name}`, validation errors bypass the translation system entirely.

---

## 5. Inconsistent error messages between `profileSchema` and `updateProfileBodySchema`

Within `profileSchema.ts` itself, the two exported schemas have divergent messages for the same fields:

| Field | `profileSchema` | `updateProfileBodySchema` |
|-------|----------------|--------------------------|
| `email` invalid | `'Please enter a valid email address'` | `'Invalid email format'` |
| `bio` too long | `'Bio must be 500 characters or less'` | `'Bio too long'` |
| `name` max | `'Name must be 100 characters or less'` | `'Name must be 100 characters or less'` ✓ |

The `name` regex validator also exists only in `profileSchema`, not in `updateProfileBodySchema`, meaning the API route accepts names the UI form rejects.