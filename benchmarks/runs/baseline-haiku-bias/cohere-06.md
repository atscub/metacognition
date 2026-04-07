# Consistency Review

I've identified **several significant discrepancies** between these three artifacts:

## 🔴 Critical Discrepancies

### 1. **Database Migration Timing** (Order Conflict)
| Artifact | Timing |
|----------|--------|
| **Workflow** | Migrations run **AFTER** S3 sync + CloudFront invalidation |
| **Runbook** | Migrations run **BEFORE** S3 sync (Step 3 before Step 4) |
| **Script** | Migrations run **AFTER** S3 sync + CloudFront invalidation |

**Issue**: The runbook explicitly states *"Migrations must complete successfully before deploying new code"* but both the workflow and script do the opposite. This is a **critical ordering problem**—the new code is deployed to S3 before the database schema is ready.

### 2. **Node.js Version Mismatch**
| Artifact | Version |
|----------|---------|
| **Workflow** | Node 20 |
| **Script** | Node 18 (via nvm) |
| **Runbook** | Not specified |

## 🟡 Major Discrepancies

### 3. **Rollback Command Missing from Script**
- **Runbook** documents: `./scripts/deploy.sh rollback`
- **Script** doesn't support a `rollback` subcommand—it only accepts environment names

### 4. **Features Missing from Workflow/Runbook**
The **script** includes features not mentioned in the other two:
- Health check verification (10 attempts, 10s delay between)
- Deploy token registration to internal registry
- These are executed but completely undocumented

### 5. **Deploy Script Parameter Inconsistency**
- **Runbook** shows: `./scripts/deploy.sh production`
- **Script** defaults to `staging` if no arg provided
- Calling without args deploys to staging, not production (dangerous default)

### 6. **Environment Variable Handling Differs**
| Artifact | Method |
|----------|--------|
| **Workflow** | GitHub Secrets (`${{ secrets.* }}`) |
| **Script** | .env files (`${PROJECT_ROOT}/.env.${ENVIRONMENT}`) |
| **Runbook** | Ambiguous; mentions vault for deploy token |

---

## Summary Table

| Issue | Severity | Artifacts |
|-------|----------|-----------|
| Migration timing | CRITICAL | Workflow ≠ Runbook |
| Node version | HIGH | Script (18) ≠ Workflow (20) |
| Rollback command | HIGH | Runbook documents, Script lacks |
| Undocumented features | MEDIUM | Script has health check + registry, others don't |
| Default environment | MEDIUM | Script defaults to staging, unclear in runbook |
| Env var source | MEDIUM | Workflow (secrets) vs Script (.env files) |

**Recommendation**: Align these artifacts, starting with the migration ordering (decide: before or after S3 deploy?) and the Node version.