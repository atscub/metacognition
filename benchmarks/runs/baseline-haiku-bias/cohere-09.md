# Consistency Review: Discrepancies Found

## 1. **Missing Translation Key in Component** 🔴 Critical
The React component references:
```tsx
placeholder={t('profile.bio_placeholder')}
```
But `profile.bio_placeholder` doesn't exist in either locale file. This will cause a translation miss at runtime.

---

## 2. **Missing Keys in Spanish Locale** 🔴 Critical
English has keys that Spanish lacks:
- `dashboard.welcome_back` (English only) — Spanish has `dashboard.welcome` but not `welcome_back`
- `settings.danger_zone` (English only) — Spanish jumps straight to `settings.delete_account`
- `errors.rate_limited` (English only) — No Spanish equivalent

These will cause i18n failures for Spanish users if those features are used.

---

## 3. **Hardcoded Validation Messages Not Localized** 🟡 Moderate
The Zod schema (Artifact 4) has validation errors as hardcoded English strings:
```typescript
.min(1, 'Name is required')
.max(100, 'Name must be 100 characters or less')
```

But the React component uses translation keys for UI strings. Validation errors won't be localized for Spanish users.

---

## 4. **Inconsistent Email Error Messages** 🟡 Moderate
- `profileSchema`: `"Please enter a valid email address"` (user-facing, polite)
- `updateProfileBodySchema`: `"Invalid email format"` (API response, terse)

These should be consistent or both use translation keys.

---

## Recommended Fixes

1. Add `"profile.bio_placeholder": "Tell us about yourself"` to both locales
2. Add missing keys to Spanish locale (welcome_back, danger_zone, rate_limited)
3. Extract validation messages to translation keys (create `validation.*` keys in locales)
4. Standardize error message tone across profileSchema and updateProfileBodySchema