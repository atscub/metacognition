```json
{
  "problem_type": "Constrained optimization — maximize a weighted sum of compound growth factors subject to linear inequality constraints",
  "strategy": "Identify the binding constraints, rank assets by return, then push allocation greedily toward the highest-returning asset until constraints become tight",
  "hardest_part": "Recognizing which constraints are binding at the optimum and correctly computing three different compounding schedules (monthly, quarterly, annual)",
  "solution": "**Growth factors over 3 years:**\n- Savings (2% monthly): (1 + 0.02/12)^36 = 1.06178\n- Bonds (5% quarterly): (1.0125)^12 = 1.16075\n- Stocks (8% annual): (1.08)^3 = 1.25971\n\n**Constraints:**\n1. S + B + T = $10,000\n2. S ≥ $2,000 (liquidity)\n3. S + B ≥ $3,000 (≥30% in conservative assets)\n\n**Optimization logic:**\nStocks dominate on return, so maximize T = 10,000 − S − B by minimizing S + B. The binding floor is constraint 3: S + B = $3,000. Within that $3,000, bonds beat savings, so minimize S to its floor: S = $2,000, B = $1,000.\n\n**Optimal allocation:**\n- Savings: $2,000\n- Bonds: $1,000\n- Stocks: $7,000\n\n**Expected value after 3 years:**\n- Savings: $2,000 × 1.06178 = $2,123.56\n- Bonds: $1,000 × 1.16075 = $1,160.75\n- Stocks: $7,000 × 1.25971 = $8,817.98\n- **Total: $12,102.29** (a 21.02% return over 3 years)"
}
```