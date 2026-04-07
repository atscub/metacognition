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