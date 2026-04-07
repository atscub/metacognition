Now I'll systematically audit the three artifacts against each other.

## Artifacts Under Review

1. **GitHub Actions Workflow** (.github/workflows/deploy.yml)
2. **Deployment Runbook** (docs/deployment-runbook.md)
3. **Deploy Script** (scripts/deploy.sh)

---

## Coherence Audit Results

### 1. **Factual Accuracy** ⚠️ HIGH DISCREPANCY

| Claim | Artifact 1 (GH Actions) | Artifact 2 (Runbook) | Artifact 3 (Script) | Reality |
|-------|---|---|---|---|
| **Node.js version** | 20 | (not specified) | **18** | ❌ **CONFLICT** |
| **Order: migrations before/after deploy?** | **BEFORE** (runs after build, before deploy step completes) | **BEFORE** | **AFTER** (health check, then migrate) | ❌ **CONFLICT** |
| **Stages** | test → build → deploy → notify | test → build → migrate → deploy → notify | test → build → deploy → health check → migrate → notify | ❌ **INCONSISTENT ORDERING** |
| **Health check** | Not present | Not mentioned | Present (10 retries, 10s interval) | ❌ **MISSING from GH Actions & Runbook** |
| **Deploy token usage** | Not present | Manual deploy only | Present in deploy script | ❌ **INCONSISTENT** |
| **Rollback mechanism** | Not present | Via git revert | Not present | ❌ **INCOMPLETE** |

**Critical Issue**: The **Node.js version mismatch (20 vs 18)** means the three artifacts will not produce the same behavior. GH Actions uses v20; the script enforces v18.

---

### 2. **Representational Completeness** ⚠️ MEDIUM ISSUES

- **GH Actions omits**:
  - Health check validation (present in script)
  - Deploy token registration (present in script)
  - Post-deploy verification step
  
- **Runbook omits**:
  - Health check procedure
  - Deploy token flow (except in emergency path)
  - Slack notification details
  
- **Script includes operations** not documented elsewhere:
  - Health check with retry logic (10 attempts, 10s interval)
  - Deploy registry registration with bearer token
  - Both are invisible to GH Actions & Runbook

**Impact**: Someone following the Runbook will not know about health checks. Someone reading GH Actions won't know deploy script registers deployments.

---

### 3. **Voice Consistency** ✓ ACCEPTABLE

- **GH Actions**: Technical, procedural (YAML)
- **Runbook**: Technical, instructional (Markdown checklist)
- **Script**: Technical, operational (Bash comments)

Each uses appropriate voice for its medium. No conflicts.

---

### 4. **Naming Coherence** ⚠️ MINOR ISSUES

| Concept | GH Actions | Runbook | Script |
|---------|-----------|---------|--------|
| **Deploy job name** | `deploy` | (Step 4: Deploy) | "Deploying to..." |
| **Notify job name** | `notify` | Step 5: Notify | (curl to Slack) |
| **Environment** | `environment: production` | Plural: "Deployments" | `ENVIRONMENT` variable (staging/production) |
| **Artifact storage** | `build-output` → `dist/` | "Built artifacts" | `dist/` |

**Minor inconsistency**: GH Actions defines `environment: production` but script accepts `ENVIRONMENT="${1:-staging}"` (defaults to staging). The Runbook describes production-only flow.

---

### 5. **Framing Precision** ⚠️ MEDIUM ISSUE

- **GH Actions frames** it as: "Automated on main push, follows strict sequence"
- **Runbook frames** it as: "Automated pipeline handles testing, building, deploying" but then documents **manual rollback** as primary recovery
- **Script frames** it as: Flexible (staging or production via argument)

**Discrepancy**: The Runbook says deployments are automatic on `main` merge, but then documents manual `git revert` as the rollback. If the pipeline is truly automatic, why would you manually revert and re-trigger? This framing gap suggests the Runbook describes automation but the actual safety procedure is manual control.

---

### 6. **Origin Fidelity** ✓ ACCEPTABLE

No contradictions in stated intent, though origins are not explicitly stated. Each artifact reflects operational deployment concerns.

---

### 7. **Tone Calibration** ⚠️ MINOR ISSUE

- **GH Actions**: Matter-of-fact (steps just execute)
- **Runbook**: Careful, procedural (checklists, rollback plans)
- **Script**: Confident (assumes environment variables are set, doesn't validate)

**Issue**: Script has insufficient error handling for critical operations (no validation of `S3_BUCKET`, `CF_DISTRIBUTION_ID`, etc. before use). Runbook suggests a safety-first approach, but the script is more cavalier.

---

### 8. **Category Accuracy** ✓ MOSTLY CORRECT

- GH Actions = workflow automation (correct)
- Runbook = human-readable procedures (correct)
- Script = executable deployment tool (correct)

One edge case: Script uses `nvm use 18` to enforce Node version, but this contradicts GH Actions' use of setup-node v20.

---

### 9. **Cross-Reference Redundancy** ⚠️ MEDIUM ISSUE

- **GH Actions → Runbook**: Runbook Step 3 describes build, Step 4 describes deploy. These roughly match GH Actions jobs but with **different migration ordering**.
- **Script and GH Actions**: Both deploy to S3 and invalidate CloudFront (identical), but **different migration timing and health checks**.
- **Runbook and Script**: Runbook mentions rollback script `./scripts/deploy.sh rollback` but the script doesn't implement a `rollback` subcommand.

**Broken reference**: Runbook says to run `./scripts/deploy.sh rollback` but the script only accepts `production` or `staging` as first argument.

---

### 10. **Scope Discipline** ✓ ACCEPTABLE

All three stay focused on deployment mechanics, not framework philosophy. No unnecessary ecosystem explanation.

---

## Summary of Critical Discrepancies

| Issue | Severity | Artifacts Affected |
|-------|----------|-------------------|
| **Node.js version mismatch (20 vs 18)** | 🔴 CRITICAL | GH Actions vs Script |
| **Migration execution order (before vs after deploy)** | 🔴 CRITICAL | GH Actions vs Script vs Runbook |
| **Missing rollback subcommand in script** | 🔴 CRITICAL | Runbook references non-existent feature |
| **Health check not documented in GH Actions or Runbook** | 🟠 HIGH | Incomplete specification |
| **Deploy token registration not in GH Actions** | 🟠 HIGH | Incomplete specification |
| **Unsafe script (no env var validation)** | 🟠 HIGH | Script robustness |
| **Automatic vs manual control framing** | 🟡 MEDIUM | Runbook's control model unclear |

Would you like me to create a detailed report with specific fixes, or prioritize which discrepancies to address first?