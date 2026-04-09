```json
{
  "problem_type": "Multi-step stoichiometric yield calculation with recycling",
  "strategy": "Sequential multiplication with careful stoichiometry tracking — distinguish between yield (efficiency) and molar ratios (stoichiometry), which are separate constraints",
  "hardest_part": "Step 2 has two independent constraints: a 2:1 molar ratio (stoichiometry) AND a 90% yield (efficiency). Both limit output. Missing the molar ratio would inflate D by 2×. The recycle then requires computing leftover C correctly.",
  "solution": "FORWARD PASS — Step 1: 100 mol A × 0.80 = 80 mol C. Step 2: stoichiometry caps D at 80÷2 = 40 mol max; 90% yield → 40 × 0.90 = 36 mol D produced; C consumed = 36 × 2 = 72 mol; unreacted C = 80 − 72 = 8 mol. Step 3: 36 mol D × 0.70 = 25.2 mol B. RECYCLE PASS — 8 mol unreacted C re-enters Step 2; stoichiometry caps at 8÷2 = 4 mol D max; 90% yield → 4 × 0.90 = 3.6 mol D; Step 3: 3.6 × 0.70 = 2.52 mol additional B. FINAL ANSWERS: Base process = 25.2 mol B; recycle adds 2.52 mol B."
}
```