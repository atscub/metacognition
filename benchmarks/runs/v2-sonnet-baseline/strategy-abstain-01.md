```json
{
  "problem_type": "Kinematics / classic convergent-series trap problem",
  "strategy": "Reframe at the right level of abstraction — solve for total time first, then multiply. Resist the urge to sum the infinite geometric series of individual legs.",
  "hardest_part": "The direction-change question. The bird bounces infinitely many times in finite time (Zeno-style convergent series). Most solvers either skip it or incorrectly give a finite number.",
  "solution": "DISTANCE: Trains close at 60+80=140 mph over 280 miles → meet in 280/140 = 2 hours. Bird flies 2 hrs × 100 mph = 200 miles. DIRECTION CHANGES: Infinite. Each round-trip takes a fraction of the remaining time (ratio < 1), forming a convergent geometric series. The bird completes infinitely many back-and-forth legs in exactly 2 hours — the series sums to finite time but has no last term."
}
```