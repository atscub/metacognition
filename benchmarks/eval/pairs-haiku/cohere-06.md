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

## Response B
# Consistency Review: Discrepancies Found

I've identified **6 significant discrepancies** between these artifacts:

## 🔴 Critical Issues

### 1. **Node.js Version Mismatch**
- **Workflow**: Node 20
- **Runbook**: Node 20  
- **Deploy Script**: Node **18** (`nvm use 18`)

This is the most critical — your actual deployment script uses a different Node version than documented.

### 2. **Database Migration Ordering Conflict**
- **Workflow**: Deploys to S3 → **then** runs migrations
- **Runbook**: States migrations happen **before** deployment (Step 3 before Step 4)
- **Script**: Deploys to S3 → health check → **then** runs migrations

The runbook implies migrations must complete before deployment goes live, but both automation tools run migrations *after* S3 deployment.

---

## 🟡 Missing Features

### 3. **Health Check Only in Script**
- **Script**: Includes 10 retry attempts to verify `/health` endpoint
- **Workflow**: No health check
- **Runbook**: No mention of health check

The script waits for the service to be healthy before running migrations — this critical safety check is missing from the CI workflow.

### 4. **Deploy Registry Only in Script**
- **Script**: Registers deployment with `deploy-registry.internal`
- **Workflow**: No registry call
- **Runbook**: No mention of registry

The script logs deployments to an internal registry that the workflow doesn't know about.

---

## 🟠 Environment Flexibility

### 5. **Workflow is Production-Only**
- **Script**: Accepts environment parameter (`staging`/`production`) with separate .env files
- **Workflow**: Hard-coded to production (`aws-region: us-east-1`, uses `environment: production`)
- **Runbook**: Implies staging exists (mentions "staging" in rollback section)

The workflow can't deploy to staging like the script can.

### 6. **Undocumented Rollback in Script**
- **Runbook**: References `./scripts/deploy.sh rollback`
- **Script**: Only accepts environment name (no `rollback` subcommand implemented)

The documented rollback procedure doesn't match the script's actual interface.

---

## Recommendation
These inconsistencies suggest the **script and workflow are out of sync** — likely the CI workflow is newer and the script is legacy (or vice versa). Before deploying, determine which is authoritative and update the others.

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
