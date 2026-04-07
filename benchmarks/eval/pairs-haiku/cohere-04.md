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

## Response B
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
