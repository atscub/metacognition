## Coherence Audit: Feature Flag Artifacts

**Parts identified:** `dev.json`, `staging.json`, `prod.json`, `featureGate.ts`, `rollout-plan.md`

---

### Findings by Category

**1. Factual Accuracy — 3 discrepancies, 1 dependency violation**

**A. `dark_mode` in prod — configs vs. rollout plan disagree**

| Source | Value |
|--------|-------|
| `prod.json` | `enabled: true, percentage: 100` (fully on) |
| `rollout-plan.md` table | `50%` (gradual rollout) |

One of these is wrong. The schedule describes a week-by-week ramp to 100%, suggesting prod.json is ahead of the plan — or the plan table was never updated after the flag reached 100%.

---

**B. `new_index_engine` in staging — configs vs. rollout plan disagree**

| Source | Value |
|--------|-------|
| `staging.json` | `enabled: false, percentage: 0` (off) |
| `rollout-plan.md` table | `100%` (fully on) |

Direct contradiction. The Week 1 schedule says "Enable `new_index_engine` on staging at 100%" — if that ran, staging.json was never updated.

---

**C. `new_checkout_flow` — exists in two artifacts, missing from all three configs**

`featureGate.ts` calls `featureGate.isEnabled('new_checkout_flow')` in `applyFeatureGates`. The rollout plan lists it with values (dev: 100%, staging: 50%, prod: 0%). But the flag is absent from `dev.json`, `staging.json`, and `prod.json` entirely.

At runtime, `getFeatureFlags()` will not return this key, so `this.flags['new_checkout_flow']` will be `undefined` — `isEnabled` returns `false`, and the redirect to `/api/v2/checkout` is silently dead. The code and plan agree the flag should exist; the configs disagree by omission.

---

**D. Dependency rule violated in `staging.json`**

The rollout plan states explicitly:
> `beta_search` depends on `new_index_engine` — **never enable beta_search in an environment where new_index_engine is disabled.**

`staging.json` breaks this rule directly:
- `beta_search`: `enabled: true, percentage: 50`
- `new_index_engine`: `enabled: false, percentage: 0`

`beta_search` is active in staging on top of a disabled `new_index_engine`. This is the highest-severity finding — it's a documented rule that the current config violates.

---

**2. Representational Completeness — partial**

`dark_mode` and `new_index_engine` appear in all configs and the rollout plan, but neither is gated anywhere in `featureGate.ts`. This may be intentional (client-side only flags fetched by frontend), but it's unverifiable from these artifacts and creates an implicit assumption that isn't documented anywhere.

---

**3. Cross-Reference Redundancy — medium**

The rollout plan's "Current Status" table duplicates the config files but has drifted from them in two places (findings A and B above). The table either needs to be kept in sync with the configs or replaced with a link/automation that derives from the configs as the source of truth.

---

### Summary Table

| # | Finding | Severity | Artifacts in Conflict |
|---|---------|----------|-----------------------|
| A | `dark_mode` prod: configs say 100%, plan says 50% | High | `prod.json` ↔ `rollout-plan.md` |
| B | `new_index_engine` staging: configs say 0%, plan says 100% | High | `staging.json` ↔ `rollout-plan.md` |
| C | `new_checkout_flow` missing from all three config files | High | `featureGate.ts` + `rollout-plan.md` ↔ all JSONs |
| D | `beta_search` enabled in staging while `new_index_engine` is off | High | `staging.json` ↔ `rollout-plan.md` (dependency rule) |
| E | `dark_mode`, `new_index_engine` unrepresented in `applyFeatureGates` | Low | `featureGate.ts` ↔ all configs |

**Root cause pattern:** The configs and rollout plan were updated independently — the plan describes an intended or past state that was never reflected back into the JSON files (or vice versa). `new_checkout_flow` looks like it was added to code and docs but the config scaffolding was forgotten entirely.