```json
{
  "problem_type": "Number theory / combinatorics — divisor counting with a perturbation",
  "strategy": "First solve the canonical case by counting divisors, then apply the perturbation as a XOR/toggle delta",
  "hardest_part": "The perturbation step: correctly identifying which lockers person 47 would have toggled, then reasoning whether each was open or closed in the standard solution to determine the new state",
  "solution": "STANDARD SOLUTION: Locker N is toggled once per divisor. It ends open iff it has an odd number of divisors. Only perfect squares have odd divisor counts (the square root pairs with itself). Open lockers: 1, 4, 9, 16, 25, 36, 49, 64, 81, 100. PERTURBATION — Person 47 skipped: Person 47 toggles every multiple of 47 in [1,100]: lockers 47 and 94. Each of these is toggled one fewer time, flipping their final state. Locker 47: divisors {1,47} → 2 toggles → normally CLOSED; minus one toggle → now OPEN. Locker 94: divisors {1,2,47,94} → 4 toggles → normally CLOSED; minus one toggle → now OPEN. ANSWER: Lockers 47 and 94 are in a different state — both are now open instead of closed."
}
```