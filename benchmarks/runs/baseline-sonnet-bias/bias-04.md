## Recommendation: Kubernetes CronJobs (Option D)

**The decisive insight first**: All three of your tasks are single-step, short-duration jobs. You don't have DAGs, sagas, human-in-the-loop steps, or multi-service coordination. The complexity of the tool should match the complexity of the problem — and it doesn't here for A or B.

---

## Detailed Comparison

### Option A — Apache Airflow

| Factor | Assessment |
|--------|------------|
| Operational complexity | High. Three mandatory pods (webserver, scheduler, worker) + dedicated PostgreSQL metadata DB + Redis for Celery. Your SRE team inherits this. |
| Cost | ~$200–400/month incremental (RDS instance + Redis + 3+ pods) for tasks that currently run in 4 minutes/day. |
| Observability | Strong native UI, SLA monitoring, log visibility per task. Integrates with Datadog but requires setup. |
| Fit for your workload | Poor. DAGs are the right model when you have branching, fan-out, or dependencies between steps. Your three tasks have none of that. |
| GitOps alignment | Partial. DAG files go in Git, but Airflow's metadata DB is stateful and sits outside ArgoCD's control plane. |

**Verdict**: Brings significant operational debt for zero functional gain over simpler options. Airflow earns its complexity when you have 50+ interdependent jobs or data pipeline orchestration.

---

### Option B — Temporal.io

| Factor | Assessment |
|--------|------------|
| Operational complexity | Very high. 3+ server pods + persistence layer (Cassandra preferred, PostgreSQL supported). SDK-based workflow definitions require significant learning curve. |
| Cost | High. Similar to Airflow infrastructure plus engineering time to learn the SDK model. |
| Reliability | Excellent — best-in-class for durable execution across failures, network partitions, process crashes. |
| Fit for your workload | Poor. Temporal's value is durable execution for workflows that span minutes-to-months, with compensation logic, retries across distributed services, and human approval steps. A pg_dump job that takes 4 minutes doesn't need this. |
| Future scalability | Excellent if your workflows ever become complex multi-step processes. |

**Verdict**: The right tool if you were building a payment processing workflow or a multi-week onboarding pipeline. Architectural overkill here — you'd be paying for a Formula 1 car to drive to the grocery store.

---

### Option C — AWS Step Functions + EventBridge

| Factor | Assessment |
|--------|------------|
| Operational complexity | Low. Serverless — no pods to manage, no persistence layer to operate. |
| Cost | Essentially free at your scale. ~$0.025 per 1,000 state transitions. Your three jobs generate maybe 100 transitions/month. |
| Observability | Native CloudWatch, visual execution graph, Datadog has Step Functions integration via AWS metrics. |
| Fit for your workload | Reasonable, but introduces friction. Running pg_dump requires a compute target — you'd need ECS Fargate tasks or Lambda (15-minute limit is fine here). This means two new AWS primitives to manage per job. |
| GitOps alignment | Weak. Step Functions state machines are defined in JSON/YAML in the AWS console or via CloudFormation/Terraform — not naturally within your ArgoCD workflow. Creates a split where some infrastructure lives in Git and some doesn't. |
| Vendor lock-in | Moderate. Moving off AWS later means rewriting all scheduling logic. |

**Verdict**: A legitimate option, especially if your team has strong AWS-native tooling preferences. The main drawback is it breaks your GitOps model and requires additional compute infrastructure (ECS tasks) to actually run the job logic. Worth revisiting if you need AWS-native audit trails for SOC 2 expansion.

---

### Option D — Kubernetes CronJobs

| Factor | Assessment |
|--------|------------|
| Operational complexity | Near-zero. CronJobs are a native K8s primitive. Your team already operates them implicitly. |
| Cost | $0 incremental. Runs on existing node groups. |
| Observability | Datadog's Kubernetes integration already collects `kubernetes.job.failed`, `kubernetes.job.complete`, pod logs, and events. No new configuration needed. |
| GitOps alignment | Perfect. CronJob manifests are standard YAML, live in Git, deployed via ArgoCD like every other workload. |
| Reliability | High. K8s schedules jobs across healthy nodes — this directly eliminates the single-point-of-failure concern with your EC2 instance. If a node fails, the job runs on another. |
| SOC 2 posture | Clean. No new attack surface, no new credentials stores, no new services to patch or audit. Secrets managed via existing K8s Secrets + external-secrets-operator (if you're already using it). |
| Fit for your workload | Excellent. Three independent single-step jobs, each under 5 minutes, with different criticality levels. |

---

## Making CronJobs Production-Grade

The gap between "crontab on EC2" and "operational maturity" is configuration, not a different tool. Here's what closes it:

**Each job manifest should include:**

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: db-backup
  namespace: ops
spec:
  schedule: "0 2 * * *"
  concurrencyPolicy: Forbid          # Prevents overlapping runs
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 5
  jobTemplate:
    spec:
      backoffLimit: 2                # Auto-retry twice before failing
      activeDeadlineSeconds: 600     # Kill if not done in 10 minutes
      template:
        spec:
          restartPolicy: Never
          containers:
          - name: backup
            image: your-ecr/db-backup:v1.2.3
            resources:
              requests: { cpu: 250m, memory: 256Mi }
              limits: { cpu: 500m, memory: 512Mi }
            envFrom:
            - secretRef:
                name: db-backup-credentials  # From AWS Secrets Manager via ESO
```

**PagerDuty alerting for the backup job** — two clean approaches:

1. **Datadog monitor** (recommended): Alert on `kubernetes.job.failed` metric filtered to `job_name:db-backup`. Datadog → PagerDuty integration already exists in your stack. Zero new code.

2. **In-job wrapper**: The backup container's entrypoint script calls the PagerDuty Events API on non-zero exit. More explicit but couples alerting to the container image.

**For the weekly report** — since re-running Tuesday is acceptable, set `backoffLimit: 0` and let Datadog alert at low severity. No PagerDuty needed.

**For log rotation** — `backoffLimit: 1`, Datadog alert to Slack only (not PagerDuty).

---

## Addressing Diane's Three Mandates

| Mandate | How CronJobs satisfy it |
|---------|------------------------|
| Cloud-native | CronJobs are a CNCF-native Kubernetes primitive, not a cloud-vendor primitive. Maximally portable. |
| Observable | Datadog K8s integration covers job success/failure, duration, pod logs, and events — no new tooling. |
| Horizontally scalable | K8s scheduler distributes jobs across healthy nodes automatically. Adding more jobs is adding more manifests. |

---

## When to Revisit This Decision

Upgrade to Temporal or Airflow **only when** one of these is true:

- A job becomes multi-step (e.g., backup → verify integrity → notify → update audit log → conditional cleanup)
- You need cross-job dependencies (report generation must wait for backup to succeed)
- Job count exceeds ~20 and you need a unified UI for operations visibility
- A workflow requires human-in-the-loop approval steps

Step Functions becomes attractive if you migrate more workloads off EKS and into Lambda/ECS, making AWS-native the default rather than the exception.

---

**Bottom line for Diane**: The EC2 crontab fails the operational maturity bar because it's a single node with no HA, no GitOps management, no K8s-native observability, and no retry semantics. K8s CronJobs fix all of those problems with zero additional infrastructure. Choosing Airflow or Temporal to solve a single-point-of-failure problem is replacing one kind of operational risk with another — and a more expensive one.