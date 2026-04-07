Here are the discrepancies I found across the three artifacts:

---

## Discrepancy 1: `dark_mode` prod percentage

| Source | Value |
|---|---|
| `prod.json` | `enabled: true, percentage: 100` |
| Rollout plan table | 50% |

The rollout plan says prod is at 50% (gradual rollout), but prod.json has it fully enabled at 100%.

---

## Discrepancy 2: `new_index_engine` in staging

| Source | Value |
|---|---|
| `staging.json` | `enabled: false, percentage: 0` |
| Rollout plan table | 100% |

The rollout plan shows staging at 100%, and Week 1 of the schedule says "Enable `new_index_engine` on staging at 100%" — but staging.json has it fully disabled.

---

## Discrepancy 3: Dependency violation in staging

The rollout plan states explicitly:

> `beta_search` depends on `new_index_engine` — **never enable beta_search in an environment where new_index_engine is disabled.**

But `staging.json` has `beta_search` enabled at 50% while `new_index_engine` is disabled (0%). This directly violates the stated dependency rule.

---

## Discrepancy 4: `new_checkout_flow` missing from all configs

| Source | Status |
|---|---|
| Rollout plan | Dev 100%, Staging 50%, Prod 0% |
| `featureGate.ts` | Referenced as `'new_checkout_flow'` in `applyFeatureGates()` |
| All three config files | **Not present** |

The flag is in both the code and the rollout plan, but defined in none of the JSON configs. At runtime, `isEnabled('new_checkout_flow')` will always return `false` (flag lookup returns `undefined`), so the v2 checkout redirect will never fire — silently broken.

---

## Summary table

| # | Flag | Where | Issue |
|---|---|---|---|
| 1 | `dark_mode` | prod.json vs. rollout plan | 100% in config, 50% in plan |
| 2 | `new_index_engine` | staging.json vs. rollout plan | 0% in config, 100% in plan |
| 3 | `beta_search` + `new_index_engine` | staging.json vs. rollout plan rules | Dependency violated: beta_search on while new_index_engine off |
| 4 | `new_checkout_flow` | configs vs. code + rollout plan | Flag used in code and planned in doc, absent from all JSON configs |