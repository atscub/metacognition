```json
{
  "problem_type": "Statistical reasoning problem: distinguishing between mathematical correctness and meaningful interpretation; identifying misleading use of averages",
  "strategy": "Three-step verification: (1) Check arithmetic validity (2) Examine what the mean actually measures vs. what's being claimed (3) Compare with alternative statistical measures appropriate for skewed distributions",
  "hardest_part": "Recognizing that the calculation is mathematically correct but the conclusion is logically invalid—requires understanding how outliers distort the mean and how 'average' differs from 'typical' in the presence of skewed data",
  "solution": {
    "calculation_correct": true,
    "calculation_verification": "95 × $50,000 + 5 × $500,000 = $4,750,000 + $2,500,000 = $7,250,000; ÷100 = $72,500 ✓",
    "conclusion_valid": false,
    "why_conclusion_fails": "The mean ($72,500) is pulled upward by 5 extreme outliers (executives earning $500k). Claiming this is what 'the typical employee' earns is false—95% of employees earn only $50,000, nowhere near $72,500.",
    "more_appropriate_measures": {
      "median": "$50,000 — the salary where 50% earn more, 50% earn less. Directly answers 'what is typical'",
      "mode": "$50,000 — the most common salary. Also highly representative",
      "full_distribution": "95% earn $50k; 5% earn $500k — this single sentence conveys more truth than any single number"
    },
    "key_insight": "When a distribution is heavily skewed (outliers in one direction), the mean becomes unrepresentative. Use median or describe the distribution explicitly. The phrase 'average salary' is misleading in contexts with high inequality."
  }
}
```