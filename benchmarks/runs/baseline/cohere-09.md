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