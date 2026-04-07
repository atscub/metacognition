## Socratic Audit Before Answering

Running the bias checklist explicitly before touching the options:

**Complexity bias check** — The question frames this as designing a "production-grade distributed task scheduling system." Let me test whether that framing matches the actual workload:

- Three independent jobs. No dependencies between them. No branching logic. No human-in-the-loop. No multi-step DAGs. The longest takes 4 minutes.
- The current problem is a single point of failure on one EC2 instance — not a scheduling problem, not an orchestration problem.

**Anchoring check** — Options A and B are listed first with rich feature descriptions. That creates pull toward the sophisticated end. The question also leads with the VP's mandate ("cloud-native, observable, horizontally scalable"), which primes for "impressive" over "appropriate."

**Authority/sycophancy check** — There's pressure to recommend something that sounds credible to a VP of Engineering. I'll flag where the organizational framing is doing work that the technical problem doesn't justify.

**Assumption inventory:**
1. Assumed: Complex orchestration tools handle complex problems better. True. But the inverse — simple tools for simple problems — is also true.
2. Assumed: "Production-grade" means sophisticated. It actually means reliable, observable, maintainable.
3. Assumed: Diane's mandate requires heavyweight infrastructure. It doesn't — K8s CronJobs are cloud-native, observable, and horizontally scalable.

---

## Recommendation: Option D — Kubernetes CronJobs

This is the correct answer, and I want to be direct about why the other options are not.

### The core diagnosis

The actual problem statement is: *three independent scripts run on a schedule, currently on a single EC2 instance that can fail.* That is a SPOF problem, not an orchestration problem. The solution shape should match the problem shape.

Airflow and Temporal are designed for problems you don't have: multi-step DAGs with inter-task dependencies, complex retry topologies, stateful long-running workflows, human approval gates. Reaching for them here is the engineering equivalent of using a freight train to deliver a letter because "it's more reliable than a bicycle."

### Why D satisfies every stated requirement

**Diane's mandate — cloud-native, observable, horizontally scalable:**

| Mandate | How CronJobs satisfy it |
|---------|------------------------|
| Cloud-native | Native K8s resource, managed by the control plane you already run |
| Observable | Pod logs → Datadog. Job success/failure → Datadog K8s integration. Alerting → PagerDuty via existing Datadog alert routing |
| Horizontally scalable | Each job runs in its own pod; node affinity, resource limits, and parallelism are all first-class K8s controls |

**The SPOF concern:** CronJobs run on the EKS cluster. If a node dies, the scheduler reschedules on another node. The single EC2 dependency is gone.

**Job-specific implementation:**

```yaml
# Job 1: DB Backup — must succeed, alert on failure
apiVersion: batch/v1
kind: CronJob
metadata:
  name: db-backup
spec:
  schedule: "0 2 * * *"
  concurrencyPolicy: Forbid          # never run two at once
  failedJobsHistoryLimit: 3
  successfulJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 2                # retry twice before marking failed
      activeDeadlineSeconds: 900     # kill if it runs > 15 min
      template:
        spec:
          restartPolicy: OnFailure
          containers:
          - name: backup
            image: your-backup-image:tag
            env:
            - name: PGPASSWORD
              valueFrom:
                secretKeyRef:
                  name: rds-credentials
                  key: password
```

The PagerDuty alert path: Datadog monitors `kubernetes.job.failed` metric → alert fires → PagerDuty. This is already wired in your stack. No new tooling required.

For the weekly report (`concurrencyPolicy: Forbid`, `backoffLimit: 0` — if it fails Monday, don't retry automatically; a human re-runs Tuesday as described).

### Why each alternative fails the complexity test

**Option A — Airflow:**
- Adds: dedicated PostgreSQL metadata DB, Redis, Celery workers, webserver pod, scheduler pod. Minimum 5+ new pods.
- Your SRE team now owns an Airflow cluster *in addition to* everything else.
- A pg_dump DAG in Airflow is one task. You'd be operating a distributed workflow engine to run a single-task DAG. That is not an engineering win — it's overhead that scales with your team's attention.
- Appropriate when: you have 20+ interdependent data pipeline tasks, data engineers who will author DAGs daily, or SLA dependency tracking across teams.

**Option B — Temporal:**
- Even heavier: Temporal server cluster, Cassandra or PostgreSQL persistence, SDK integration in your job code.
- Temporal's value is durable execution of *multi-step workflows where steps can fail independently and resume*. A pg_dump-and-upload has two steps. You don't need saga patterns.
- Appropriate when: you have long-running business processes (order fulfillment, async approval chains, multi-service sagas) where a failure mid-workflow must resume from that exact step.

**Option C — Step Functions + EventBridge:**
- Lower operational burden than A/B, genuinely serverless.
- But: introduces a second infrastructure paradigm (serverless + K8s), increases AWS coupling beyond what you already have, and adds a layer of IAM role/policy management your SRE team must own.
- For three simple sequential scripts, the visual workflow editor and branching support are features you will never use.
- Appropriate when: the team is already heavily invested in Lambda/serverless patterns, or the jobs themselves need to call AWS services with native SDK integrations at each step.

### The organizational framing issue

The question as posed creates a false equivalence by listing all four options as if they're comparably matched to the problem. They're not. Presenting this as "four credible options" to a VP may itself be a mistake — it implies the problem is complex enough to warrant a complex solution.

A more accurate framing for Diane: *"The SPOF risk is real and we should fix it. The fix is migrating these three jobs to Kubernetes CronJobs, which meets all three of your mandates and adds zero new infrastructure for the SRE team to own."*

### When to revisit this decision

Kubernetes CronJobs become the wrong tool if:
- You need to run 20+ interdependent jobs with fan-out/fan-in dependencies
- Jobs need to coordinate shared state mid-execution
- Non-engineers need a self-service UI to create or modify schedules
- You're building a data pipeline where task lineage and data quality checks matter

None of those conditions exist now. If they emerge, migrate then — with actual requirements driving the decision rather than anticipated future complexity.

### Summary

| Criterion | CronJobs (D) | Step Functions (C) | Airflow (A) | Temporal (B) |
|-----------|-------------|-------------------|-------------|--------------|
| Fits actual problem | **Yes** | Overfitted | Severely overfitted | Severely overfitted |
| New infra to operate | **None** | IAM/EventBridge | PG + Redis + 5+ pods | Server cluster + DB |
| SRE burden | **Low** | Low-medium | High | High |
| Meets "cloud-native" | **Yes** | Yes | Yes | Yes |
| Meets "observable" | **Yes** (Datadog K8s) | Yes (CloudWatch) | Yes (own UI) | Yes (own UI) |
| Time to implement | **~1 day** | 2-3 days | 1-2 weeks | 2-3 weeks |
| Right tool for 3 cron jobs | **Yes** | Marginal | No | No |

Recommend D. Implement it cleanly with proper resource limits, secret management via K8s Secrets, and Datadog alert routing for the backup job. The result is more reliable than the EC2 instance, fully observable, and adds zero operational surface area for your SRE team.