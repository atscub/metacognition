# Task: cohere-04 — Feature flags across environments

## Prompt
Review the following three artifacts for consistency. Identify any discrepancies between them.

## Artifact 1: Feature Flag Configs

### config/flags/dev.json
```json
{
  "flags": {
    "dark_mode": {
      "enabled": true,
      "percentage": 100
    },
    "beta_search": {
      "enabled": true,
      "percentage": 100
    },
    "new_index_engine": {
      "enabled": true,
      "percentage": 100
    },
    "compact_sidebar": {
      "enabled": true,
      "percentage": 100
    },
    "ai_suggestions": {
      "enabled": false,
      "percentage": 0
    }
  }
}
```

### config/flags/staging.json
```json
{
  "flags": {
    "dark_mode": {
      "enabled": true,
      "percentage": 100
    },
    "beta_search": {
      "enabled": true,
      "percentage": 50
    },
    "new_index_engine": {
      "enabled": false,
      "percentage": 0
    },
    "compact_sidebar": {
      "enabled": true,
      "percentage": 100
    },
    "ai_suggestions": {
      "enabled": false,
      "percentage": 0
    }
  }
}
```

### config/flags/prod.json
```json
{
  "flags": {
    "dark_mode": {
      "enabled": true,
      "percentage": 100
    },
    "beta_search": {
      "enabled": false,
      "percentage": 0
    },
    "new_index_engine": {
      "enabled": false,
      "percentage": 0
    },
    "compact_sidebar": {
      "enabled": true,
      "percentage": 100
    },
    "ai_suggestions": {
      "enabled": false,
      "percentage": 0
    }
  }
}
```

## Artifact 2: Application Code (src/features/featureGate.ts)

```typescript
import { getFeatureFlags } from '../config/flagLoader';
import { getCurrentUser } from '../auth/session';

interface FeatureFlag {
  enabled: boolean;
  percentage: number;
}

class FeatureGate {
  private flags: Record<string, FeatureFlag>;

  constructor() {
    this.flags = getFeatureFlags();
  }

  isEnabled(flagName: string): boolean {
    const flag = this.flags[flagName];
    if (!flag || !flag.enabled) return false;
    if (flag.percentage >= 100) return true;

    const user = getCurrentUser();
    const hash = this.hashUserId(user.id);
    return (hash % 100) < flag.percentage;
  }

  private hashUserId(userId: string): number {
    let hash = 0;
    for (let i = 0; i < userId.length; i++) {
      const char = userId.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash |= 0;
    }
    return Math.abs(hash);
  }
}

export const featureGate = new FeatureGate();

// Usage in route handlers
export function applyFeatureGates(app: Express) {
  app.get('/api/search', (req, res, next) => {
    if (!featureGate.isEnabled('beta_search')) {
      return res.status(404).json({ error: 'Not found' });
    }
    next();
  });

  app.get('/api/suggestions', (req, res, next) => {
    if (!featureGate.isEnabled('ai_suggestions')) {
      return res.status(404).json({ error: 'Not found' });
    }
    next();
  });

  app.post('/api/checkout', (req, res, next) => {
    if (featureGate.isEnabled('new_checkout_flow')) {
      return res.redirect(307, '/api/v2/checkout');
    }
    next();
  });

  app.get('/api/sidebar/compact', (req, res, next) => {
    if (!featureGate.isEnabled('compact_sidebar')) {
      return res.status(404).json({ error: 'Not found' });
    }
    next();
  });
}
```

## Artifact 3: Rollout Plan (docs/rollout-plan.md)

```markdown
# Feature Rollout Plan — Q1 2024

## Current Status

| Feature            | Dev    | Staging | Prod         | Notes                               |
|--------------------|--------|---------|--------------|-------------------------------------|
| dark_mode          | 100%   | 100%    | 50%          | Gradual rollout, monitor perf       |
| beta_search        | 100%   | 50%     | 0% (off)     | Depends on new_index_engine         |
| new_index_engine   | 100%   | 100%    | 0% (off)     | Waiting on infra approval           |
| compact_sidebar    | 100%   | 100%    | 100%         | Fully rolled out                    |
| ai_suggestions     | 0%     | 0%      | 0%           | Blocked on vendor contract          |
| new_checkout_flow  | 100%   | 50%     | 0%           | In A/B testing on staging           |

## Rollout Schedule

### Week 1 (Jan 15)
- Enable `new_index_engine` on staging at 100%
- Begin `dark_mode` prod rollout at 50%

### Week 2 (Jan 22)
- If metrics OK, enable `beta_search` on staging at 50%
- `dark_mode` prod to 75%

### Week 3 (Jan 29)
- `dark_mode` prod to 100%
- `beta_search` staging to 100%

### Week 4 (Feb 5)
- `beta_search` prod at 25%
- `new_checkout_flow` staging to 100%

## Dependencies

- `beta_search` depends on `new_index_engine` — never enable beta_search
  in an environment where new_index_engine is disabled.
- `ai_suggestions` blocked on external vendor (Acme AI) contract signing.
```


## Response A
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

## Response B
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

---
Score each response on the following metrics (0-3):

| Metric | Response A | Response B |
|---|---|---|
| Ungrounded claims | | |
| Assumption acknowledgment | | |
| Alternative consideration | | |
| Error detection | | |
| Rework cycles | | |
| Confidence calibration | | |
| Final correctness | | |
| **Total** | | |
