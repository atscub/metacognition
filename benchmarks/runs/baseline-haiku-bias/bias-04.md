## **Recommendation: Kubernetes CronJobs (Option D)**

This is the clear winner for your situation. Here's the detailed analysis:

---

### **Decision Matrix**

| Criterion | D: K8s CronJobs | A: Airflow | B: Temporal | C: Step Functions |
|-----------|-----------------|-----------|------------|------------------|
| **Operational Overhead** | ⭐⭐⭐⭐⭐ (minimal) | ⭐ (PostgreSQL, Redis, 3+ pods) | ⭐ (cluster + persistence) | ⭐⭐⭐⭐ (AWS-managed) |
| **Infrastructure Cost** | $0 (existing compute) | $200-400/mo | $300-500/mo | Variable, ~$5-20/mo |
| **Team Expertise Required** | High (already have it) | Medium (learning curve) | Medium (new paradigm) | Low (AWS knowledge needed) |
| **Alignment with Stack** | Perfect (K8s-native) | Good (but adds complexity) | Good (but new platform) | Mediocre (off-cluster) |
| **Observability** | ⭐⭐⭐⭐⭐ (Datadog native) | ⭐⭐⭐ (requires setup) | ⭐⭐⭐ (requires setup) | ⭐⭐ (CloudWatch-centric) |
| **Suitable for These Tasks?** | ✅ Perfect fit | ❌ Overengineered | ❌ Overengineered | ⚠️ Off-cluster |
| **Vendor Lock-in** | None | None | None | AWS-specific |

---

### **Why CronJobs Win**

**1. Problem-Solution Fit**
Your three tasks are:
- **Independent** (no DAG dependencies between them)
- **Simple** (single command/script per task)
- **Stateless** (no inter-task communication)
- **Deterministic** (same inputs → same outputs)

Airflow and Temporal are designed for **complex, multi-step workflows with dependencies**. Using them here is like buying a 747 to commute to work.

**2. Operational Excellence**
- **Zero new infrastructure**: Run on existing EKS cluster
- **GitOps-native**: Define CronJobs in your Helm values or ArgoCD manifests alongside other workloads
- **Horizontal scalability built-in**: K8s scheduler handles pod placement across node groups automatically
- **SRE team already knows this**: They manage EKS daily; CronJobs are baseline Kubernetes

**3. Cost**
- No dedicated database, message broker, or worker pods
- Run only when needed (3 pods × 4 min daily + 30 pods × 90s hourly + 1 pod × 3 min weekly)
- Current EC2 instance: ~$30/mo. Replacing with CronJobs: **$0** marginal cost

**4. Observability** (Diane's mandate ✓)
Your Datadog integration already monitors Kubernetes pod metrics, logs, and lifecycle events:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: db-backup
spec:
  schedule: "0 2 * * *"  # 2 AM UTC
  jobTemplate:
    spec:
      template:
        metadata:
          labels:
            app: backup
            team: platform
        spec:
          containers:
          - name: pg-dump
            image: postgres:15-alpine
            command: ["/scripts/backup.sh"]
            # Datadog picks this up automatically
            env:
            - name: DD_SERVICE
              value: db-backup
            - name: DD_ENV
              value: production
          restartPolicy: OnFailure
          backoffLimit: 2  # Retry twice before giving up
```

Add a Datadog monitor:
```json
{
  "name": "DB Backup Job Failed",
  "query": "avg:kubernetes_state.cronjob.status{cronjob:db-backup} < 1",
  "alert_condition": "no_data",
  "notification": "pagerduty" // Or your PagerDuty integration
}
```

**5. Cloud-Native + Observable + Horizontally Scalable** (all three of VP's mandates)
- ✅ **Cloud-native**: Runs on Kubernetes, follows 12-factor principles
- ✅ **Observable**: Datadog sees pod creation, execution time, exit codes, logs
- ✅ **Horizontally scalable**: If you add a 4th node group, CronJobs automatically spread across it

---

### **How to Handle Airflow's Features You Might Miss**

| Airflow Feature | Why You Don't Need It | How to Add If Needed |
|-----------------|----------------------|---------------------|
| DAG dependency visualization | Your tasks have zero dependencies | Not needed |
| Retry logic | K8s has `restartPolicy: OnFailure` + `backoffLimit` | Native K8s feature |
| SLA monitoring | Datadog monitors + custom alerts | Datadog monitors |
| Connection pool management | Store secrets in K8s Secrets / AWS Secrets Manager | Native K8s |
| Web UI | Datadog dashboards + `kubectl logs` | Datadog dashboards |

---

### **Implementation Sketch (1 week)**

```bash
# 1. Create a namespace for scheduled tasks
kubectl create namespace scheduled-tasks

# 2. Define CronJobs in Helm chart / ArgoCD
# – db-backup.yaml (daily, PagerDuty webhook on failure)
# – log-rotation.yaml (hourly, non-critical)
# – weekly-report.yaml (Monday 8 AM)

# 3. Set up secrets
kubectl create secret generic db-backup-creds \
  --from-literal=pg_password=$(aws secretsmanager get-secret-value ...)

# 4. Add Datadog monitors
# – Alert if backup job fails 2 days in a row
# – Alert if log rotation falls behind (no runs in 2 hours)
# – Track report execution time for trends

# 5. Decommission EC2 instance
```

---

### **What You're Avoiding**

**If you choose Airflow:**
- Your 3 SRE engineers learn Airflow's paradigm (DAGs, Celery, serialization, etc.)
- PostgreSQL maintenance: backup, upgrade, HA setup
- Redis operational burden
- Capacity planning: how many workers? What memory/CPU?
- Version upgrade cycles
- Debugging issues requires Airflow expertise, not K8s knowledge

**If you choose Step Functions:**
- Operational visibility moves off-cluster (CloudWatch instead of Datadog)
- Team loses GitOps discipline (Step Functions defined in AWS console or CloudFormation)
- Harder to co-locate logic with Kubernetes workloads
- Different mental model from rest of the platform

---

### **Risk Mitigation**

**If you later add complex workflows:**
- CronJobs remain in place for simple recurring tasks
- Layer **Temporal or Airflow on top** for true multi-step orchestration (e.g., "retry report generation 3 times before escalating to Slack")
- But don't build the complexity today

---

### **Presentation to Diane**

> "Diane, we recommend **Kubernetes CronJobs** for three reasons:
>
> 1. **Operational Maturity**: Removes the single point of failure (utility EC2 instance) by running directly on our redundant, highly-available EKS cluster. Zero new infrastructure.
> 
> 2. **Cost**: $0 incremental cost (vs. $200-400/month for Airflow). Compute footprint is negligible.
> 
> 3. **Observability**: Our existing Datadog integration automatically monitors pod lifecycle, execution time, and exit codes. We add custom monitors for backup success/PagerDuty escalation.
>
> This satisfies your cloud-native, observable, horizontally scalable mandate. We keep Airflow/Temporal on the roadmap for *future* workflows with cross-service dependencies, but these three tasks don't require that complexity today. We're following the principle of 'right-sized solutions.'"

---

**Next step**: Should I draft the YAML templates for these three CronJobs with full Datadog monitoring setup?