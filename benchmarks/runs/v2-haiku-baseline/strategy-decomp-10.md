```json
{
  "problem_type": "Non-linear transportation/network flow optimization with step-function cost structure",
  "strategy": "Enumerate cost regimes (which warehouses exceed 600-package threshold) and solve linear optimization within each regime, then compare total costs",
  "hardest_part": "The overtime surcharge applies to ALL packages (not just those over 600), creating discrete regimes rather than a smooth continuous function. Must check boundary cases where warehouses cross the 600-package threshold",
  "solution": "OPTIMAL PLAN: W1 ships 600 packages, W2 ships 600 packages (no overtime).\n\nAllocation:\n- W1 → East: 500 packages @ $2 = $1,000\n- W1 → Central: 100 packages @ $5 = $500\n- W2 → Central: 200 packages @ $4 = $800\n- W2 → West: 400 packages @ $2 = $800\n\nTOTAL DAILY COST: $3,100\n\nVerification:\n- Demand met: East 500 ✓, Central 300 ✓, West 400 ✓\n- Capacity: W1 600/700 ✓, W2 600/600 ✓\n- No overtime surcharges (neither warehouse exceeds 600)\n- Alternative regimes (W1>600 or W2>600) cost $3,700+ due to $1/pkg surcharge\n\nKey insight: The $1 surcharge on ALL packages makes any warehouse operating >600 very expensive ($3-9/pkg vs $2-5/pkg). The sweet spot is operating both warehouses at exactly 600, using greedy assignment to lowest-cost routes."
}
```