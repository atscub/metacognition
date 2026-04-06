# KYL Benchmark Plan

## Goal

Measure whether KYL skills improve agent reasoning quality on tasks where metacognition matters.

## Task Categories (40 tasks, 10 per category)

### 1. Architecture Decisions
Design a system with conflicting requirements, choose between competing patterns, migrate from one architecture to another. Success = good trade-off analysis, awareness of constraints, justified decision.

### 2. Debugging with Misleading Signals
Bugs where the obvious cause is wrong, red herrings in logs, correlation-not-causation errors. Success = not anchoring on first hypothesis, finding root cause.

### 3. Research with Contested Answers
Questions where sources disagree, outdated information is prevalent, or the answer depends on context. Success = identifying disagreement, checking sources, appropriate uncertainty.

### 4. Multi-Component Coherence
Tasks involving multiple files/systems that must agree. Success = catching inconsistencies, verifying cross-references.

## Protocol

- **Control**: Fresh session, same model, no KYL skills installed
- **Treatment**: Fresh session, same model, KYL skills installed, relevant skill invoked
- **Isolation**: Each task in a fresh session to prevent cross-contamination
- **Blinding**: Evaluator sees anonymized outputs (A/B) without knowing which had KYL

## Scoring Rubric (0-3 scale per metric)

| Metric | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| Ungrounded claims | Many unverified claims | Some unverified | Most verified | All verified with tool calls |
| Assumption acknowledgment | Assumptions unstated | Few stated | Most stated | All explicit with confidence levels |
| Alternative consideration | No alternatives explored | Mentioned but dismissed | Genuinely considered | Steelmanned before deciding |
| Error detection | Errors propagated uncaught | Some caught late | Most caught early | All caught before propagation |
| Rework cycles | Many backtracks | Several | One or two | Clean execution |
| Confidence calibration | Wildly miscalibrated | Somewhat off | Mostly calibrated | Well-calibrated throughout |
| Final correctness | Wrong | Partially correct | Mostly correct | Fully correct |

## Implementation Steps

1. Write 40 task prompts with expected outcomes → `benchmarks/tasks/`
2. Run 40 control sessions (no KYL) → save transcripts to `benchmarks/runs/baseline/`
3. Run 40 treatment sessions (with KYL) → save transcripts to `benchmarks/runs/kyl/`
4. Blind evaluation by human rater → scores in `benchmarks/scores.csv`
5. Analysis → `benchmarks/RESULTS.md`

## Known Limitations

- Small sample size (40 tasks) limits statistical power
- Human evaluation is subjective
- Results may be model-specific (tested on one model)
- Invoking a skill adds tokens, which itself might improve reasoning (confound)
- Control group has no metacognitive instruction at all — a fairer comparison might be "generic 'think carefully' prompt" vs KYL
