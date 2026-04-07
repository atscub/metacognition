I'll now work through the 10-point coherence checklist on these three artifacts:

---

## Coherence Audit Results

### 1. **Factual Accuracy** ⚠️ CRITICAL MISMATCH

| Aspect | Workflow | Runbook | Script |
|--------|----------|---------|--------|
| **Node.js version** | 20 | 20 | **18** ❌ |
| **Database migrations timing** | After S3/CloudFront deploy | After deploy | After health check ❌ |
| **AWS authentication** | OIDC role-to-arn | Not specified | AWS_PROFILE |
| **Slack webhook** | `secrets.SLACK_WEBHOOK` | Not specified | `${SLACK_WEBHOOK_URL}` |
| **Rollback mechanism** | Git revert | `./scripts/deploy.sh rollback` | Not implemented ❌ |

**Finding**: Script uses Node 18 while workflow enforces 20 — will cause runtime inconsistency. Rollback command documented but not implemented in script.

---

### 2. **Representational Completeness** ⚠️ INCOMPLETE

The script includes **extra operations not mentioned in the runbook or workflow**:
- Health check verification loop (10 attempts)
- Deploy token registration to `deploy-registry.internal`

The workflow **omits** the health check that the script implements, making the automation appear complete when it's actually missing verification.

---

### 3. **Voice Consistency** ✅ ACCEPTABLE

Each medium has appropriate voice (YAML, markdown, bash). However:
- **Runbook tone**: "If issues are detected..." (hedged)
- **Workflow tone**: Implicit assumption it works (confident)
- **Script tone**: Explicit health checks (defensive)

Mismatch in assumed reliability.

---

### 4. **Naming Coherence** ⚠️ CONTRADICTORY

| Artifact | Name/Title | Default Environment |
|----------|-----------|---------------------|
| Workflow | "Deploy to **Production**" | `main` branch (production) |
| Script | Accepts `ENVIRONMENT` param | Default: **staging** ❌ |

**Finding**: Workflow is hardcoded to production (`main` → `us-east-1`, environment: production), but script defaults to staging. Contradiction about what's actually being deployed.

---

### 5. **Framing Precision** ⚠️ MISLEADING

**Runbook states**:
> "Deployments are triggered automatically when code is merged to `main`."

**But script supports**:
```bash
./scripts/deploy.sh production  # Manual trigger
./scripts/deploy.sh staging     # Different environment
```

**Finding**: Runbook frames deployments as purely automated, but script reveals they can be manual. Framing is incomplete.

---

### 6. **Origin Fidelity** ⚠️ UNCLEAR INTENT

Three different deployment pathways are described:

1. **Workflow**: Automated via GitHub Actions (push to main)
2. **Runbook Manual Deploy**: Emergency fallback, uses `deploy.sh`
3. **Script**: Can run independently with any environment

**Question unresolved**: Is the script meant to **replace** the workflow, **supplement** it, or **be called by** it? This relationship isn't stated anywhere.

---

### 7. **Tone Calibration** ⚠️ OVERPROMISE

**Workflow/Runbook tone**:
- Present the process as bulletproof
- Minimal error handling
- CloudFront invalidation happens immediately after S3 sync

**Script reality**:
- Includes health check retry logic (10 attempts, 10s each)
- Explicitly hedges on deployment success
- More defensive

**Finding**: Workflow/Runbook tone suggests instant reliability; script tone suggests it's uncertain. Mismatch in confidence level.

---

### 8. **Category Accuracy** ⚠️ CLASSIFICATION DRIFT

The script does things not categorized in the workflow or runbook:

| Operation | Categorized As | Actually Is |
|-----------|---|---|
| `nvm use 18` | Prerequisite setup | **Configuration that conflicts with workflow** |
| Health check loop | (not listed) | **Core verification step** |
| Deploy registry POST | (not listed) | **Audit/tracking** |

**Finding**: Script implements verification and tracking steps that aren't acknowledged as part of the official deployment process.

---

### 9. **Cross-Reference Redundancy** 🔴 DANGEROUS DUPLICATION

The workflow and script both:
- Install dependencies (`npm ci`)
- Run lint and tests
- Build (`npm run build`)
- Sync to S3
- Invalidate CloudFront
- Run migrations
- Send Slack notification

**But they don't reference each other**. Is the script:
- A fallback if the workflow fails?
- An alternative path that should be kept in sync?
- Obsolete documentation?

**Finding**: Two complete implementations of the same process with **no coordination mechanism**. They will drift over time.

---

### 10. **Scope Discipline** ⚠️ MISSING CONTEXT

**Runbook includes**:
- Rollback procedure (appropriate)
- Pre-deployment checklist (appropriate)

**Runbook references but doesn't explain**:
- `./.scripts/deploy.sh rollback` — This command doesn't exist in the provided script
- `vault read -field=token` — Vault setup not explained
- Health check URLs — Not specified, assumed from `DOMAIN` env var

**Finding**: Runbook assumes knowledge of external systems (Vault, health check setup) without documenting them.

---

## Summary of Discrepancies

| Issue | Severity | Category |
|-------|----------|----------|
| Node.js version mismatch (18 vs 20) | **HIGH** | Factual Accuracy |
| Rollback command documented but not implemented | **HIGH** | Factual Accuracy |
| Default environment is staging, but workflow targets production | **HIGH** | Naming Coherence |
| Workflow/script relationship undefined | **HIGH** | Cross-Reference Redundancy |
| Health check step invisible in workflow/runbook | **MEDIUM** | Representational Completeness |
| Database migration timing differs between paths | **MEDIUM** | Factual Accuracy |
| Runbook frames deployments as fully automated; script reveals manual path | **MEDIUM** | Framing Precision |
| Two complete implementations with no sync mechanism | **MEDIUM** | Cross-Reference Redundancy |

### Recommended Fixes

1. **Unify Node versions** → Lock to 20 everywhere (workflow is the source of truth)
2. **Clarify script purpose** → Either integrate it into the workflow or explicitly document it as fallback-only
3. **Fix default environment** → Either change script default to "production" or change workflow naming
4. **Implement/remove rollback** → Either add `rollback` function to script or remove from runbook
5. **Document health check** → Add to workflow and runbook as official verification step
6. **Sync operations order** → Ensure all three use the same sequence (particularly migrations timing)