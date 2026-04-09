# Dimension 1: Metacognitive Monitoring Results

## Overall Metrics

| Metric | v2-sonnet-baseline | v2-sonnet-kyl | v2-haiku-baseline | v2-haiku-kyl |
|---|---|---|---|---|
| N (valid / total) | 100 / 100 | 100 / 100 | 100 / 100 | 97 / 100 |
| Parse failure rate | 0.0% | 0.0% | 0.0% | 3.0% |
| Accuracy | 0.2 | 0.17 | 0.08 | 0.0722 |
| Mean confidence | 55.17 | 44.76 | 43.77 | 31.79 |
| ECE (lower is better) | 0.3517 | 0.3002 | 0.3577 | 0.2509 |
| AUROC (higher is better) | 0.6131 | 0.6917 | 0.7228 | 0.7865 |
| Brier score (lower is better) | 0.3259 | 0.2673 | 0.2902 | 0.1962 |
| Selective accuracy @80% | 0.2375 (n=80) | 0.2125 (n=80) | 0.1 (n=80) | 0.0897 (n=78) |

## AUROC Bootstrap Confidence Intervals

- **v2-sonnet-baseline**: 0.6116 [0.495, 0.7271] (n_bootstrap=2000)
- **v2-sonnet-kyl**: 0.691 [0.5792, 0.7949] (n_bootstrap=2000)
- **v2-haiku-baseline**: 0.7202 [0.5975, 0.8262] (n_bootstrap=2000)
- **v2-haiku-kyl**: 0.7857 [0.6325, 0.9151] (n_bootstrap=1998)

## Per-Difficulty Breakdown

### Difficulty: easy

| Metric | v2-sonnet-baseline | v2-sonnet-kyl | v2-haiku-baseline | v2-haiku-kyl |
|---|---|---|---|---|
| N | 30 | 30 | 30 | 29 |
| Accuracy | 0.2333 | 0.2333 | 0.1 | 0.069 |
| Mean confidence | 38.37 | 26.3 | 19.77 | 12.9 |
| ECE | 0.1723 | 0.1097 | 0.1097 | 0.1131 |
| AUROC | 0.8261 | 0.9627 | 0.9753 | 0.9815 |
| Brier | 0.1559 | 0.0708 | 0.0517 | 0.0327 |

### Difficulty: hard

| Metric | v2-sonnet-baseline | v2-sonnet-kyl | v2-haiku-baseline | v2-haiku-kyl |
|---|---|---|---|---|
| N | 70 | 70 | 70 | 68 |
| Accuracy | 0.1857 | 0.1429 | 0.0714 | 0.0735 |
| Mean confidence | 62.37 | 52.67 | 54.06 | 39.85 |
| ECE | 0.462 | 0.4161 | 0.4691 | 0.3324 |
| AUROC | 0.5344 | 0.6 | 0.6185 | 0.7143 |
| Brier | 0.3988 | 0.3515 | 0.3925 | 0.2659 |

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
| 0-10 | 5.14 | 0.0 | 22 |
| 10-20 | 14.5 | 0.0 | 10 |
| 20-30 | 22.56 | 0.2222 | 9 |
| 30-40 | 33.83 | 0.0833 | 12 |
| 40-50 | 43.5 | 1.0 | 2 |
| 50-60 | 52.0 | 0.3333 | 3 |
| 60-70 | 63.2 | 0.3 | 10 |
| 70-80 | 73.33 | 0.4444 | 9 |
| 80-90 | 85.46 | 0.1538 | 13 |
| 90-100 | 96.3 | 0.2 | 10 |

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

### Paired t-test on Brier scores (v2-sonnet-baseline vs v2-sonnet-kyl)

- N pairs: 100
- t-statistic: 2.4542
- p-value: 0.0159 *
- Mean Brier difference: 0.0586
- Direction: second lower (better)

### Bootstrap AUROC comparison (v2-sonnet-baseline vs v2-sonnet-kyl)

- N pairs: 100
- Mean AUROC difference: -0.0783
- 95% CI: [-0.1866, 0.0288]
- p-value: 0.156

## Parse Failure Rates

- **v2-sonnet-baseline**: 0.0% (0/100)
- **v2-sonnet-kyl**: 0.0% (0/100)
- **v2-haiku-baseline**: 0.0% (0/100)
- **v2-haiku-kyl**: 3.0% (3/100)

\* p < 0.05, \*\* p < 0.01
