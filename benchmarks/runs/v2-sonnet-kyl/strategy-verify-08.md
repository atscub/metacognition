```json
{
  "problem_type": "Multi-layer reasoning problem: (1) arithmetic verification, (2) framing/comparison validity, (3) financial optimization under competing rates, (4) motivated reasoning detection",

  "strategy": "Decompose into layers. Verify the math independently. Then stress-test the comparison itself — is it comparing what it claims to compare? Then model the actual alternative the advisor is dismissing. Finally, check for motivated reasoning or conflict of interest.",

  "hardest_part": "The math is correct, which creates a credibility halo. The flaw isn't in the arithmetic — it's in what the arithmetic is being used to prove. Separating 'the numbers are right' from 'the conclusion follows' requires resisting the anchoring effect of verified calculations.",

  "solution": {
    "math_verdict": "CORRECT but INCOMPLETE. Both calculations check out: 10000×(1.07)^30 = $76,123 and 10000×(1.07)^20 = $38,697. The $37,426 gap is real.",

    "framing_flaw": "The comparison is not apples-to-apples. The advisor models 'wait 10 years' as doing nothing — investing $0 and earning $0. The actual alternative is paying off 22% APR debt. Paying off debt at 22% APR is a guaranteed 22% return. The advisor has defined away the thing being compared.",

    "the_actual_math": "Carrying $10,000 in 22% APR debt while investing at 7% yields a net rate of 7% - 22% = -15% on that capital. Every dollar invested instead of applied to the debt is losing 15 percentage points annually. The opportunity cost runs backward — you are not 'gaining' 7%, you are netting -15%.",

    "correct_comparison": "Pay off 22% debt → guaranteed 22% return, zero risk. Then invest with freed cash flow. Versus: invest at 7% while credit card compounds at 22%. The break-even rate where 'invest instead of paying off debt' makes sense is if your investment return EXCEEDS the debt rate — here 7% < 22%, so it never makes sense.",

    "advisor_reasoning_failure": "Three compounding errors: (1) false dichotomy — invest now OR wait 10 years, omitting 'pay off 22% debt then invest'; (2) asymmetric risk framing — 7% is expected/volatile, 22% debt elimination is guaranteed; (3) anchor on the large-looking $37,426 number to generate urgency, while hiding the larger number: carrying 22% debt over any meaningful period destroys far more wealth.",

    "conflict_of_interest_flag": "Financial advisors are typically compensated on assets under management. Paying off your credit card gives the advisor nothing to manage. This is not proof of bad faith, but it is a structural incentive worth naming explicitly.",

    "verdict": "The financial advice is wrong. The math is used correctly but applied to the wrong comparison. A financially literate person should pay off 22% APR debt before investing at 7% — the guaranteed return on debt elimination exceeds the expected return on investment by 15 percentage points annually, before accounting for investment risk."
  }
}
```