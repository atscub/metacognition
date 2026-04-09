```json
{
  "problem_type": "Integer linear programming / constrained optimization",
  "strategy": "LP relaxation to find optimal vertex, then integer rounding with feasibility checks on nearby candidates",
  "hardest_part": "The three binding constraints (flour, eggs, oven) create a polytope whose corner points must be evaluated — the LP relaxation yields a non-integer optimum, requiring careful ILP rounding rather than a clean analytical solution",
  "solution": "Variables: b=bread, c=cake, k=cookies. Objective: max 3b+8c+5k. Constraints: (1) 2b+3c+k≤30 flour, (2) b+4c+2k≤40 eggs, (3) b+c+k≤20 oven, (4) b≥5. Since bread earns the least, set b=5 (minimum). Reduced problem: max 8c+5k s.t. 3c+k≤20, 4c+2k≤35, c+k≤15. LP relaxation corner: intersection of 3c+k=20 and c+k=15 gives c=2.5, k=12.5 (revenue=97.5 — non-integer). Integer candidates: [c=2,k=13] → flour=29✓, eggs=39✓, oven=20✓ → revenue=$96; [c=3,k=11] → revenue=$94; [c=0,k=15] → revenue=$90. OPTIMAL: b=5 bread, c=2 cakes, k=13 cookie batches → daily revenue=$96 (uses 29/30 flour cups, 39/40 eggs, 20/20 oven slots)."
}
```