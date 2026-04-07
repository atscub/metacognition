## Coherence Audit Results

I've systematically checked all four artifacts against the 10 coherence categories. Here are the discrepancies:

---

### **1. Factual Accuracy** — HIGH SEVERITY

**Missing Translation Key:**
- `ProfileForm.tsx` line 57 references `t('profile.bio_placeholder')` but this key **does not exist** in either `locales/en.json` or `locales/es.json`

**Incomplete Spanish Locale:**
- `dashboard.welcome_back` exists in English but is **missing from Spanish**
- `settings.danger_zone` exists in English but is **missing from Spanish**

---

### **2. Representational Completeness** — MEDIUM SEVERITY

**Spanish Locale Gaps:**
The Spanish locale claims to be a complete translation set but omits 2 keys from the English version. Either:
- These features don't apply to Spanish users (should be documented), OR
- The Spanish translation was not updated when English added these keys

---

### **4. Naming Coherence** — HIGH SEVERITY

**Dual Schema Identity Crisis:**
`profileSchema.ts` exports two very similar but distinct schemas with different error messages:

| Schema | Name Error | Email Error |
|--------|-----------|-------------|
| `profileSchema` | "Name must be 100 characters or less" | "Please enter a valid email address" |
| `updateProfileBodySchema` | (only `min(1)` check) | "Invalid email format" |

Unclear which is authoritative or why they differ.

---

### **6. Origin Fidelity** — HIGH SEVERITY

**Hardcoded Validation Messages vs. Locale System:**

The validation schema in `profileSchema.ts` has error messages in English hardcoded in the Zod schema:
```typescript
.min(1, 'Name is required')
.email('Please enter a valid email address')
```

But the component expects to pull messages from locales:
```tsx
toast.success(t('profile.save_success'));  // ✓ localized
toast.error(t('profile.save_error'));      // ✓ localized
```

**This creates a gap:** Validation errors from the schema will never be translated. Users see English validation messages even in Spanish mode.

---

### **8. Category Accuracy** — MEDIUM SEVERITY

The validation schema mixes concerns:
- **Form-level validation** (`profileSchema`)
- **API-level validation** (`updateProfileBodySchema`)

But they're exported from the same file with different rules. The component only uses one, but it's unclear which schema is the source of truth.

---

### **10. Scope Discipline** — LOW SEVERITY

The name validation regex `/^[a-zA-Z\s'-]+$/` enforces rules (no numbers, special punctuation) that users never see explained. If someone submits "Jean-Pierre123", they get an error but no i18n-friendly message explaining the constraint.

---

## Summary of Required Fixes

| Issue | Type | Fix |
|-------|------|-----|
| `profile.bio_placeholder` missing | Factual | Add to both locales |
| Spanish locale incomplete | Factual | Add `dashboard.welcome_back` and `settings.danger_zone` to Spanish |
| Hardcoded validation messages | Design | Move Zod error messages to locales OR wire schema to use translation keys |
| Dual validation schemas | Naming | Either merge into one or clearly document the role of each |
| Name regex unexplained | Documentation | Add a locale key documenting valid name format, or adjust regex to accept more input |

Would you like me to fix these issues systematically?