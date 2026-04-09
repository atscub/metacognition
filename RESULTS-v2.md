# KYL Metacognition Benchmark v2 — Combined Results

## Executive Summary

KYL showed improvements on: Control: KYL improved F1 (abstain/answer decision) by 5.0% (0.762 -> 0.800); Knowledge: KYL improved Exact match rate (score=2) by 2.2% (27.5% -> 28.1%) (not significant); Monitoring: KYL improved ECE (lower is better) by 14.6% (0.3517 -> 0.3002) (p = 0.0159); Wild: KYL improved Mean score by 25.0% (2.4 -> 3.0) (not significant). KYL showed regressions on: Bias Awareness: KYL worsened Detection accuracy (100.0% -> 90.0%).

## Per-Dimension Summary

| Dimension | Primary metric | v2-haiku-baseline | v2-haiku-kyl | v2-sonnet-baseline | v2-sonnet-kyl | p-value |
|---|---|---|---|---|---|---|
| Bias Awareness | Detection accuracy | 97.5% | 92.5% | 100.0% | 90.0% | -- |
| Control | F1 (abstain/answer decision) | 0.824 | 0.919 | 0.762 | 0.800 | -- |
| Knowledge | Exact match rate (score=2) | 35.9% | 30.0% | 27.5% | 28.1% | 0.3173 |
| Monitoring | ECE (lower is better) | 0.3577 | 0.2509 | 0.3517 | 0.3002 | 0.0159 |
| Wild | Mean score | 1.8 | 2.4 | 2.4 | 3.0 | 0.5 |

## Cross-Dimension Patterns

The following patterns emerge from comparing KYL effects across dimensions:

- **Bias Awareness** (Detection accuracy): v2-haiku-baseline: 97.5%, v2-haiku-kyl: 92.5%, v2-sonnet-baseline: 100.0%, v2-sonnet-kyl: 90.0% (no stat test)
- **Control** (F1 (abstain/answer decision)): v2-haiku-baseline: 0.824, v2-haiku-kyl: 0.919, v2-sonnet-baseline: 0.762, v2-sonnet-kyl: 0.800 (no stat test)
- **Knowledge** (Exact match rate (score=2)): v2-haiku-baseline: 35.9%, v2-haiku-kyl: 30.0%, v2-sonnet-baseline: 27.5%, v2-sonnet-kyl: 28.1% (p = 0.3173)
- **Monitoring** (ECE (lower is better)): v2-haiku-baseline: 0.3577, v2-haiku-kyl: 0.2509, v2-sonnet-baseline: 0.3517, v2-sonnet-kyl: 0.3002 (p = 0.0159)
- **Wild** (Mean score): v2-haiku-baseline: 1.8, v2-haiku-kyl: 2.4, v2-sonnet-baseline: 2.4, v2-sonnet-kyl: 3.0 (p = 0.5)

## Methodology

### Benchmark Design

v2 measures metacognition independently from cognition across four academic dimensions plus observed-failure replication:

- **Dim 1: Metacognitive Monitoring**: ECE (lower is better)
- **Dim 2: Metacognitive Knowledge**: Exact match rate (score=2)
- **Dim 3: Metacognitive Control**: F1 (abstain/answer decision)
- **Dim 4: Bias Awareness**: Detection accuracy
- **Dim W: Observed-Failure Replication**: Mean score

### Conditions

- **Baseline**: `claude -p --disable-slash-commands --no-session-persistence`
- **KYL**: `claude -p --plugin-dir plugins/metacognition --no-session-persistence`

### Dimensions Scored

- Dim 4: Bias Awareness: 4 condition(s) (v2-haiku-baseline, v2-haiku-kyl, v2-sonnet-baseline, v2-sonnet-kyl)
- Dim 3: Metacognitive Control: 4 condition(s) (v2-haiku-baseline, v2-haiku-kyl, v2-sonnet-baseline, v2-sonnet-kyl)
- Dim 2: Metacognitive Knowledge: 4 condition(s) (v2-haiku-baseline, v2-haiku-kyl, v2-sonnet-baseline, v2-sonnet-kyl)
- Dim 1: Metacognitive Monitoring: 4 condition(s) (v2-haiku-baseline, v2-haiku-kyl, v2-sonnet-baseline, v2-sonnet-kyl)
- Dim W: Observed-Failure Replication: 4 condition(s) (v2-haiku-baseline, v2-haiku-kyl, v2-sonnet-baseline, v2-sonnet-kyl)

### Source Files

- Bias Awareness: `/home/abraham/Personal/AI_2026/metacognition/benchmarks/results/RESULTS-bias-awareness.md`
- Control: `/home/abraham/Personal/AI_2026/metacognition/benchmarks/results/RESULTS-control.md`
- Knowledge: `/home/abraham/Personal/AI_2026/metacognition/benchmarks/results/RESULTS-knowledge.md`
- Monitoring: `/home/abraham/Personal/AI_2026/metacognition/benchmarks/results/RESULTS-monitoring.md`
- Wild: `/home/abraham/Personal/AI_2026/metacognition/benchmarks/results/RESULTS-wild.md`
