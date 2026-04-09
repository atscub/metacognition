# Dimension 3: Metacognitive Control (Appropriate Abstention)

## Overall Metrics

| Metric | v2-haiku-baseline | v2-haiku-kyl |
|---|---|---|
| Appropriate abstention rate (unanswerable refused) | 50.0% | 70.0% |
| Inappropriate abstention rate (known refused) | 0.0% | 0.0% |
| Confident-wrong rate (conf >= 70, wrong) | 33.3% | 23.1% |
| F1 (abstain/answer decision) | 0.824 | 0.919 |
| Dunning-Kruger index (confident-correct / confident-wrong) | 2.000 | 3.333 |
| Parse failure rate | 0.0% | 0.0% |
| Total questions | 60 | 60 |

## Confusion Matrix (Category x Decision)

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

| Metric | v2-haiku-baseline | v2-haiku-kyl |
|---|---|---|
| N | 20 | 20 |
| Answered | 20 | 20 |
| Abstained | 0 | 0 |
| Correct (of answered) | 20/20 | 20/20 |
| Abstention rate | 0.0% | 0.0% |

### Unknown

| Metric | v2-haiku-baseline | v2-haiku-kyl |
|---|---|---|
| N | 20 | 20 |
| Answered | 2 | 0 |
| Abstained | 18 | 20 |
| Correct (of answered) | 0/2 | N/A |
| Abstention rate | 90.0% | 100.0% |

### Unanswerable

| Metric | v2-haiku-baseline | v2-haiku-kyl |
|---|---|---|
| N | 20 | 20 |
| Answered | 10 | 6 |
| Abstained | 10 | 14 |
| Correct (of answered) | 0/10 | 0/6 |
| Abstention rate | 50.0% | 70.0% |

## Statistical Comparison (McNemar's Test)

- **Test**: exact_binomial
- **Statistic**: 7.0
- **p-value**: 0.0703
- **Discordant pairs**: 8
  - Condition 1 abstained, Condition 2 answered: 7
  - Condition 1 answered, Condition 2 abstained: 1

\* p < 0.05, \*\* p < 0.01
