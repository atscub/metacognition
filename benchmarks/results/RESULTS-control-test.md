# Dimension 3: Metacognitive Control (Appropriate Abstention)

## Overall Metrics

| Metric | v2-test-baseline |
|---|---|
| Appropriate abstention rate (unanswerable refused) | 100.0% |
| Inappropriate abstention rate (known refused) | 0.0% |
| Confident-wrong rate (conf >= 70, wrong) | 0.0% |
| F1 (abstain/answer decision) | 1.000 |
| Dunning-Kruger index (confident-correct / confident-wrong) | inf |
| Parse failure rate | 0.0% |
| Total questions | 3 |

## Confusion Matrix (Category x Decision)

### v2-test-baseline

| Category | Answered | Abstained | Total |
|---|---|---|---|
| known | 1 | 0 | 1 |
| unknown | 1 | 0 | 1 |
| unanswerable | 0 | 1 | 1 |

## Per-Category Breakdown

### Known

| Metric | v2-test-baseline |
|---|---|
| N | 1 |
| Answered | 1 |
| Abstained | 0 |
| Correct (of answered) | 1/1 |
| Abstention rate | 0.0% |

### Unknown

| Metric | v2-test-baseline |
|---|---|
| N | 1 |
| Answered | 1 |
| Abstained | 0 |
| Correct (of answered) | 1/1 |
| Abstention rate | 0.0% |

### Unanswerable

| Metric | v2-test-baseline |
|---|---|
| N | 1 |
| Answered | 0 |
| Abstained | 1 |
| Correct (of answered) | N/A |
| Abstention rate | 100.0% |

## Statistical Comparison (McNemar's Test)

McNemar's test requires exactly two conditions. Skipped.
