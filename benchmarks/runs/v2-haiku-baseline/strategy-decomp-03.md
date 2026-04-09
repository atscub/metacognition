```json
{
  "problem_type": "Constrained portfolio optimization with compound interest at multiple compounding frequencies",
  "strategy": "Identify binding constraints, then allocate remaining capital to highest-return asset. Use compound interest formulas for each frequency, then apply linear programming logic.",
  "hardest_part": "Correctly computing 3-year growth factors for three different compounding schedules, then recognizing which constraints are binding (active at optimum).",
  "solution": {
    "approach": "Since stock fund has highest 3-year return (25.97%), minimize allocations to lower-return assets while respecting constraints.",
    "calculations": {
      "growth_factors_over_3_years": {
        "savings_2_percent_monthly": "(1 + 0.02/12)^36 = 1.06184",
        "bonds_5_percent_quarterly": "(1 + 0.05/4)^12 = 1.15965",
        "stocks_8_percent_annual": "(1.08)^3 = 1.25971"
      },
      "binding_constraints": [
        "S ≥ 2,000 (liquidity) → set S = 2,000",
        "B + S ≥ 3,000 (30% minimum) → with S = 2,000, need B ≥ 1,000"
      ],
      "optimal_allocation": {
        "savings_S": 2000,
        "bonds_B": 1000,
        "stocks_K": 7000,
        "verification": "2000 + 1000 + 7000 = 10000 ✓; B+S = 3000 ✓"
      },
      "final_values_after_3_years": {
        "savings": "2000 × 1.06184 = 2,123.68",
        "bonds": "1000 × 1.15965 = 1,159.65",
        "stocks": "7000 × 1.25971 = 8,817.97",
        "total": "12,101.30"
      }
    },
    "answer": {
      "allocation": "$2,000 savings / $1,000 bonds / $7,000 stocks",
      "expected_total_after_3_years": "$12,101.30",
      "total_gain": "$2,101.30 (21.01% return)"
    }
  }
}
```