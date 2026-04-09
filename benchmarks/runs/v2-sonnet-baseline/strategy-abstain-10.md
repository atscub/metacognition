```json
{
  "problem_type": "Mathematical/statistical — inverse Elo rating calculation followed by forward prediction",
  "strategy": "Apply Elo expected-score formula algebraically to back-solve ratings from observed win rates, then use the derived ratings to compute head-to-head expectation",
  "hardest_part": "Recognizing this is an inverse problem (solve for R given E and R_opponent), and correctly chaining the two derived ratings into a third prediction without compounding rounding errors",
  "solution": "**Elo formula:** E = 1 / (1 + 10^((R_opp - R_player)/400))\n\n**Grandmaster** (W=7/10, E=0.70, R_opp=2000):\n  0.70 = 1/(1 + 10^((2000-R)/400))\n  10^((2000-R)/400) = (1/0.70) - 1 = 0.4286\n  (2000-R)/400 = log10(0.4286) = -0.3680\n  R_GM = 2000 + 147.2 ≈ **2147**\n\n**Beginner** (W=1/10, E=0.10, R_opp=2000):\n  0.10 = 1/(1 + 10^((2000-R)/400))\n  10^((2000-R)/400) = (1/0.10) - 1 = 9\n  (2000-R)/400 = log10(9) = 0.9542\n  R_B = 2000 - 381.7 ≈ **1618**\n\n**Head-to-head prediction** (R_GM - R_B = 529):\n  E_GM = 1/(1 + 10^(-529/400)) = 1/(1 + 10^(-1.3225)) = 1/(1 + 0.0476) ≈ **0.955**\n  In 10 games: 0.955 × 10 ≈ **9.5 wins → predict 9–10 wins for the grandmaster**"
}
```