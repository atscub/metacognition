```json
{
  "problem_type": "Systems framing error — a resource-allocation problem masquerading as a capacity problem. Management has anchored on 'supply solution' (more agents) without diagnosing whether the real lever is demand reduction.",

  "strategy": "Reframe before optimizing. The Socratic move here is to question the implicit assumption that wait time is a supply/capacity problem. In queuing systems, wait time = f(arrival rate, service rate, agents). You can pull any of those levers. Management is only looking at one.",

  "hardest_part": "Resisting the intuitive plausibility of 'more agents = less wait'. It's locally true but it's also expensive, slow, and treats the symptom. The bias is anchoring: once 'double agents' is on the table, alternatives feel like objections rather than starting points. Also: the relationship between agents and wait time (Erlang C) is non-linear near saturation — doubling agents may not halve wait time at all, depending on current utilization.",

  "solution": {
    "the_question_they_should_ask_first": "Why are customers calling — and can we eliminate the need to call at all?",
    "sub_questions": [
      "What are the top 5 call reasons by volume? (Often 30-40% are 'where is my order' or password resets — fully automatable)",
      "What is our first-call resolution rate? (Low FCR means the same customer calls twice, doubling load)",
      "Is wait time uniform across the day, or driven by 2-hour peaks? (Targeted scheduling beats blanket hiring)",
      "What is average handle time, and is it bloated by agent tooling or process friction?"
    ],
    "alternatives_by_cost": [
      "Demand reduction (cheapest): Fix the product/process that generates calls. Better order tracking, proactive shipment notifications, clearer billing — these eliminate call categories entirely.",
      "Self-service deflection: Chatbot or IVR for top-N call types. A well-tuned FAQ or status page can deflect 20-40% of volume at near-zero marginal cost per call.",
      "Callback scheduling: Customers request a callback instead of waiting. Actual wait time unchanged, but perceived wait time drops to near zero — often solves the customer experience problem without solving the operational one.",
      "First-call resolution improvement: If FCR is 60%, fixing it to 80% cuts repeat call volume by ~33%. Training, better agent tooling, or authority to resolve issues on first contact.",
      "Peak-hour flex staffing: If 60% of calls hit in a 4-hour window, part-time or overflow routing costs a fraction of full-time headcount.",
      "Partial automation of handle time: IVR pre-authentication, screen-pops with customer history, macros — reducing AHT by 2 minutes has the same throughput effect as adding agents."
    ],
    "the_meta_point": "Doubling agents is the right answer only after you've exhausted demand-side levers. It's also the irreversible, highest-ongoing-cost option. The framing error is treating 'wait time' as the root cause rather than a symptom — the root cause is call volume × handle time relative to capacity. Management should see a breakdown of call reasons before approving a single hire."
  }
}
```