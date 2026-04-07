## Coherence Audit — Four Locale/Form Artifacts

Working through all 10 categories, comparing each artifact against every other.

---

### Step 1: Parts Inventory

| Artifact | Role |
|---|---|
| `en.json` | Source-of-truth key definitions + English strings |
| `es.json` | Spanish translations — must be a 1:1 key mirror of en.json |
| `ProfileForm.tsx` | Consumes locale keys via `t()`, field structure must match schema |
| `profileSchema.ts` | Validates field structure used by the form; also exports an API variant |

---

### Step 2: Checklist Results

---

#### 1. Factual Accuracy — **3 breaks**

**`profile.bio_placeholder` is referenced in the component but exists in neither locale.**

`ProfileForm.tsx:70`:
```tsx
placeholder={t('profile.bio_placeholder')}
```
Both `en.json` and `es.json` have no such key. At runtime this renders the raw key string `"profile.bio_placeholder"` as the placeholder text.

**`Avatar` is imported but never rendered.**

`ProfileForm.tsx:6`:
```tsx
import { Avatar } from './Avatar';
```
`Avatar` never appears in the JSX. The import is dead.

**`profile.avatar_label` is in both locales but has no consuming code.**

Neither the form's `formData` state, nor the JSX, nor the schema include an avatar field. The key exists in both locale files with no referencing code.

---

#### 2. Representational Completeness — **1 break**

**`es.json` is missing 3 keys that `en.json` defines:**

| Missing key | en.json value |
|---|---|
| `dashboard.welcome_back` | `"Welcome back, {{name}}!"` |
| `settings.danger_zone` | `"Danger Zone"` |
| `errors.rate_limited` | `"Too many requests. Please wait a moment."` |

`es.json` has `dashboard.welcome` but silently drops `dashboard.welcome_back`. Any code that calls `t('dashboard.welcome_back')` in Spanish will fall back to the key string or the English fallback, depending on i18next config.

---

#### 3. Voice Consistency — **1 break**

**Validation error message register is inconsistent between the two schemas.**

`profileSchema` uses full, polite sentences: `"Please enter a valid email address"`, `"Name is required"`.

`updateProfileBodySchema` uses terse fragments: `"Invalid email format"`, `"Bio too long"`, `"Email is required"`.

These are in the same file, described as covering the same data shape. A developer reading one will develop incorrect expectations about the other.

---

#### 4. Naming Coherence — **1 break**

**`common.submit` exists in both locales but the form uses `common.save` for its submit button.**

This isn't necessarily wrong — Save vs Submit is a product decision — but `common.submit` is defined and never referenced by this form, while `common.save` is used on a `<button type="submit">`. The distinction is undocumented and a future developer may reach for the wrong key.

---

#### 5. Framing Precision — **1 break**

**`profileSchema` and `updateProfileBodySchema` are framed as the same data shape for different contexts, but they diverge in rules:**

| Rule | `profileSchema` | `updateProfileBodySchema` |
|---|---|---|
| `name` regex | `^[a-zA-Z\s'-]+$` | absent |
| `bio` transform | `.trim() \|\| ''` | absent |
| `email` error | "Please enter a valid email address" | "Invalid email format" |

The comment `// Re-export for use in API routes` implies these are equivalent, but the API will accept names with numbers/symbols that the client form rejects. The server and client can diverge on what constitutes a valid profile.

---

#### 6. Origin Fidelity — no break

Both locales, the form, and the schema are coherent in intent: a profile editing workflow. No drift detected here.

---

#### 7. Tone Calibration — **1 break** (overlaps #3 above)

Zod validation errors in `profileSchema` are English-only hardcoded strings:
```ts
.min(1, 'Name is required')
.regex(/^[a-zA-Z\s'-]+$/, 'Name contains invalid characters')
```

These are displayed directly in the UI via:
```tsx
fieldErrors[field] = issue.message;  // ProfileForm.tsx:37
// ...
{errors.name && <span className="error">{errors.name}</span>}
```

The app has full i18n infrastructure (`react-i18next`, two locale files) but field-level validation errors will always appear in English regardless of language setting. The locale files have `errors.validation: "Please fix the errors below"` but no keys for the individual field error messages. **The i18n system is bypassed for the most user-visible error text.**

---

#### 8. Category Accuracy — no break

Keys are correctly namespaced (`common.*`, `nav.*`, `auth.*`, `dashboard.*`, `profile.*`, `settings.*`, `errors.*`). No miscategorization found.

---

#### 9. Cross-Reference Redundancy — **1 break**

`profileSchema` and `updateProfileBodySchema` duplicate `name` and `email` validation with differing behavior (see #5). This creates two sources of truth for the same constraints. If the name max length changes from 100, it must be changed in two places that can drift independently.

---

#### 10. Scope Discipline — no break

All four artifacts stay within their own domain. No content defending external technology choices.

---

### Findings Summary

| # | Artifact(s) | Issue | Severity |
|---|---|---|---|
| 1 | `ProfileForm.tsx` → both locales | `profile.bio_placeholder` used but not defined — renders as raw key | **High** |
| 2 | `es.json` vs `en.json` | 3 keys missing from Spanish: `dashboard.welcome_back`, `settings.danger_zone`, `errors.rate_limited` | **High** |
| 3 | `ProfileForm.tsx` + `profileSchema.ts` → both locales | Zod error messages are hardcoded English — i18n bypassed for field-level validation | **High** |
| 4 | `profileSchema.ts` (two schemas) | Client (`profileSchema`) and server (`updateProfileBodySchema`) accept different data — name regex and bio transform absent from server schema | **High** |
| 5 | `ProfileForm.tsx` | `Avatar` imported, never used | **Medium** |
| 6 | Both locales + `ProfileForm.tsx` | `profile.avatar_label` defined in both locales, no consuming code anywhere | **Medium** |
| 7 | `profileSchema.ts` | Inconsistent error message register between the two schemas (polite sentences vs terse fragments) | **Medium** |
| 8 | Both locales | `common.submit` defined but form uses `common.save` on its submit button — purpose of `common.submit` is unclear | **Low** |