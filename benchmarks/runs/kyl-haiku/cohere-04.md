Running a systematic coherence check on your three artifacts. Here are the **critical discrepancies**:

## 🔴 Critical Issues

### 1. **Missing Flag Definition: `new_checkout_flow`**
- **Location**: Code references it (`src/features/featureGate.ts`, line 47)
- **Problem**: Not defined in ANY config file (dev, staging, or prod)
- **Impact**: Code will always get `undefined`, causing the feature gate logic to fail silently
- **Severity**: HIGH — Feature is broken, not just ungated

### 2. **Stale Rollout Plan vs. Current Configs**
The rollout plan is dated **Q1 2024**, but current date is **2026-04-07**. The plan's "current status" table contradicts actual configs:

| Feature | Plan Says | Config Says | Status |
|---------|-----------|-------------|--------|
| `dark_mode` prod | 50% | 100% | ❌ Config is ahead |
| `new_index_engine` staging | 100% (Week 1) | 0% (disabled) | ❌ Config reverted? |
| `beta_search` staging | 50% (Week 2) | 50% | ✓ Match |

**Question**: Did the rollout plan get superseded without documentation, or are the configs wrong?

---

## 🟡 High Issues

### 3. **Code vs. Configs: Incomplete Feature Gate Coverage**
The code **implements gates for only 3 flags** but configs define **5 flags**:

| Flag | In Code? | In Config? |
|------|----------|-----------|
| `beta_search` | ✓ | ✓ |
| `ai_suggestions` | ✓ | ✓ |
| `compact_sidebar` | ✓ | ✓ |
| `dark_mode` | ✗ | ✓ |
| `new_index_engine` | ✗ | ✓ |
| `new_checkout_flow` | ✓ | ✗ |

**Implication**: `dark_mode` and `new_index_engine` can't be controlled. Either they shouldn't be in configs, or the code is incomplete.

### 4. **Dependency Not Enforced in Code**
The rollout plan states:
> `beta_search` depends on `new_index_engine` — never enable beta_search in an environment where new_index_engine is disabled.

**Reality**: Staging has `beta_search` enabled at 50% while `new_index_engine` is disabled (0%). The code has no logic to prevent this misconfiguration.

---

## 📋 Summary of Coherence Failures

| Category | Finding |
|----------|---------|
| **Factual Accuracy** | `new_checkout_flow` undefined; config values don't match rollout plan |
| **Representational Completeness** | Code gates 4 flags; configs define 6; plan documents all 6 — inconsistent coverage |
| **Framing Precision** | Rollout plan framed as current Q1 2024 status, but it's April 2026 |
| **Category Accuracy** | Code has a route for a feature with no configuration record |
| **Cross-Reference Redundancy** | Plan's "current status" table contradicts the actual config files it should reflect |

**Recommendation**: Decide the authoritative source (configs or rollout plan?), then update all three artifacts to align. I'd suggest: remove the stale plan, document the flag-to-code mapping in a live spreadsheet or config schema, and add the missing `new_checkout_flow` to all three configs.