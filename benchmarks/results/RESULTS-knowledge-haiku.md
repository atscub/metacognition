# Dimension 2: Metacognitive Knowledge (Strategy Selection)

## Overall Metrics

| Metric | v2-haiku-baseline | v2-haiku-kyl |
|---|---|---|
| N (valid / total) | 39 / 40 | 40 / 40 |
| Parse failure rate | 0.0% | 0.0% |
| Strategy match rate (0-2) | 1.128 | 1.175 |
| Exact match rate (score=2) | 35.9% | 30.0% |
| Partial+ match rate (score>=1) | 76.9% | 87.5% |

## Per-Strategy Breakdown

### Abstention

| Metric | v2-haiku-baseline | v2-haiku-kyl |
|---|---|---|
| N | 10 | 10 |
| Mean score (0-2) | 0.300 | 0.600 |
| Exact match rate | 0.0% | 0.0% |
| Partial+ match rate | 30.0% | 60.0% |

### Decomposition

| Metric | v2-haiku-baseline | v2-haiku-kyl |
|---|---|---|
| N | 9 | 10 |
| Mean score (0-2) | 1.333 | 1.200 |
| Exact match rate | 44.4% | 30.0% |
| Partial+ match rate | 88.9% | 90.0% |

### Reframing

| Metric | v2-haiku-baseline | v2-haiku-kyl |
|---|---|---|
| N | 10 | 10 |
| Mean score (0-2) | 1.200 | 1.400 |
| Exact match rate | 30.0% | 40.0% |
| Partial+ match rate | 90.0% | 100.0% |

### Verification

| Metric | v2-haiku-baseline | v2-haiku-kyl |
|---|---|---|
| N | 10 | 10 |
| Mean score (0-2) | 1.700 | 1.500 |
| Exact match rate | 70.0% | 50.0% |
| Partial+ match rate | 100.0% | 100.0% |

## Difficulty Prediction

### v2-haiku-baseline
_Model difficulty predictions not yet extracted -- correlation requires 'difficulty' field in model responses_
- Tasks with expected difficulty labels: 39

### v2-haiku-kyl
_Model difficulty predictions not yet extracted -- correlation requires 'difficulty' field in model responses_
- Tasks with expected difficulty labels: 40

## Statistical Comparison

### Wilcoxon Signed-Rank Test (v2-haiku-baseline vs v2-haiku-kyl)

- N pairs: 39
- Test statistic: 56.0
- p-value: 0.7963
- Mean score (condition 1): 1.128
- Mean score (condition 2): 1.154
- Mean difference: -0.026
- Effect size (r): 0.041

\* p < 0.05, \*\* p < 0.01

## Judge & Cache Statistics

| Stat | v2-haiku-baseline | v2-haiku-kyl |
|---|---|---|
| Judge calls | 40 | 40 |
| Cache hits | 17 | 0 |
| Judge errors | 1 | 0 |
| Cache hit rate | 42.5% | 0.0% |
