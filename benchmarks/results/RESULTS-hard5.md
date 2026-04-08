# Dimension 1: Metacognitive Monitoring Results

## Overall Metrics

| Metric | v2-hard5-baseline | v2-hard5-kyl |
|---|---|---|
| N (valid / total) | 5 / 5 | 5 / 5 |
| Parse failure rate | 0.0% | 0.0% |
| Accuracy | 0.4 | 0.4 |
| Mean confidence | 48.8 | 44.0 |
| ECE (lower is better) | 0.272 | 0.16 |
| AUROC (higher is better) | 1.0 | 1.0 |
| Brier score (lower is better) | 0.0972 | 0.036 |
| Selective accuracy @80% | 0.5 (n=4) | 0.5 (n=4) |

## AUROC Bootstrap Confidence Intervals

- **v2-hard5-baseline**: 1.0 [1.0, 1.0] (n_bootstrap=1830)
- **v2-hard5-kyl**: 1.0 [1.0, 1.0] (n_bootstrap=1830)

## Per-Difficulty Breakdown

### Difficulty: hard

| Metric | v2-hard5-baseline | v2-hard5-kyl |
|---|---|---|
| N | 5 | 5 |
| Accuracy | 0.4 | 0.4 |
| Mean confidence | 48.8 | 44.0 |
| ECE | 0.272 | 0.16 |
| AUROC | 1.0 | 1.0 |
| Brier | 0.0972 | 0.036 |

## Calibration Curves

### v2-hard5-baseline

| Bin | Mean confidence | Accuracy | Count |
|---|---|---|---|
| 0-10 | -- | -- | 0 |
| 10-20 | 10.0 | 0.0 | 1 |
| 20-30 | 25.0 | 0.0 | 1 |
| 30-40 | -- | -- | 0 |
| 40-50 | -- | -- | 0 |
| 50-60 | 55.0 | 0.0 | 1 |
| 60-70 | -- | -- | 0 |
| 70-80 | 72.0 | 1.0 | 1 |
| 80-90 | 82.0 | 1.0 | 1 |
| 90-100 | -- | -- | 0 |

### v2-hard5-kyl

| Bin | Mean confidence | Accuracy | Count |
|---|---|---|---|
| 0-10 | 5.0 | 0.0 | 1 |
| 10-20 | 10.0 | 0.0 | 1 |
| 20-30 | -- | -- | 0 |
| 30-40 | 35.0 | 0.0 | 1 |
| 40-50 | -- | -- | 0 |
| 50-60 | -- | -- | 0 |
| 60-70 | -- | -- | 0 |
| 70-80 | -- | -- | 0 |
| 80-90 | 85.0 | 1.0 | 2 |
| 90-100 | -- | -- | 0 |

## Statistical Tests

### Paired t-test on Brier scores (v2-hard5-baseline vs v2-hard5-kyl)

- N pairs: 5
- t-statistic: 1.9094
- p-value: 0.1288
- Mean Brier difference: 0.0612
- Direction: second lower (better)

### Bootstrap AUROC comparison (v2-hard5-baseline vs v2-hard5-kyl)

_Insufficient paired data for bootstrap AUROC comparison_

## Parse Failure Rates

- **v2-hard5-baseline**: 0.0% (0/5)
- **v2-hard5-kyl**: 0.0% (0/5)

\* p < 0.05, \*\* p < 0.01
