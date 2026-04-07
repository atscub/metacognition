# Consistency Review: Feature Flag Artifacts

I found **4 critical discrepancies**:

## 1. **Missing Flag: `new_checkout_flow`** ⚠️
- **Location**: src/features/featureGate.ts (line 38-41)
- **Issue**: Code references `new_checkout_flow` in the `/api/checkout` route
- **Problem**: This flag is NOT defined in any config file (dev.json, staging.json, prod.json)
- **Impact**: The checkout redirect will silently fail because `featureGate.isEnabled('new_checkout_flow')` will always return `false` (missing flag defaults to disabled)
- **Rollout plan mentions it**: Yes, shows it should be 100% dev, 50% staging, 0% prod

---

## 2. **Dependency Violation: `beta_search` in Staging** 🔴
- **Location**: staging.json
- **Issue**: Violates stated dependency rule: *"beta_search depends on new_index_engine — never enable beta_search in an environment where new_index_engine is disabled"*
- **Current state**:
  - `new_index_engine`: **disabled** (enabled=false, percentage=0)
  - `beta_search`: **enabled** (enabled=true, percentage=50)
- **Impact**: Staging will try to use search features that depend on an unavailable index engine

---

## 3. **`dark_mode` Percentage Mismatch in Prod** ⚠️
- **Config vs. Plan**:
  - staging.json shows: 100%
  - prod.json shows: **100%**
  - Rollout plan shows: **50%** (should still be gradual rollout per Week 1 schedule)
- **Issue**: Config is ahead of the documented rollout schedule

---

## 4. **Code vs. Plan Mismatch: `new_checkout_flow` Routing** 
- **Issue**: Code treats `new_checkout_flow` as a feature gate, but it's not in the config
- **Expected behavior per plan**: Should be gateable at different percentages per environment
- **Current behavior**: Always returns 404 because the flag never exists

---

## Recommendations:

1. **Add `new_checkout_flow` to all config files** with appropriate percentages (dev: 100%, staging: 50%, prod: 0%)
2. **Fix staging.json**: Disable `beta_search` (set enabled=false) until `new_index_engine` is enabled
3. **Update prod.json `dark_mode`**: Change from 100% to 50% to match rollout plan, or update the plan to reflect current rollout status
4. **Document flag lifecycle**: Ensure every flag in code appears in configs and rollout plan