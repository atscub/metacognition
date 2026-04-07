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