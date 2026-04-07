## Coherence Audit: Deploy Artifacts

Comparing deploy.yml, deployment-runbook.md, and deploy.sh across all 10 categories.

---

### Findings by Category

#### 1. Factual Accuracy — 3 failures

**A. Node.js version conflict (HIGH)**
- `deploy.yml`: `node-version: "20"`
- `deploy.sh`: `nvm use 18`

The CI pipeline and manual deploy script use different Node versions. Node 18 hit end-of-life in April 2025, making the script's version not just inconsistent but outdated.

**B. Migration ordering mismatch (HIGH)**
- Runbook Step 3 is "Run Database Migrations," Step 4 is "Deploy (S3 sync)." The runbook explicitly justifies this order: *"Migrations must complete successfully before deploying new code to ensure the database schema is ready."*
- `deploy.yml`: S3 sync → CloudFront invalidation → **then** migrations (end of `deploy` job)
- `deploy.sh`: S3 sync → CloudFront → health check → **then** migrations

Both the workflow and script contradict the runbook's stated rationale. If the runbook's reasoning is correct (schema must be ready before new code serves traffic), the workflow and script have a real deployment bug.

**C. Rollback script argument nonexistent (HIGH)**
- Runbook: `./scripts/deploy.sh rollback`
- `deploy.sh`: accepts `${1:-staging}` as `ENVIRONMENT`. There is no branch on the value — `rollback` would be treated as an environment name, not a rollback command, and the script would attempt to deploy to an environment called "rollback."

---

#### 2. Representational Completeness — 2 gaps

**D. Health check absent from workflow and runbook**
- `deploy.sh` has a 10-attempt health check loop with 10-second retries after CloudFront invalidation.
- `deploy.yml`: no health check step.
- Runbook: not mentioned.

A health check that exists only in the manual path creates inconsistency: automated deploys go live without verification, manual deploys don't.

**E. Deploy registry registration absent from workflow and runbook**
- `deploy.sh` POSTs to `https://deploy-registry.internal/api/deployments` using `${DEPLOY_TOKEN}`.
- `deploy.yml`: no `DEPLOY_TOKEN` secret referenced, no registry call.
- Runbook: not mentioned.

Either this registration is required (and the workflow is missing it) or it's dead infrastructure that the script still references.

---

#### 4. Naming Coherence — 1 failure

**F. Slack webhook variable name inconsistency**
- `deploy.yml`: `env.SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK }}`
- `deploy.sh`: `${SLACK_WEBHOOK_URL}`

The secret is named `SLACK_WEBHOOK` in the workflow but `SLACK_WEBHOOK_URL` in the script. If both eventually read from the same environment variable convention or Vault path, one of them has the wrong name.

---

#### 5. Framing Precision — 1 failure

**G. Runbook step sequence misrepresents actual pipeline**

The runbook labels itself as describing "The automated pipeline" but its step ordering (migrations before deploy) contradicts what the pipeline actually does. A reader following the runbook to understand or debug the CI pipeline would have an incorrect mental model of the sequence.

---

#### 9. Cross-Reference Redundancy — acceptable

Both the workflow (Slack action) and script (curl) send Slack notifications. These serve different execution paths (automated vs. manual), so the duplication is justified. No issue here.

---

### Severity Summary

| # | Discrepancy | Severity | Location |
|---|-------------|----------|----------|
| A | Node 18 vs Node 20 | High | deploy.sh vs deploy.yml |
| B | Migrations run after deploy, runbook says before | High | All three artifacts |
| C | `deploy.sh rollback` argument doesn't exist | High | deploy.sh vs runbook |
| D | Health check only in deploy.sh | Medium | deploy.sh vs deploy.yml/runbook |
| E | Deploy registry only in deploy.sh | Medium | deploy.sh vs deploy.yml/runbook |
| F | `SLACK_WEBHOOK` vs `SLACK_WEBHOOK_URL` | Medium | deploy.yml vs deploy.sh |
| G | Runbook step order misrepresents CI sequence | Medium | runbook vs deploy.yml |

---

### Root Cause Pattern

The script and the CI workflow appear to have diverged over time. The script accumulated features (health check, registry registration) that were never added to the workflow, and the runbook was never updated to reflect the actual execution order. The most operationally dangerous discrepancy is **B** (migration order): the runbook describes the safe approach, but neither automated artifact implements it.