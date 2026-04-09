```json
{
  "problem_type": "Constraint identification under hidden assumptions — the user's framing presumes the bottleneck is agent availability without validating that.",
  "strategy": "Theory of Constraints thinking: Question whether the assumed bottleneck is the actual bottleneck. Before investing in the obvious solution, diagnose the real constraint.",
  "hardest_part": "Recognizing that the problem statement contains a buried assumption. Management sees '8-minute wait' and thinks 'not enough agents.' But 8-minute waits can come from many sources — and throwing agents at the wrong constraint wastes money and doesn't solve the problem.",
  "solution": {
    "the_question_they_should_ask_first": "What is actually causing the 8-minute wait time? Is it truly insufficient agent capacity, or something else?",
    "diagnostic_questions": [
      "What percentage of the day are agents fully booked vs. idle? (If agents are idle during high-wait periods, the bottleneck isn't headcount.)",
      "What is the distribution of wait times? Peak vs. average? (A 4-minute *average* might hide 15-minute peaks at specific times — a staffing schedule fix, not a headcount fix.)",
      "What is the average call handle time? (If it's 12 minutes and the queue is short, reducing handle time by 20% eliminates most waits without hiring.)",
      "Are calls evenly distributed across the day, or are there bottleneck hours? (Staffing skew, not total headcount.)",
      "How many calls are repetitive/routine vs. complex? (Self-service/IVR deflection might eliminate 20% of inbound volume.)",
      "What is the current agent utilization? (If it's 60%, the problem is scheduling/efficiency, not capacity.)",
      "Is there a skill/expertise mismatch? (Some agents may be slower; training might be cheaper than hiring.)"
    ],
    "lower_cost_alternatives": [
      "**Process improvement**: Reduce average handle time by 30–40% through scripting, knowledge base optimization, or protocol redesign. (Cost: training, process engineering.)",
      "**Self-service/IVR expansion**: Route 15–25% of simple calls to automated systems. (Cost: development, lower than hiring.)",
      "**Scheduling optimization**: Shift staff to match demand curves — stagger breaks, add evening/early-morning coverage. (Cost: scheduling software, minimal hiring.)",
      "**Skill-based routing**: Route complex calls to specialists, routine calls to junior agents. Reduces average handle time per call. (Cost: routing system setup.)",
      "**Call batching/callback**: Instead of wait-in-queue, offer callbacks when queue exceeds threshold. (Cost: system change, dramatically reduces abandon rates.)",
      "**Outsourcing/overflow contracts**: Peak load handling via temporary staff or outsourced overflow, not permanent headcount. (Cost: variable, scales with demand.)",
      "**Technology/infrastructure**: Ensure phone system, CRM, knowledge systems aren't causing delays. (Cost: tech audit and fixes, one-time.)"
    ],
    "why_this_matters": "Doubling agents might cost $500K–$1M+ annually in salary, benefits, training, and overhead. A 20% process improvement or scheduling fix costs $50K–$200K and might achieve the same result with lower ongoing burden. The worst outcome: hire 50 agents and discover they're idle 40% of the day because the real bottleneck was call routing or handle time."
  }
}
```

---

**The core insight**: Management is solving the wrong problem because they haven't diagnosed which constraint actually causes the 8-minute wait. Theory of Constraints (TOC) thinking says: *identify the binding constraint before investing*. If they ask the diagnostic questions above first, they may discover the answer is scheduling, process, or technology — not headcount. That's where the cost savings live.