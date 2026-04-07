Here are the discrepancies I found:

## Discrepancy 1: Node.js version mismatch (Critical)

| Artifact | Node version |
|---|---|
| GitHub Actions | 20 |
| Runbook | 20 (matches Actions) |
| deploy.sh | **18** (`nvm use 18`) |

The deploy script will use a different Node version than CI, which can cause silent compatibility bugs.

## Discrepancy 2: Migration order reversed (Critical)

| Artifact | Order |
|---|---|
| Runbook | Migrations (Step 3) → Deploy to S3 (Step 4) |
| GitHub Actions | Deploy to S3 → Migrations |
| deploy.sh | Deploy to S3 → Migrations |

The runbook explicitly justifies its order: *"Migrations must complete before deploying new code to ensure the database schema is ready."* The Actions workflow and deploy script do the opposite — they ship code that may reference schema changes before those changes exist.

## Discrepancy 3: Missing Node.js setup in deploy job (Bug)

The GitHub Actions `deploy` job runs `npm ci` and `npm run migrate` but has no `actions/setup-node` step. The `test` and `build` jobs both set it up, but `deploy` does not. This will likely fail on the runner's default Node version (which may not be 20).

## Discrepancy 4: Health check exists only in deploy.sh

The deploy script performs a 10-attempt health check loop after pushing to S3. Neither the Actions workflow nor the runbook mention this step. The runbook's deployment sequence omits it entirely.

## Discrepancy 5: Slack notification format differs

| Artifact | SHA format |
|---|---|
| GitHub Actions | Full SHA via `${{ github.sha }}` |
| deploy.sh | Short SHA via `git rev-parse --short HEAD` |

Minor, but the notifications will be inconsistent between automated and manual deploys.

## Discrepancy 6: DEPLOY_TOKEN not wired into Actions

The runbook's manual deploy procedure uses `DEPLOY_TOKEN` (sourced from Vault). The deploy script uses `${DEPLOY_TOKEN}` to register with `deploy-registry.internal`. The GitHub Actions workflow has no `DEPLOY_TOKEN` secret, meaning automated deploys never register with the deploy registry — only manual deploys do.

---

**Highest-priority fix:** The migration order (Discrepancy 2) is a correctness issue that could cause production errors. The missing Node.js setup (Discrepancy 3) would cause the automated pipeline to fail on migrations. Both should be addressed before the next deploy.