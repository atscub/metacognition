**Coherence Audit — Feature Flag System**

I'll work through the 10 categories, comparing each artifact against the others.

---

## Step 1: Identify the Parts

- **Configs** (dev/staging/prod): ground truth for flag state
- **Code** (`featureGate.ts`): enforcement logic + route gates
- **Rollout plan**: stated intent, percentages, and dependency rules

---

## Step 2: Checklist Findings

### 1. Factual Accuracy — 3 conflicts

**A. `dark_mode` prod value:**
| Source | Value |
|---|---|
| `prod.json` | `enabled: true, percentage: 100` |
| Rollout plan table | `50%` — "Gradual rollout, monitor perf" |

The config and the plan directly contradict each other.

**B. `new_index_engine` staging value:**
| Source | Value |
|---|---|
| `staging.json` | `enabled: false, percentage: 0` |
| Rollout plan table | `100%` |

Opposite states. The schedule (Week 1: "Enable `new_index_engine` on staging at 100%") implies this should have already happened — either the config was never updated after Week 1, or the plan was never executed.

**C. `new_checkout_flow` — missing from all config files:**
| Source | State |
|---|---|
| `prod.json`, `staging.json`, `dev.json` | flag does not exist |
| `featureGate.ts` (`applyFeatureGates`) | `featureGate.isEnabled('new_checkout_flow')` — actively checked |
| Rollout plan table | dev 100%, staging 50%, prod 0% |

The code and plan agree this flag exists. The configs are missing it entirely. In production, `isEnabled('new_checkout_flow')` will silently return `false` (the `!flag` branch), meaning the redirect to `/api/v2/checkout` never fires — but no error surfaces.

---

### 2. Representational Completeness — 1 gap

`dark_mode` and `new_index_engine` appear in all three configs and the rollout plan, but have **no enforcement in `applyFeatureGates`**. Every other gated flag (`beta_search`, `ai_suggestions`, `compact_sidebar`, `new_checkout_flow`) has a corresponding route gate. This may be intentional (dark_mode is likely client-side; new_index_engine may be gated deeper in the stack), but neither the code nor the docs acknowledge the asymmetry.

---

### 3. Dependency Rule Violation — 1 policy breach

The rollout plan states explicitly:

> `beta_search` depends on `new_index_engine` — **never enable beta_search in an environment where new_index_engine is disabled.**

Current state in `staging.json`:
- `new_index_engine`: `enabled: false, percentage: 0`
- `beta_search`: `enabled: true, percentage: 50`

This is a direct violation of the stated dependency rule. The `FeatureGate` class has no enforcement of this constraint — it evaluates flags independently. The rule only exists in prose.

---

### 4. Naming Coherence — clean

All flag names are consistent across artifacts where they co-appear. No renames or aliasing.

---

### 5–10: No significant findings

Voice, framing, origin, tone, category, cross-reference redundancy, and scope are all coherent within and across artifacts.

---

## Summary of Discrepancies

| # | Severity | Finding |
|---|---|---|
| 1 | **High** | `dark_mode` prod: config=100%, rollout plan=50% — one is stale |
| 2 | **High** | `new_index_engine` staging: config=0%, rollout plan=100% — Week 1 action may be unexecuted |
| 3 | **High** | `new_checkout_flow` exists in code + plan but is absent from all three config files — silent no-op in production |
| 4 | **High** | Staging violates the `beta_search → new_index_engine` dependency rule declared in the rollout plan |
| 5 | **Low** | `dark_mode` and `new_index_engine` have no route gate in `applyFeatureGates` — possibly intentional but undocumented |

**Root pattern:** The rollout plan and configs have drifted apart. Either the configs weren't updated after Week 1 actions, or the plan was written ahead of actual execution and the states were never reconciled. The `new_checkout_flow` gap suggests the config files may be the lagging artifact — the plan and code both assume it exists.