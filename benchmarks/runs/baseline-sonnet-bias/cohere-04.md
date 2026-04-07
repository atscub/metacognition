Here are the discrepancies I found across the three artifacts:

---

## 1. `dark_mode` prod value mismatch

- **prod.json**: `enabled: true, percentage: 100`
- **Rollout plan table**: 50% — "Gradual rollout, monitor perf"

The config has already reached 100% but the plan documents it as a 50% rollout.

---

## 2. `new_index_engine` staging value mismatch

- **staging.json**: `enabled: false, percentage: 0`
- **Rollout plan table**: 100%

The plan says staging is at 100%, but the config has it fully disabled.

---

## 3. `new_checkout_flow` missing from all config files

- **featureGate.ts** checks `featureGate.isEnabled('new_checkout_flow')` at `/api/checkout`
- **Rollout plan** lists it with dev=100%, staging=50%, prod=0%
- **All three JSON configs** have no `new_checkout_flow` entry at all

The code will silently treat this flag as disabled everywhere (the `!flag` branch returns `false`), which means the checkout redirect never fires — contradicting the plan's claim of 100% in dev and 50% on staging.

---

## 4. Dependency rule violated in staging

The rollout plan explicitly states:
> `beta_search` depends on `new_index_engine` — never enable beta_search in an environment where new_index_engine is disabled.

But **staging.json** has `beta_search` enabled at 50% while `new_index_engine` is disabled at 0%. This directly violates the documented dependency.

---

## Summary table

| Discrepancy | Artifact A | Artifact B |
|---|---|---|
| `dark_mode` prod % | prod.json = 100% | rollout plan = 50% |
| `new_index_engine` staging % | staging.json = 0% | rollout plan = 100% |
| `new_checkout_flow` flag | missing from all configs | present in code + plan |
| `beta_search`/`new_index_engine` dependency | staging.json violates it | rollout plan doc states it |