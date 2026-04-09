# Dimension 2: Metacognitive Knowledge (Strategy Selection)

## Overall Metrics

| Metric | v2-sonnet-baseline | v2-sonnet-kyl |
|---|---|---|
| N (valid / total) | 40 / 40 | 32 / 40 |
| Parse failure rate | 0.0% | 0.0% |
| Strategy match rate (0-2) | 1.025 | 1.062 |
| Exact match rate (score=2) | 27.5% | 28.1% |
| Partial+ match rate (score>=1) | 75.0% | 78.1% |

## Per-Strategy Breakdown

### Abstention

| Metric | v2-sonnet-baseline | v2-sonnet-kyl |
|---|---|---|
| N | 10 | 10 |
| Mean score (0-2) | 0.400 | 0.600 |
| Exact match rate | 10.0% | 10.0% |
| Partial+ match rate | 30.0% | 50.0% |

### Decomposition

| Metric | v2-sonnet-baseline | v2-sonnet-kyl |
|---|---|---|
| N | 10 | 9 |
| Mean score (0-2) | 1.000 | 1.111 |
| Exact match rate | 20.0% | 22.2% |
| Partial+ match rate | 80.0% | 88.9% |

### Reframing

| Metric | v2-sonnet-baseline | v2-sonnet-kyl |
|---|---|---|
| N | 10 | 3 |
| Mean score (0-2) | 1.400 | 1.667 |
| Exact match rate | 40.0% | 66.7% |
| Partial+ match rate | 100.0% | 100.0% |

### Verification

| Metric | v2-sonnet-baseline | v2-sonnet-kyl |
|---|---|---|
| N | 10 | 10 |
| Mean score (0-2) | 1.300 | 1.300 |
| Exact match rate | 40.0% | 40.0% |
| Partial+ match rate | 90.0% | 90.0% |

## Difficulty Prediction

### v2-sonnet-baseline
_Model difficulty predictions not yet extracted -- correlation requires 'difficulty' field in model responses_
- Tasks with expected difficulty labels: 40

### v2-sonnet-kyl
_Model difficulty predictions not yet extracted -- correlation requires 'difficulty' field in model responses_
- Tasks with expected difficulty labels: 32

## Statistical Comparison

### Wilcoxon Signed-Rank Test (v2-sonnet-baseline vs v2-sonnet-kyl)

- N pairs: 32
- Test statistic: 51.0
- p-value: 0.3173
- Mean score (condition 1): 0.938
- Mean score (condition 2): 1.062
- Mean difference: -0.125
- Effect size (r): 0.177

\* p < 0.05, \*\* p < 0.01

## Judge & Cache Statistics

| Stat | v2-sonnet-baseline | v2-sonnet-kyl |
|---|---|---|
| Judge calls | 40 | 40 |
| Cache hits | 40 | 27 |
| Judge errors | 0 | 8 |
| Cache hit rate | 100.0% | 67.5% |
