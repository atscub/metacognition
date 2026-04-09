# Dimension 4: Bias Awareness (Bias Detection in Others)

## Overall Metrics

| Metric | v2-sonnet-baseline | v2-sonnet-kyl |
|---|---|---|
| Bias detection accuracy | 100.0% | 90.0% |
| Bias naming accuracy (of true positives) | 70.0% | 73.3% |
| False positive rate (clean flagged as biased) | 0.0% | 40.0% |
| False negative rate (biased flagged as clean) | 0.0% | 0.0% |
| Parse failure rate | 0.0% | 0.0% |
| Total tasks | 40 | 40 |

## Per-Bias-Type Detection Rate

| Bias Type | N | Detection (v2-sonnet-baseline) | Naming (v2-sonnet-baseline) | Detection (v2-sonnet-kyl) | Naming (v2-sonnet-kyl) |
|---|---|---|---|---|---|
| anchoring | 5 | 100.0% | 100.0% | 100.0% | 100.0% |
| authority | 5 | 100.0% | 100.0% | 100.0% | 100.0% |
| confirmation | 5 | 100.0% | 100.0% | 100.0% | 100.0% |
| framing | 5 | 100.0% | 80.0% | 100.0% | 60.0% |
| premature_closure | 5 | 100.0% | 20.0% | 100.0% | 20.0% |
| sycophancy | 5 | 100.0% | 20.0% | 100.0% | 60.0% |

## Confusion Matrix (Actual vs Predicted Bias Type)

### v2-sonnet-baseline

| Actual \ Predicted | anchoring | authority | confirmation | framing | premature_closure | other | none |
|---|---|---|---|---|---|---|---|
| anchoring | 3 | 0 | 0 | 0 | 0 | 2 | 0 |
| authority | 0 | 2 | 0 | 0 | 0 | 3 | 0 |
| clean | 0 | 0 | 0 | 0 | 0 | 0 | 10 |
| confirmation | 0 | 0 | 5 | 0 | 0 | 0 | 0 |
| framing | 0 | 0 | 0 | 4 | 0 | 1 | 0 |
| premature_closure | 0 | 0 | 0 | 0 | 1 | 4 | 0 |
| sycophancy | 0 | 2 | 0 | 0 | 0 | 3 | 0 |

### v2-sonnet-kyl

| Actual \ Predicted | anchoring | authority | confirmation | framing | sycophancy | other | none |
|---|---|---|---|---|---|---|---|
| anchoring | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| authority | 0 | 4 | 0 | 0 | 0 | 1 | 0 |
| clean | 1 | 0 | 3 | 0 | 0 | 0 | 6 |
| confirmation | 0 | 0 | 5 | 0 | 0 | 0 | 0 |
| framing | 0 | 0 | 1 | 2 | 0 | 2 | 0 |
| premature_closure | 0 | 0 | 4 | 0 | 0 | 1 | 0 |
| sycophancy | 0 | 1 | 0 | 0 | 3 | 1 | 0 |

## Statistical Comparison (Wilcoxon Signed-Rank Test)

- **N pairs**: 40
- **Non-zero differences**: 4
- **Test statistic**: 0.0
- **p-value**: 0.0455 *
- **Effect size (r)**: 0.2887
- **Mean detection score (v2-sonnet-baseline)**: 1.0
- **Mean detection score (v2-sonnet-kyl)**: 0.9

\* p < 0.05, \*\* p < 0.01
