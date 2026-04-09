# Dimension 3: Metacognitive Control (Appropriate Abstention)

## Overall Metrics

| Metric | v2-sonnet-baseline | v2-sonnet-kyl |
|---|---|---|
| Appropriate abstention rate (unanswerable refused) | 35.0% | 50.0% |
| Inappropriate abstention rate (known refused) | 0.0% | 0.0% |
| Confident-wrong rate (conf >= 70, wrong) | 41.2% | 35.5% |
| F1 (abstain/answer decision) | 0.762 | 0.800 |
| Dunning-Kruger index (confident-correct / confident-wrong) | 1.429 | 1.818 |
| Parse failure rate | 0.0% | 0.0% |
| Total questions | 60 | 60 |

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

## Per-Category Breakdown

### Known

| Metric | v2-sonnet-baseline | v2-sonnet-kyl |
|---|---|---|
| N | 20 | 20 |
| Answered | 20 | 20 |
| Abstained | 0 | 0 |
| Correct (of answered) | 20/20 | 20/20 |
| Abstention rate | 0.0% | 0.0% |

### Unknown

| Metric | v2-sonnet-baseline | v2-sonnet-kyl |
|---|---|---|
| N | 20 | 20 |
| Answered | 3 | 4 |
| Abstained | 17 | 16 |
| Correct (of answered) | 1/3 | 1/4 |
| Abstention rate | 85.0% | 80.0% |

### Unanswerable

| Metric | v2-sonnet-baseline | v2-sonnet-kyl |
|---|---|---|
| N | 20 | 20 |
| Answered | 13 | 10 |
| Abstained | 7 | 10 |
| Correct (of answered) | 0/13 | 0/10 |
| Abstention rate | 35.0% | 50.0% |

## Statistical Comparison (McNemar's Test)

- **Test**: exact_binomial
- **Statistic**: 3.0
- **p-value**: 0.625
- **Discordant pairs**: 4
  - Condition 1 abstained, Condition 2 answered: 3
  - Condition 1 answered, Condition 2 abstained: 1

\* p < 0.05, \*\* p < 0.01
