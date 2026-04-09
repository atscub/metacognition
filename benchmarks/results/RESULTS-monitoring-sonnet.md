# Dimension 1: Metacognitive Monitoring Results

## Overall Metrics

| Metric | v2-sonnet-baseline | v2-sonnet-kyl |
|---|---|---|
| N (valid / total) | 100 / 100 | 69 / 100 |
| Parse failure rate | 0.0% | 31.0% |
| Accuracy | 0.2 | 0.2899 |
| Mean confidence | 55.17 | 31.9 |
| ECE (lower is better) | 0.3517 | 0.1375 |
| AUROC (higher is better) | 0.6131 | 0.7781 |
| Brier score (lower is better) | 0.3259 | 0.192 |
| Selective accuracy @80% | 0.2375 (n=80) | 0.3571 (n=56) |

## AUROC Bootstrap Confidence Intervals

- **v2-sonnet-baseline**: 0.6116 [0.495, 0.7271] (n_bootstrap=2000)
- **v2-sonnet-kyl**: 0.7784 [0.6653, 0.8759] (n_bootstrap=2000)

## Per-Difficulty Breakdown

### Difficulty: easy

| Metric | v2-sonnet-baseline | v2-sonnet-kyl |
|---|---|---|
| N | 30 | 30 |
| Accuracy | 0.2333 | 0.2667 |
| Mean confidence | 38.37 | 25.5 |
| ECE | 0.1723 | 0.0783 |
| AUROC | 0.8261 | 0.9233 |
| Brier | 0.1559 | 0.0979 |

### Difficulty: hard

| Metric | v2-sonnet-baseline | v2-sonnet-kyl |
|---|---|---|
| N | 70 | 39 |
| Accuracy | 0.1857 | 0.3077 |
| Mean confidence | 62.37 | 36.82 |
| ECE | 0.462 | 0.2518 |
| AUROC | 0.5344 | 0.6574 |
| Brier | 0.3988 | 0.2643 |

## Calibration Curves

### v2-sonnet-baseline

| Bin | Mean confidence | Accuracy | Count |
|---|---|---|---|
| 0-10 | 5.0 | 0.0 | 6 |
| 10-20 | 11.25 | 0.0 | 8 |
| 20-30 | 24.36 | 0.0909 | 11 |
| 30-40 | 35.0 | 0.1 | 10 |
| 40-50 | 43.88 | 0.375 | 8 |
| 50-60 | 52.75 | 0.0 | 4 |
| 60-70 | 62.0 | 0.4286 | 7 |
| 70-80 | 72.0 | 0.4 | 20 |
| 80-90 | 84.0 | 0.1667 | 12 |
| 90-100 | 95.36 | 0.1429 | 14 |

### v2-sonnet-kyl

| Bin | Mean confidence | Accuracy | Count |
|---|---|---|---|
| 0-10 | 5.05 | 0.0 | 21 |
| 10-20 | 15.12 | 0.25 | 8 |
| 20-30 | 22.83 | 0.3333 | 12 |
| 30-40 | 33.71 | 0.5714 | 7 |
| 40-50 | 43.4 | 0.4 | 5 |
| 50-60 | -- | -- | 0 |
| 60-70 | 65.0 | 0.6667 | 3 |
| 70-80 | 72.86 | 0.5714 | 7 |
| 80-90 | 81.0 | 0.5 | 2 |
| 90-100 | 95.0 | 0.25 | 4 |

## Statistical Tests

### Paired t-test on Brier scores (v2-sonnet-baseline vs v2-sonnet-kyl)

- N pairs: 69
- t-statistic: 0.9206
- p-value: 0.3605
- Mean Brier difference: 0.0202
- Direction: second lower (better)

### Bootstrap AUROC comparison (v2-sonnet-baseline vs v2-sonnet-kyl)

- N pairs: 69
- Mean AUROC difference: -0.0172
- 95% CI: [-0.1, 0.0678]
- p-value: 0.669

## Parse Failure Rates

- **v2-sonnet-baseline**: 0.0% (0/100)
- **v2-sonnet-kyl**: 31.0% (31/100) **WARNING: >10% parse failures -- data unreliable**

\* p < 0.05, \*\* p < 0.01
