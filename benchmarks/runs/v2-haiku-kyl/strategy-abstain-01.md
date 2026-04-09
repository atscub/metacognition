```json
{
  "problem_type": "Kinematics/relative motion with a convergence series",
  "strategy": "Recognize that the bird's total distance depends only on time-in-motion, not on individual legs. For direction changes, recognize this as an infinite series problem (the bird bounces infinitely many times in finite time as the gap shrinks).",
  "hardest_part": "Resisting the urge to track each leg individually — most people solve this the hard way. Second: understanding that direction changes form an infinite series converging to a finite time window.",
  "solution": {
    "bird_distance": "200 miles",
    "reasoning_distance": "Time until trains meet: 280 miles ÷ (60+80) mph = 280÷140 = 2 hours. Bird flies continuously for 2 hours at 100 mph = 200 miles. The bird's path complexity is irrelevant to total distance.",
    "direction_changes": "Infinite",
    "reasoning_direction_changes": "The bird bounces between trains at accelerating frequency as they approach each other. Each turnaround is a direction change. This is a convergent series — infinitely many bounces occur in the finite 2-hour window before the trains meet. Mathematically, lim(n→∞) = infinite direction changes."
  }
}
```

---

### Key insight (epistemically grounded):

**High confidence on distance**: The core principle is rock-solid — the bird's distance is `speed × time`, period. The path doesn't matter.

**Medium-high confidence on direction changes**: The answer is almost certainly intended to be **infinite**, but I'm flagging this: some versions of this problem frame it differently (e.g., "counting only complete back-and-forth legs" rather than instantaneous turns). The problem statement says "changes direction," not "completes round trips," so infinite is the mathematically correct answer — but if this came from a source that expects a finite number, they may have different framing.

The reason for infinite: as the trains get arbitrarily close, the gap the bird has to cross shrinks, but the time for each crossing also shrinks faster than it can be counted. You get infinitely many legs in finite time — a classic Zeno-like paradox resolution.