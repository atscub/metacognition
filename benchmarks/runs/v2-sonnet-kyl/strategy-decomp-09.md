```json
{
  "problem_type": "Sequential stoichiometric yield calculation with a recycling loop",
  "strategy": "Track moles step-by-step, being careful to separate the stoichiometric 2:1 ratio (a hard constraint on how much C is consumed) from the 90% yield (how efficiently the reaction proceeds within that constraint). The two interact to determine leftover C.",
  "hardest_part": "Step 2 conflates two things: stoichiometry (2 mol C → 1 mol D) and yield (90% of possible D is actually made). Both affect how much C is consumed. Getting that interaction wrong cascades through everything including the recycle.",
  "solution": {
    "step_1": {
      "input_A": 100,
      "yield": 0.80,
      "C_produced": 80
    },
    "step_2_no_recycle": {
      "C_available": 80,
      "stoichiometry": "2 mol C per mol D",
      "theoretical_max_D": 40,
      "yield": 0.90,
      "D_produced": 36,
      "C_consumed": "36 × 2 = 72",
      "C_unreacted": "80 - 72 = 8"
    },
    "step_3_no_recycle": {
      "D_input": 36,
      "yield": 0.70,
      "B_produced": 25.2
    },
    "recycle_pass": {
      "C_recycled": 8,
      "theoretical_max_D": 4,
      "yield": 0.90,
      "D_produced": 3.6,
      "B_additional": "3.6 × 0.70 = 2.52"
    },
    "answers": {
      "moles_B_without_recycle": 25.2,
      "additional_moles_B_from_recycle": 2.52,
      "total_moles_B_with_recycle": 27.72
    },
    "confidence": "High — the stoichiometry is explicit in the problem. The key assumption is that '90% yield' means 90% of the theoretical maximum D is obtained, which determines C consumed as 2 × D_actual rather than 2 × D_theoretical. This is the standard chemical-engineering interpretation."
  }
}
```