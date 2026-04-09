```json
{
  "problem_type": "Number theory problem involving divisors and parity (perfect squares and prime factorization)",
  "strategy": "Recognize that each locker's final state depends on how many times it's toggled. Locker N is toggled by each person whose number divides N. Odd number of toggles → open; even → closed. Perfect squares have odd divisor counts.",
  "hardest_part": "Identifying all lockers affected when person 47 skips. Must find all multiples of the prime 47 within the range, then recalculate divisor parity for those lockers.",
  "solution": {
    "standard_solution": {
      "rule": "A locker ends open iff it's toggled an odd number of times, which happens iff its number is a perfect square",
      "open_lockers": [1, 4, 9, 16, 25, 36, 49, 64, 81, 100],
      "total_open": 10,
      "explanation": "Only perfect squares have an odd number of divisors (because divisors pair up except when d = √n)"
    },
    "with_person_47_absent": {
      "affected_lockers": [47, 94],
      "locker_47": {
        "standard": "divisors = {1, 47}, count = 2 (even) → closed",
        "without_47": "divisors = {1}, count = 1 (odd) → open",
        "state_change": "closed → open"
      },
      "locker_94": {
        "standard": "divisors = {1, 2, 47, 94}, count = 4 (even) → closed",
        "without_47": "divisors = {1, 2, 94}, count = 3 (odd) → open",
        "state_change": "closed → open"
      },
      "answer": "Lockers 47 and 94 change state (both move from closed to open). All other lockers remain unchanged because 47 is prime and only divides its multiples within 1-100."
    }
  }
}
```