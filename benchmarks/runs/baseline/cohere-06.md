Here are the discrepancies I found:

---

## 1. Node.js Version Mismatch

| Artifact | Version |
|---|---|
| GitHub Actions | Node.js **20** |
| deploy.sh | `nvm use` **18** |

The CI pipeline and manual deploy script will behave differently. Any Node 20-specific behavior in tests/build won't be caught by manual deploys.

---

## 2. Migration Order Is Inverted

This is the most dangerous discrepancy.

**Runbook (Step 3 → Step 4):** Migrations run *before* deploying new code. The runbook explicitly justifies this: *"ensure the database schema is ready for the new application version."*

**GitHub Actions (deploy job):** S3 sync + CloudFront invalidation run *first*, then migrations.

**deploy.sh:** S3 sync → CloudFront → health check → *then* migrations (migrations run last, after the health check even).

The GitHub Actions workflow and deploy.sh both run new code before the schema is ready, directly contradicting the runbook's stated rationale. This is a correctness bug with potential data integrity consequences.

---

## 3. Health Check Exists Only in deploy.sh

The deploy script polls `${HEALTH_CHECK_URL}` (10 attempts, 10s apart) after the S3 sync. Neither the GitHub Actions workflow nor the runbook mention a health check step. The automated pipeline has no equivalent verification before declaring success.

---

## 4. Slack Notification Format Differs

| Artifact | SHA Format |
|---|---|
| GitHub Actions | Full SHA (`${{ github.sha }}`) |
| deploy.sh | Short SHA (`git rev-parse --short HEAD`) |

Minor, but the notifications from CI and manual deploys won't be consistent.

---

## 5. Deployment Registry Call Absent from CI

deploy.sh POSTs to `deploy-registry.internal/api/deployments` with a `DEPLOY_TOKEN`. This step doesn't exist in the GitHub Actions workflow, so automated deploys are never registered there.

---

## Summary by Severity

| Severity | Discrepancy |
|---|---|
| **Critical** | Migration runs after deploy in CI and deploy.sh, contradicting runbook |
| **High** | Node.js 18 vs 20 between CI and manual deploy |
| **Medium** | Health check only in deploy.sh, missing from CI pipeline |
| **Low** | Deployment registry call missing from CI |
| **Low** | SHA format differs in Slack notifications |