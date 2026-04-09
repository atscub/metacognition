# Dimension 1: Metacognitive Monitoring Results

## Overall Metrics

| Metric | v2-haiku-baseline | v2-haiku-kyl |
|---|---|---|
| N (valid / total) | 100 / 100 | 97 / 100 |
| Parse failure rate | 0.0% | 3.0% |
| Accuracy | 0.08 | 0.0722 |
| Mean confidence | 43.77 | 31.79 |
| ECE (lower is better) | 0.3577 | 0.2509 |
| AUROC (higher is better) | 0.7228 | 0.7865 |
| Brier score (lower is better) | 0.2902 | 0.1962 |
| Selective accuracy @80% | 0.1 (n=80) | 0.0897 (n=78) |

## AUROC Bootstrap Confidence Intervals

- **v2-haiku-baseline**: 0.7202 [0.5975, 0.8262] (n_bootstrap=2000)
- **v2-haiku-kyl**: 0.7857 [0.6325, 0.9151] (n_bootstrap=1998)

## Per-Difficulty Breakdown

### Difficulty: easy

| Metric | v2-haiku-baseline | v2-haiku-kyl |
|---|---|---|
| N | 30 | 29 |
| Accuracy | 0.1 | 0.069 |
| Mean confidence | 19.77 | 12.9 |
| ECE | 0.1097 | 0.1131 |
| AUROC | 0.9753 | 0.9815 |
| Brier | 0.0517 | 0.0327 |

### Difficulty: hard

| Metric | v2-haiku-baseline | v2-haiku-kyl |
|---|---|---|
| N | 70 | 68 |
| Accuracy | 0.0714 | 0.0735 |
| Mean confidence | 54.06 | 39.85 |
| ECE | 0.4691 | 0.3324 |
| AUROC | 0.6185 | 0.7143 |
| Brier | 0.3925 | 0.2659 |

## Calibration Curves

### v2-haiku-baseline

| Bin | Mean confidence | Accuracy | Count |
|---|---|---|---|
| 0-10 | 5.0 | 0.0 | 29 |
| 10-20 | 15.0 | 0.0 | 19 |
| 20-30 | 25.0 | 0.0 | 2 |
| 30-40 | 35.0 | 0.0 | 3 |
| 40-50 | 45.0 | 0.4 | 5 |
| 50-60 | -- | -- | 0 |
| 60-70 | 64.0 | 0.0 | 3 |
| 70-80 | 75.27 | 0.2727 | 11 |
| 80-90 | 85.11 | 0.1111 | 9 |
| 90-100 | 93.74 | 0.1053 | 19 |

### v2-haiku-kyl

| Bin | Mean confidence | Accuracy | Count |
|---|---|---|---|
| 0-10 | 4.93 | 0.0 | 45 |
| 10-20 | 15.0 | 0.0833 | 12 |
| 20-30 | 25.0 | 0.3333 | 3 |
| 30-40 | 35.0 | 0.0 | 3 |
| 40-50 | 45.0 | 0.2 | 5 |
| 50-60 | 56.5 | 0.0 | 2 |
| 60-70 | 62.57 | 0.1429 | 7 |
| 70-80 | 75.0 | 0.1429 | 7 |
| 80-90 | 86.67 | 0.0 | 3 |
| 90-100 | 94.1 | 0.2 | 10 |

## Statistical Tests

### Paired t-test on Brier scores (v2-haiku-baseline vs v2-haiku-kyl)

- N pairs: 97
- t-statistic: 4.5119
- p-value: 0.0 **
- Mean Brier difference: 0.0901
- Direction: second lower (better)

### Bootstrap AUROC comparison (v2-haiku-baseline vs v2-haiku-kyl)

- N pairs: 97
- Mean AUROC difference: -0.06
- 95% CI: [-0.2146, 0.0827]
- p-value: 0.4212

## Parse Failure Rates

- **v2-haiku-baseline**: 0.0% (0/100)
- **v2-haiku-kyl**: 3.0% (3/100)

\* p < 0.05, \*\* p < 0.01
