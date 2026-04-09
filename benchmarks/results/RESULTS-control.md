# Dimension 3: Metacognitive Control (Appropriate Abstention)

## Overall Metrics

| Metric | v2-sonnet-baseline | v2-sonnet-kyl | v2-haiku-baseline | v2-haiku-kyl |
|---|---|---|---|---|
| Appropriate abstention rate (unanswerable refused) | 35.0% | 50.0% | 50.0% | 70.0% |
| Inappropriate abstention rate (known refused) | 0.0% | 0.0% | 0.0% | 0.0% |
| Confident-wrong rate (conf >= 70, wrong) | 41.2% | 35.5% | 33.3% | 23.1% |
| F1 (abstain/answer decision) | 0.762 | 0.800 | 0.824 | 0.919 |
| Dunning-Kruger index (confident-correct / confident-wrong) | 1.429 | 1.818 | 2.000 | 3.333 |
| Parse failure rate | 0.0% | 0.0% | 0.0% | 0.0% |
| Total questions | 60 | 60 | 60 | 60 |

## Confusion Matrix (Category x Decision)

### v2-sonnet-baseline

| Category | Answered | Abstained | Total |
|---|---|---|---|
| known | 20 | 0 | 20 |
| unknown | 3 | 17 | 20 |
| unanswerable | 13 | 7 | 20 |

### v2-sonnet-kyl

| Category | Answered | Abstained | Total |
|---|---|---|---|
| known | 20 | 0 | 20 |
| unknown | 4 | 16 | 20 |
| unanswerable | 10 | 10 | 20 |

### v2-haiku-baseline

| Category | Answered | Abstained | Total |
|---|---|---|---|
| known | 20 | 0 | 20 |
| unknown | 2 | 18 | 20 |
| unanswerable | 10 | 10 | 20 |

### v2-haiku-kyl

| Category | Answered | Abstained | Total |
|---|---|---|---|
| known | 20 | 0 | 20 |
| unknown | 0 | 20 | 20 |
| unanswerable | 6 | 14 | 20 |

## Per-Category Breakdown

### Known

| Metric | v2-sonnet-baseline | v2-sonnet-kyl | v2-haiku-baseline | v2-haiku-kyl |
|---|---|---|---|---|
| N | 20 | 20 | 20 | 20 |
| Answered | 20 | 20 | 20 | 20 |
| Abstained | 0 | 0 | 0 | 0 |
| Correct (of answered) | 20/20 | 20/20 | 20/20 | 20/20 |
| Abstention rate | 0.0% | 0.0% | 0.0% | 0.0% |

### Unknown

| Metric | v2-sonnet-baseline | v2-sonnet-kyl | v2-haiku-baseline | v2-haiku-kyl |
|---|---|---|---|---|
| N | 20 | 20 | 20 | 20 |
| Answered | 3 | 4 | 2 | 0 |
| Abstained | 17 | 16 | 18 | 20 |
| Correct (of answered) | 1/3 | 1/4 | 0/2 | N/A |
| Abstention rate | 85.0% | 80.0% | 90.0% | 100.0% |

### Unanswerable

| Metric | v2-sonnet-baseline | v2-sonnet-kyl | v2-haiku-baseline | v2-haiku-kyl |
|---|---|---|---|---|
| N | 20 | 20 | 20 | 20 |
| Answered | 13 | 10 | 10 | 6 |
| Abstained | 7 | 10 | 10 | 14 |
| Correct (of answered) | 0/13 | 0/10 | 0/10 | 0/6 |
| Abstention rate | 35.0% | 50.0% | 50.0% | 70.0% |

## Statistical Comparison (McNemar's Test)

McNemar's test requires exactly two conditions. Skipped.
