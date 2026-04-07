Running the audit systematically across all 10 coherence categories, comparing each artifact pair.

---

## Coherence Audit: Three Deployment Artifacts

### Artifacts Under Review
- **W**: `.github/workflows/deploy.yml`
- **R**: `docs/deployment-runbook.md`
- **S**: `scripts/deploy.sh`

---

### Category 1: Factual Accuracy

**Finding 1 — Node.js version conflict** `HIGH`

| Artifact | Node version |
|----------|-------------|
| W (workflow) | `node-version: "20"` |
| R (runbook) | "Node.js 20" |
| S (script) | `nvm use 18` |

W and R agree on Node 20. S uses Node 18. The script will run the build with a different runtime than the CI pipeline. This could mask compatibility bugs that only surface in CI, or vice versa.

**Finding 2 — Migration order contradicts across all three artifacts** `HIGH`

This is the most dangerous discrepancy. The three artifacts describe different orderings:

| Artifact | Migration position |
|----------|-------------------|
| W (workflow) | S3 sync → CloudFront invalidation → **migrate** (last in deploy job) |
| R (runbook) | Step 3: **Migrate** → Step 4: Deploy → Step 5: Notify |
| S (script) | S3 sync → CloudFront → health check → **migrate** (after health check) |

The runbook explicitly states: *"Migrations must complete successfully before deploying new code to ensure the database schema is ready for the new application version."* This is a deliberate safety argument — migrations-first prevents new code from running against a stale schema. But both the workflow and the script contradict it by deploying first. The three artifacts cannot all be correct.

**Finding 3 — Rollback script command doesn't work** `HIGH`

R says: `./scripts/deploy.sh rollback`

S receives its first argument as `ENVIRONMENT="${1:-staging}"`, then immediately sources `.env.rollback`. No such file exists in any documented location, and no rollback branch exists in the script. Calling the script with `rollback` would fail at the `source` line with a file-not-found error. The runbook documents a command that does not function as described.

**Finding 4 — Undocumented deploy-registry step** `MEDIUM`

S ends with a call to `deploy-registry.internal/api/deployments` using `${DEPLOY_TOKEN}`. Neither W nor R mentions this step exists. It is entirely invisible to anyone following the runbook or reading the workflow.

**Finding 5 — Health check invisible to W and R** `MEDIUM`

S performs a 10-attempt health check (polling `${HEALTH_CHECK_URL}`) between deployment and migrations. Neither W nor R acknowledges this step. If the health check fails, migrations never run — a failure mode that is undocumented.

---

### Category 2: Representational Completeness

**Finding 6 — Runbook's step sequence is missing the health check**

The runbook lists 5 steps. The script has 7 distinct phases (tests, build, deploy, health check, migrate, notify, register). Two phases — health check and deploy-registry registration — are completely absent from the runbook's representation of the pipeline.

---

### Category 4: Naming Coherence

**Finding 7 — DEPLOY_TOKEN sourced differently in R vs. S** `MEDIUM`

R (manual deploy section): `export DEPLOY_TOKEN=$(vault read -field=token secret/deploy)`

S: Loads `${DEPLOY_TOKEN}` from `source "${PROJECT_ROOT}/.env.${ENVIRONMENT}"` — no vault call.

These describe two different mechanisms for obtaining the same secret. A responder following the runbook for an emergency manual deploy would set the token via vault; the script then ignores that and reads from `.env.${ENVIRONMENT}`. If the env file doesn't have `DEPLOY_TOKEN` set, the script silently uses an empty value (or fails, depending on whether `set -u` catches it — it will, since `set -euo pipefail` is declared).

---

### Category 5: Framing Precision

**Finding 8 — Runbook frames migrations-before-deploy as the pipeline's behavior, but it isn't**

The runbook's Step 3 rationale reads: *"ensure the database schema is ready for the new application version."* This is framed as a description of how the system works, not a recommendation. But the actual workflow runs migrations after the code is already live. The runbook misdescribes the system's real behavior.

---

### Category 9: Cross-Reference Redundancy

**Finding 9 — Tests run twice in the manual path** `LOW`

S runs `npm run lint` and `npm test` before building. The runbook describes S as an emergency fallback when CI is down. If CI is down, running tests locally before deploying is reasonable. But S and W run identical test commands with no differentiation in purpose. This is defensible duplication, but it isn't acknowledged — someone maintaining the script might remove the test step as "redundant" without realizing it's the only safety net in the emergency path.

---

### Category 10: Scope Discipline

No out-of-scope content found. All three artifacts stay within the deployment domain.

---

## Summary Table

| # | Finding | Severity | Artifacts in Conflict |
|---|---------|----------|----------------------|
| 1 | Node version: 20 (W, R) vs. 18 (S) | **High** | W+R vs. S |
| 2 | Migration order: before deploy (R) vs. after deploy (W, S) | **High** | R vs. W+S |
| 3 | `./scripts/deploy.sh rollback` doesn't work | **High** | R vs. S |
| 4 | Deploy-registry step undocumented | **Medium** | S vs. W+R |
| 5 | Health check undocumented | **Medium** | S vs. W+R |
| 6 | Step count incomplete in runbook | **Medium** | R vs. S |
| 7 | DEPLOY_TOKEN via vault (R) vs. env file (S) | **Medium** | R vs. S |
| 8 | Runbook describes wrong migration order as fact | **High** | R vs. W+S |
| 9 | Test duplication unacknowledged in emergency path | **Low** | W vs. S |

---

## Recommended Fixes (in priority order)

1. **Decide the canonical migration order** and make all three artifacts agree. Given the runbook's safety argument (schema-first), the workflow and script should both be updated to run migrations before the S3 sync — not after.

2. **Fix the rollback command** in the runbook. Either add a `rollback` branch to `deploy.sh`, or replace the command with accurate instructions (e.g., revert-and-push, which is already described above it).

3. **Align Node version** — either bump the script to `nvm use 20` or update the workflow and runbook to 18. The choice should reflect what's actually tested against.

4. **Document the health check and deploy-registry steps** in the runbook's step sequence, and add them to the workflow if they belong in the automated path.

5. **Reconcile DEPLOY_TOKEN sourcing** — either the script should call vault, or the runbook should say "ensure `.env.production` contains `DEPLOY_TOKEN`."