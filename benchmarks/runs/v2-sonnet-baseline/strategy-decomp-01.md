```json
{
  "problem_type": "Production throughput / bottleneck analysis",
  "strategy": "Calculate per-stage throughput rates (machines ÷ cycle time), identify the binding constraint, then multiply bottleneck rate by total available time.",
  "hardest_part": "Resisting the urge to sum or average across stages — only the bottleneck stage determines system throughput.",
  "solution": "Throughput per stage: Stage 1 = 3 machines × (1/4 widget/min) = 0.75/min. Stage 2 = 2 machines × (1/6 widget/min) = 0.333/min. Stage 3 = 4 machines × (1/3 widget/min) = 1.333/min. Bottleneck is Stage 2 at 1/3 widget/min. Shift = 8h × 60 = 480 min. Max output = 480 × (1/3) = 160 widgets."
}
```