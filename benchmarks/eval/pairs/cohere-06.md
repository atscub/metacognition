# Task: cohere-06 — CI/CD pipeline vs deployment docs vs deploy script

## Prompt
Review the following three artifacts for consistency. Identify any discrepancies between them.

## Artifact 1: GitHub Actions Workflow (.github/workflows/deploy.yml)

```yaml
name: Deploy to Production

on:
  push:
    branches: [main]

permissions:
  contents: read
  id-token: write

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
      - run: npm ci
      - run: npm run lint
      - run: npm test

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
      - run: npm ci
      - run: npm run build
      - uses: actions/upload-artifact@v4
        with:
          name: build-output
          path: dist/

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: build-output
          path: dist/
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-arn: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1
      - name: Deploy to S3 and invalidate CloudFront
        run: |
          aws s3 sync dist/ s3://${{ secrets.S3_BUCKET }}/ --delete
          aws cloudfront create-invalidation \
            --distribution-id ${{ secrets.CF_DISTRIBUTION_ID }} \
            --paths "/*"
      - name: Run database migrations
        run: |
          npm ci
          DATABASE_URL=${{ secrets.DATABASE_URL }} npm run migrate

  notify:
    needs: deploy
    runs-on: ubuntu-latest
    if: always()
    steps:
      - name: Send Slack notification
        uses: slackapi/slack-github-action@v1
        with:
          payload: |
            {
              "text": "Deploy ${{ needs.deploy.result }}: ${{ github.sha }}"
            }
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK }}
```

## Artifact 2: Deployment Runbook (docs/deployment-runbook.md)

```markdown
# Production Deployment Runbook

## Overview
Deployments are triggered automatically when code is merged to `main`.
The CI/CD pipeline handles testing, building, and deploying.

## Pre-Deployment Checklist
- [ ] All PR checks passing
- [ ] Code reviewed and approved
- [ ] Database migration tested on staging
- [ ] Rollback plan documented

## Deployment Steps

The automated pipeline follows this sequence:

### Step 1: Run Tests
Automated tests run using Node.js 20 on Ubuntu.
- Linting (ESLint)
- Unit & integration tests

### Step 2: Build
Production build is created and artifacts are uploaded.

### Step 3: Run Database Migrations
Database migrations run against production using `npm run migrate`.
Migrations must complete successfully before deploying new code to
ensure the database schema is ready for the new application version.

### Step 4: Deploy
Built artifacts are synced to S3 and CloudFront cache is invalidated.

### Step 5: Notify
Slack notification is sent with deployment status.

## Rollback Procedure

If issues are detected after deployment:

1. Revert the merge commit on `main`:
   ```bash
   git revert <commit-sha>
   git push origin main
   ```
2. This triggers a new deployment with the reverted code.
3. If database migrations need reverting, run:
   ```bash
   ./scripts/deploy.sh rollback
   ```

## Manual Deploy (Emergency Only)

If the CI pipeline is down, use the deploy script:
```bash
export AWS_PROFILE=production
export DEPLOY_TOKEN=$(vault read -field=token secret/deploy)
./scripts/deploy.sh production
```
```

## Artifact 3: Deploy Script (scripts/deploy.sh)

```bash
#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT="${1:-staging}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== Deploying to ${ENVIRONMENT} ==="

# Load environment variables
source "${PROJECT_ROOT}/.env.${ENVIRONMENT}"

# Ensure correct Node version
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
nvm use 18

# Install dependencies
cd "$PROJECT_ROOT"
npm ci

# Run tests
echo "Running tests..."
npm run lint
npm test

# Build
echo "Building..."
npm run build

# Deploy
echo "Deploying to S3..."
aws s3 sync dist/ "s3://${S3_BUCKET}/" --delete

echo "Invalidating CloudFront..."
aws cloudfront create-invalidation \
  --distribution-id "${CF_DISTRIBUTION_ID}" \
  --paths "/*"

# Post-deploy verification
echo "Verifying deployment..."
HEALTH_URL="${HEALTH_CHECK_URL:-https://${DOMAIN}/health}"
for i in {1..10}; do
  if curl -sf "$HEALTH_URL" > /dev/null; then
    echo "Health check passed!"
    break
  fi
  echo "Waiting for health check (attempt $i/10)..."
  sleep 10
done

# Run migrations
echo "Running database migrations..."
DATABASE_URL="${DATABASE_URL}" npm run migrate

# Notify
echo "Sending notification..."
curl -X POST "${SLACK_WEBHOOK_URL}" \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"Deployed to ${ENVIRONMENT}: $(git rev-parse --short HEAD)\"}"

# Authenticate with deploy token
echo "Registering deployment..."
curl -X POST "https://deploy-registry.internal/api/deployments" \
  -H "Authorization: Bearer ${DEPLOY_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"env\": \"${ENVIRONMENT}\", \"sha\": \"$(git rev-parse HEAD)\"}"

echo "=== Deploy complete ==="
```


## Response A
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

## Response B
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
