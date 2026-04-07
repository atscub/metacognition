# Consistency Review: Discrepancies Found

I've identified **5 significant discrepancies** between these artifacts:

## 1. **Critical: Dependency Violation** ⚠️
**Staging config violates documented dependency constraint**
- `staging.json` enables `beta_search` at 50% 
- `staging.json` has `new_index_engine` disabled (0%)
- Rollout plan explicitly states: `beta_search` depends on `new_index_engine` — **never enable beta_search where new_index_engine is disabled**
- **Impact**: Staging environment is in an invalid state per its own constraints

## 2. **Missing Flag in Configs** 🔴
**Code references flag not defined in any config file**
- `src/features/featureGate.ts` checks `new_checkout_flow` in the `/api/checkout` route
- `new_checkout_flow` does **not exist** in dev.json, staging.json, or prod.json
- Rollout plan lists it with rollout percentages (100% dev, 50% staging, 0% prod)
- **Impact**: Code will always return false for this flag since it's not in the loaded configs

## 3. **Stale Rollout Plan**
- Document header says "Q1 2024" but today is **April 7, 2026** (~2 years old)
- Schedule shows dates like "Week 1 (Jan 15)" which have long passed
- **Impact**: Cannot determine current correct state or next actions

## 4. **dark_mode Percentage Mismatch**
- `prod.json` shows `dark_mode` at **100%**
- Rollout plan's current status table shows `dark_mode` prod at **50%**
- Plan schedules: Week 1 → 50%, Week 3 → 100%
- **Likely cause**: prod.json is ahead of the (stale) rollout plan schedule, OR the config was pushed without updating documentation

## 5. **Rollout Plan Missing ai_suggestions Details**
- Rollout plan notes `ai_suggestions` is "Blocked on vendor contract" 
- All three configs correctly show it disabled (0%)
- ✅ This one is **consistent**, but worth noting the documentation explains *why* it's off

---

### Recommendation
1. Update rollout plan with current date and actual status
2. Add `new_checkout_flow` to all three config files
3. Fix staging: disable `beta_search` until `new_index_engine` is enabled, or enable `new_index_engine` in staging
4. Document why `dark_mode` is at 100% in prod (was it already fully rolled out, or is the config out of sync with the plan?)