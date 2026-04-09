```json
{
  "problem_type": "Probability / Combinatorics with a hidden assumption trap (a classic paradox)",
  "strategy": "Calculate expected values rigorously; identify what makes this problem *feel* like it should change the ratio but doesn't; question the framing of 'population impact'",
  "hardest_part": "Resisting the intuitive assumption that 'stopping at a boy' skews female; recognizing that expectation is linear and each family's process, despite variable length, produces the same expected outcome as a fixed alternative",
  "solution": {
    "fraction_female": 0.5,
    "population_impact": "No change — neutral in expectation",
    "reasoning": {
      "key_insight": "Each family, under 'stop at boy' policy, has an *expected* 1 girl and *exactly* 1 boy, for an expected 2 children total.",
      "calculation": {
        "family_sequences": [
          "B (prob 1/2): 0 girls, 1 boy, 1 child",
          "GB (prob 1/4): 1 girl, 1 boy, 2 children",
          "GGB (prob 1/8): 2 girls, 1 boy, 3 children",
          "GGGB (prob 1/16): 3 girls, 1 boy, 4 children"
        ],
        "expected_girls": "E[girls] = 0(1/2) + 1(1/4) + 2(1/8) + 3(1/16) + ... = 1",
        "expected_boys": 1,
        "expected_children_per_family": 2,
        "female_fraction": "1 / (1 + 1) = 0.5"
      },
      "comparison_to_exactly_2_children": {
        "both_policies_yield": "Expected 2 children per family, split 50/50 girls/boys",
        "population_growth_impact": "Identical in expectation; no effect"
      },
      "why_this_surprises": "The variable-length process *feels* like it should skew female, but linearity of expectation means the average outcome equals the fixed case"
    }
  }
}
```