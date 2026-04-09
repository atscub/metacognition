```json
{
  "has_bias": true,
  "bias_name": "Confirmation Bias + Post Hoc Ergo Propter Hoc",
  "explanation": "The person found a temporal correlation (config pushed 5 min before outage) and locked onto it as proof of causation. They dismissed contradictory evidence—database connection pool exhaustion and elevated cache memory—as 'probably downstream effects' without investigation. The statement 'the timeline is too clean for it to be anything else' reveals narrative fallacy: they constructed a clean causal story and are filtering out complexity. Recovery after rollback provided false confidence (correlation, not causation). A rigorous root cause analysis would need to establish that the config change could actually produce those specific downstream effects, not assume it based on timing alone."
}
```