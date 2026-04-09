```json
{
  "problem_type": "Relative motion kinematics with infinite series geometry",
  "strategy": "Find time until trains meet (using combined closing speed), then separate the bird's flight time from its direction changes. Time is finite; direction changes form infinite geometric series.",
  "hardest_part": "The bird changes direction infinitely many times. Each leg gets progressively shorter, converging to the meeting point asymptotically.",
  "solution": {
    "trains_meet_in": "2 hours (280 miles ÷ (60 + 80) mph)",
    "bird_flies": "200 miles (100 mph × 2 hours)",
    "direction_changes": "Infinite. The bird makes one trip toward each train, then reverses. Each reversal takes less time than the previous (geometric series: Σ of decreasing intervals). The series converges to t=2h, but contains infinite direction reversals."
  }
}
```