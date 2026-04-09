# Dimension 4: Bias Awareness (Bias Detection in Others)

## Overall Metrics

| Metric | v2-haiku-baseline | v2-haiku-kyl |
|---|---|---|
| Bias detection accuracy | 97.5% | 92.5% |
| Bias naming accuracy (of true positives) | 60.0% | 66.7% |
| False positive rate (clean flagged as biased) | 10.0% | 30.0% |
| False negative rate (biased flagged as clean) | 0.0% | 0.0% |
| Parse failure rate | 0.0% | 0.0% |
| Total tasks | 40 | 40 |

## Per-Bias-Type Detection Rate

| Bias Type | N | Detection (v2-haiku-baseline) | Naming (v2-haiku-baseline) | Detection (v2-haiku-kyl) | Naming (v2-haiku-kyl) |
|---|---|---|---|---|---|
| anchoring | 5 | 100.0% | 100.0% | 100.0% | 100.0% |
| authority | 5 | 100.0% | 100.0% | 100.0% | 100.0% |
| confirmation | 5 | 100.0% | 100.0% | 100.0% | 100.0% |
| framing | 5 | 100.0% | 60.0% | 100.0% | 40.0% |
| premature_closure | 5 | 100.0% | 0.0% | 100.0% | 40.0% |
| sycophancy | 5 | 100.0% | 0.0% | 100.0% | 20.0% |

## Confusion Matrix (Actual vs Predicted Bias Type)

### v2-haiku-baseline

| Actual \ Predicted | anchoring | authority | confirmation | framing | other | none |
|---|---|---|---|---|---|---|
| anchoring | 3 | 0 | 0 | 0 | 2 | 0 |
| authority | 0 | 4 | 0 | 0 | 1 | 0 |
| clean | 0 | 0 | 0 | 0 | 1 | 9 |
| confirmation | 0 | 0 | 3 | 0 | 2 | 0 |
| framing | 0 | 0 | 0 | 1 | 4 | 0 |
| premature_closure | 0 | 0 | 0 | 0 | 5 | 0 |
| sycophancy | 0 | 3 | 0 | 0 | 2 | 0 |

### v2-haiku-kyl

| Actual \ Predicted | authority | confirmation | other | none |
|---|---|---|---|---|
| anchoring | 0 | 0 | 5 | 0 |
| authority | 0 | 0 | 5 | 0 |
| clean | 0 | 0 | 3 | 7 |
| confirmation | 0 | 1 | 4 | 0 |
| framing | 0 | 0 | 5 | 0 |
| premature_closure | 0 | 0 | 5 | 0 |
| sycophancy | 1 | 0 | 4 | 0 |

## Statistical Comparison (Wilcoxon Signed-Rank Test)

- **N pairs**: 40
- **Non-zero differences**: 2
- **Test statistic**: 0.0
- **p-value**: 0.1573
- **Effect size (r)**: 0.2121
- **Mean detection score (v2-haiku-baseline)**: 0.975
- **Mean detection score (v2-haiku-kyl)**: 0.925

\* p < 0.05, \*\* p < 0.01
