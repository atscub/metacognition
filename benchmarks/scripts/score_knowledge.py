#!/usr/bin/env python3
"""Score Dimension 2: Metacognitive Knowledge (Strategy Selection).

Uses LLM-as-judge to score whether the model correctly identified the
cognitive strategy a problem requires.  Compares baseline and KYL conditions.

Usage:
    python scripts/score_knowledge.py \
      --runs runs/v2-sonnet-baseline runs/v2-sonnet-kyl \
      --tasks tasks/v2/knowledge/ \
      --output results/RESULTS-knowledge.md \
      --judge-model haiku

Metrics:
  - Strategy match rate (mean judge score, 0-2 scale)
  - Exact match rate (% scoring 2)
  - Per-strategy breakdown (decomposition, reframing, verification, abstention)
  - Difficulty prediction correlation
  - Wilcoxon signed-rank test between conditions
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import yaml
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS_DIR = PROJECT_ROOT / "benchmarks"
JUDGE_CACHE_DIR = BENCHMARKS_DIR / "eval" / "judge_cache"

VALID_STRATEGIES = {"decomposition", "reframing", "verification", "abstention"}


# ---------------------------------------------------------------------------
# Task loading
# ---------------------------------------------------------------------------


def load_tasks(tasks_dir: Path) -> dict[str, dict]:
    """Load v2 knowledge task YAML files.

    Returns dict keyed by task id with fields: expected_strategy,
    expected_difficulty, prompt.
    """
    tasks: dict[str, dict] = {}
    for yaml_path in sorted(tasks_dir.rglob("*.yaml")):
        with open(yaml_path) as f:
            task = yaml.safe_load(f)
        if task is None:
            continue
        # Only load knowledge-dimension tasks (or tasks without a dimension
        # field, assuming directory-based filtering was done by the caller)
        dim = task.get("dimension", "knowledge")
        if dim != "knowledge":
            continue
        tid = task.get("id", yaml_path.stem)
        tasks[tid] = {
            "expected_strategy": task.get("expected_strategy", "unknown"),
            "expected_difficulty": task.get("expected_difficulty", "unknown"),
            "prompt": task.get("prompt", ""),
        }
    return tasks


# ---------------------------------------------------------------------------
# Response parsing (same patterns as score_monitoring.py / score_control.py)
# ---------------------------------------------------------------------------

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def extract_json(text: str) -> dict | None:
    """Extract the first valid JSON object from *text*."""
    # Try markdown fenced block first
    m = _JSON_FENCE_RE.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Try the full text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find the first { ... } block (greedy on closing brace)
    for start in range(len(text)):
        if text[start] == "{":
            for end in range(len(text), start, -1):
                if text[end - 1] == "}":
                    try:
                        return json.loads(text[start:end])
                    except json.JSONDecodeError:
                        continue
    return None


def load_run_responses(run_dir: Path) -> dict[str, dict]:
    """Load all response JSON files from a run directory.

    Returns dict keyed by task_id with fields: parsed (dict|None),
    raw (str), parse_ok (bool).
    """
    responses: dict[str, dict] = {}
    for json_path in sorted(run_dir.rglob("*.json")):
        if json_path.name.startswith("_"):
            continue
        with open(json_path) as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                continue

        raw_response = data.get("response", "")
        result_text = raw_response

        # claude CLI wraps output in a JSON envelope with a `result` field
        if isinstance(raw_response, str):
            try:
                envelope = json.loads(raw_response)
                if isinstance(envelope, dict) and "result" in envelope:
                    result_text = envelope["result"]
            except (json.JSONDecodeError, TypeError):
                pass

        parsed = extract_json(result_text) if isinstance(result_text, str) else None

        # Determine task id: prefer explicit task_id field, then id, then stem
        tid = data.get("task_id", data.get("id", json_path.stem))

        responses[tid] = {
            "parsed": parsed,
            "raw": result_text if isinstance(result_text, str) else str(result_text),
            "parse_ok": parsed is not None,
        }

    return responses


# ---------------------------------------------------------------------------
# Judge: LLM-as-judge via claude CLI
# ---------------------------------------------------------------------------


def _cache_key(task_id: str, condition: str, model_response: str) -> str:
    """Deterministic hash for judge cache lookup."""
    payload = json.dumps(
        {"task_id": task_id, "condition": condition, "model_response": model_response},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _load_cache(cache_key: str) -> dict | None:
    """Load a cached judge result if it exists."""
    cache_path = JUDGE_CACHE_DIR / f"{cache_key}.json"
    if cache_path.exists():
        try:
            with open(cache_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _save_cache(cache_key: str, result: dict) -> None:
    """Persist a judge result to disk."""
    JUDGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = JUDGE_CACHE_DIR / f"{cache_key}.json"
    with open(cache_path, "w") as f:
        json.dump(result, f, indent=2)


def judge_strategy_match(
    task_id: str,
    condition: str,
    expected_strategy: str,
    model_strategy: str,
    model_problem_type: str,
    judge_model: str,
) -> dict:
    """Call the judge model to score strategy match.

    Returns dict with keys: score (0-2), reasoning (str), cached (bool).
    """
    # Build the input string that determines the cache key
    model_response_key = json.dumps(
        {"strategy": model_strategy, "problem_type": model_problem_type},
        sort_keys=True,
    )
    key = _cache_key(task_id, condition, model_response_key)

    # Check cache first
    cached = _load_cache(key)
    if cached is not None:
        cached["cached"] = True
        return cached

    # Build judge prompt
    judge_prompt = f"""You are evaluating whether a model correctly identified the cognitive strategy needed for a problem.

Expected strategy: {expected_strategy}
Model's stated strategy: {model_strategy}
Model's problem type analysis: {model_problem_type}

Score the strategy match:
- 2 = Exact match (model identified the correct strategy or a clear synonym)
- 1 = Partial match (model identified a related strategy that partially overlaps)
- 0 = Wrong (model identified an unrelated strategy)

Respond ONLY with JSON: {{"score": 0, "reasoning": "brief explanation"}}"""

    # Call claude CLI
    try:
        result = subprocess.run(
            [
                "claude",
                "-p",
                judge_prompt,
                "--model",
                judge_model,
                "--output-format",
                "json",
                "--no-session-persistence",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        output_text = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {
            "score": -1,
            "reasoning": f"Judge call failed: {e}",
            "cached": False,
        }

    # Parse the judge response -- it comes back as a CLI JSON envelope
    parsed = extract_json(output_text)
    if parsed is None:
        return {
            "score": -1,
            "reasoning": f"Could not parse judge output: {output_text[:200]}",
            "cached": False,
        }

    # The CLI JSON envelope has a `result` field containing the model's text
    if "result" in parsed and isinstance(parsed["result"], str):
        inner = extract_json(parsed["result"])
        if inner is not None:
            parsed = inner

    # Validate score
    score = parsed.get("score")
    if score is None or score not in (0, 1, 2):
        try:
            score = int(score)
            score = max(0, min(2, score))
        except (TypeError, ValueError):
            score = -1

    judge_result = {
        "score": score,
        "reasoning": parsed.get("reasoning", "no reasoning provided"),
    }

    # Cache the result
    _save_cache(key, judge_result)
    judge_result["cached"] = False
    return judge_result


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score_condition(
    responses: dict[str, dict],
    tasks: dict[str, dict],
    condition_label: str,
    judge_model: str,
) -> dict:
    """Score a single condition using the LLM-as-judge.

    Returns a dict with metrics, per-task details, and cache stats.
    """
    details: list[dict] = []
    parse_failures = 0
    judge_calls = 0
    judge_cache_hits = 0
    judge_errors = 0
    total = 0

    for tid, task_info in tasks.items():
        if tid not in responses:
            continue
        total += 1
        resp = responses[tid]

        if not resp["parse_ok"]:
            parse_failures += 1
            details.append({
                "task_id": tid,
                "expected_strategy": task_info["expected_strategy"],
                "model_strategy": None,
                "model_problem_type": None,
                "judge_score": -1,
                "judge_reasoning": "Parse failure -- no structured response",
                "parse_ok": False,
                "cached": False,
            })
            continue

        parsed = resp["parsed"]
        model_strategy = str(parsed.get("strategy", "")).strip()
        model_problem_type = str(parsed.get("problem_type", "")).strip()

        if not model_strategy:
            # No strategy field -- try alternative field names
            model_strategy = str(
                parsed.get("cognitive_strategy", parsed.get("approach", ""))
            ).strip()

        # Call the judge
        judge_calls += 1
        judge_result = judge_strategy_match(
            task_id=tid,
            condition=condition_label,
            expected_strategy=task_info["expected_strategy"],
            model_strategy=model_strategy,
            model_problem_type=model_problem_type,
            judge_model=judge_model,
        )

        if judge_result.get("cached"):
            judge_cache_hits += 1
        if judge_result["score"] == -1:
            judge_errors += 1

        details.append({
            "task_id": tid,
            "expected_strategy": task_info["expected_strategy"],
            "model_strategy": model_strategy or None,
            "model_problem_type": model_problem_type or None,
            "judge_score": judge_result["score"],
            "judge_reasoning": judge_result["reasoning"],
            "parse_ok": True,
            "cached": judge_result.get("cached", False),
        })

    if total == 0:
        return {"error": "No matching tasks found between run and task definitions"}

    # --- Compute metrics ---

    # Filter to valid judge scores (exclude -1 errors)
    valid = [d for d in details if d["judge_score"] >= 0]
    scores = np.array([d["judge_score"] for d in valid]) if valid else np.array([])

    # 1. Strategy match rate: mean judge score (0-2 scale)
    strategy_match_rate = float(scores.mean()) if len(scores) > 0 else float("nan")

    # 2. Exact match rate: % scoring 2
    exact_match_rate = (
        float(np.sum(scores == 2) / len(scores)) if len(scores) > 0 else float("nan")
    )

    # 3. Partial match rate: % scoring >= 1
    partial_match_rate = (
        float(np.sum(scores >= 1) / len(scores)) if len(scores) > 0 else float("nan")
    )

    # 4. Per-strategy breakdown
    per_strategy: dict[str, dict] = {}
    for strat in VALID_STRATEGIES:
        strat_details = [d for d in valid if d["expected_strategy"] == strat]
        if not strat_details:
            continue
        strat_scores = np.array([d["judge_score"] for d in strat_details])
        per_strategy[strat] = {
            "n": len(strat_details),
            "mean_score": round(float(strat_scores.mean()), 3),
            "exact_match_rate": round(float(np.sum(strat_scores == 2) / len(strat_scores)), 3),
            "partial_match_rate": round(float(np.sum(strat_scores >= 1) / len(strat_scores)), 3),
        }

    # 5. Difficulty prediction (if model responses have difficulty info)
    difficulty_correlation = _compute_difficulty_correlation(details, tasks)

    return {
        "metrics": {
            "strategy_match_rate": round(strategy_match_rate, 3)
            if not np.isnan(strategy_match_rate)
            else float("nan"),
            "exact_match_rate": round(exact_match_rate, 3)
            if not np.isnan(exact_match_rate)
            else float("nan"),
            "partial_match_rate": round(partial_match_rate, 3)
            if not np.isnan(partial_match_rate)
            else float("nan"),
        },
        "per_strategy": per_strategy,
        "difficulty_correlation": difficulty_correlation,
        "details": details,
        "n_total": total,
        "n_valid": len(valid),
        "n_parse_fail": parse_failures,
        "parse_fail_rate": round(parse_failures / total, 3) if total > 0 else 0.0,
        "judge_stats": {
            "total_calls": judge_calls,
            "cache_hits": judge_cache_hits,
            "errors": judge_errors,
        },
    }


def _compute_difficulty_correlation(
    details: list[dict], tasks: dict[str, dict]
) -> dict | None:
    """If model responses include difficulty predictions, correlate with expected difficulty.

    Maps expected_difficulty labels to numeric values:
      easy=1, medium=2, hard=3
    and checks if the model's hardest_part / difficulty prediction correlates.
    """
    difficulty_map = {"easy": 1, "medium": 2, "hard": 3}

    predicted = []
    expected = []

    for d in details:
        if not d["parse_ok"] or d["judge_score"] < 0:
            continue
        tid = d["task_id"]
        task_info = tasks.get(tid, {})
        exp_diff = task_info.get("expected_difficulty", "unknown")
        if exp_diff not in difficulty_map:
            continue

        # Check if the model response contained difficulty info
        # We don't have direct access to parsed here, so we look for
        # difficulty-related information in the model's problem_type
        # This is a best-effort heuristic
        # For a proper implementation, we'd need the full parsed response
        # For now, skip if we can't extract model difficulty prediction
        expected.append(difficulty_map[exp_diff])

    if len(expected) < 5:
        return None

    # Without model difficulty predictions, we can report the distribution
    return {
        "n_with_expected_difficulty": len(expected),
        "note": "Model difficulty predictions not yet extracted -- "
        "correlation requires 'difficulty' field in model responses",
    }


# ---------------------------------------------------------------------------
# Statistical tests
# ---------------------------------------------------------------------------


def wilcoxon_test(
    scores_a: dict[str, int],
    scores_b: dict[str, int],
) -> dict:
    """Wilcoxon signed-rank test on judge scores between two conditions.

    Args:
        scores_a: dict of task_id -> judge score for condition A
        scores_b: dict of task_id -> judge score for condition B

    Returns test result dict.
    """
    common = sorted(set(scores_a) & set(scores_b))
    # Filter to tasks where both have valid scores
    common = [t for t in common if scores_a[t] >= 0 and scores_b[t] >= 0]

    if len(common) < 5:
        return {
            "test": "wilcoxon_signed_rank",
            "n_pairs": len(common),
            "note": "Insufficient paired data (need >= 5 pairs)",
        }

    vals_a = np.array([scores_a[t] for t in common])
    vals_b = np.array([scores_b[t] for t in common])
    diffs = vals_a - vals_b

    # Wilcoxon requires at least one non-zero difference
    if np.all(diffs == 0):
        return {
            "test": "wilcoxon_signed_rank",
            "n_pairs": len(common),
            "note": "All differences are zero -- conditions produced identical scores",
        }

    try:
        stat, p_value = stats.wilcoxon(vals_a, vals_b)
    except ValueError as e:
        return {
            "test": "wilcoxon_signed_rank",
            "n_pairs": len(common),
            "note": f"Test failed: {e}",
        }

    # Effect size: r = Z / sqrt(N)
    z_score = stats.norm.ppf(p_value / 2)
    effect_r = abs(z_score) / np.sqrt(len(common))

    return {
        "test": "wilcoxon_signed_rank",
        "n_pairs": len(common),
        "statistic": round(float(stat), 4),
        "p_value": round(float(p_value), 4),
        "mean_a": round(float(vals_a.mean()), 3),
        "mean_b": round(float(vals_b.mean()), 3),
        "mean_diff": round(float(diffs.mean()), 3),
        "effect_r": round(float(effect_r), 3),
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def fmt(val: float, decimals: int = 3) -> str:
    """Format a float for display, handling nan."""
    if val != val:  # nan
        return "N/A"
    return f"{val:.{decimals}f}"


def fmt_pct(val: float) -> str:
    """Format a float as percentage."""
    if val != val:
        return "N/A"
    return f"{val * 100:.1f}%"


def generate_report(
    results: dict[str, dict],
    stat_test: dict | None,
    run_labels: list[str],
) -> str:
    """Generate a markdown results report."""
    lines: list[str] = []
    lines.append("# Dimension 2: Metacognitive Knowledge (Strategy Selection)")
    lines.append("")

    # --- Overall metrics table ---
    lines.append("## Overall Metrics")
    lines.append("")
    header = "| Metric |"
    sep = "|---|"
    for label in run_labels:
        header += f" {label} |"
        sep += "---|"
    lines.append(header)
    lines.append(sep)

    metric_rows = [
        ("N (valid / total)", lambda r: f"{r['n_valid']} / {r['n_total']}"),
        ("Parse failure rate", lambda r: fmt_pct(r["parse_fail_rate"])),
        ("Strategy match rate (0-2)", lambda r: fmt(r["metrics"]["strategy_match_rate"])),
        ("Exact match rate (score=2)", lambda r: fmt_pct(r["metrics"]["exact_match_rate"])),
        ("Partial+ match rate (score>=1)", lambda r: fmt_pct(r["metrics"]["partial_match_rate"])),
    ]

    for label, fn in metric_rows:
        row = f"| {label} |"
        for rl in run_labels:
            r = results[rl]
            if "error" in r:
                row += " ERROR |"
            else:
                row += f" {fn(r)} |"
        lines.append(row)
    lines.append("")

    # --- Per-strategy breakdown ---
    lines.append("## Per-Strategy Breakdown")
    lines.append("")

    # Collect all strategies across conditions
    all_strategies = set()
    for rl in run_labels:
        r = results[rl]
        if "error" not in r:
            all_strategies.update(r.get("per_strategy", {}).keys())

    if all_strategies:
        for strat in sorted(all_strategies):
            lines.append(f"### {strat.capitalize()}")
            lines.append("")
            lines.append("| Metric |" + "".join(f" {l} |" for l in run_labels))
            lines.append("|---|" + "---|" * len(run_labels))

            strat_metrics = [
                ("N", lambda s: str(s["n"])),
                ("Mean score (0-2)", lambda s: fmt(s["mean_score"])),
                ("Exact match rate", lambda s: fmt_pct(s["exact_match_rate"])),
                ("Partial+ match rate", lambda s: fmt_pct(s["partial_match_rate"])),
            ]

            for metric_name, fn in strat_metrics:
                row = f"| {metric_name} |"
                for rl in run_labels:
                    r = results[rl]
                    ps = r.get("per_strategy", {}).get(strat)
                    if ps:
                        row += f" {fn(ps)} |"
                    else:
                        row += " -- |"
                lines.append(row)
            lines.append("")
    else:
        lines.append("_No per-strategy data available._")
        lines.append("")

    # --- Difficulty prediction ---
    lines.append("## Difficulty Prediction")
    lines.append("")
    has_diff = False
    for rl in run_labels:
        r = results[rl]
        dc = r.get("difficulty_correlation")
        if dc:
            has_diff = True
            lines.append(f"### {rl}")
            if "note" in dc:
                lines.append(f"_{dc['note']}_")
            if "n_with_expected_difficulty" in dc:
                lines.append(f"- Tasks with expected difficulty labels: {dc['n_with_expected_difficulty']}")
            lines.append("")
    if not has_diff:
        lines.append("_No difficulty prediction data available._")
        lines.append("")

    # --- Statistical test ---
    lines.append("## Statistical Comparison")
    lines.append("")

    if stat_test is None:
        lines.append("_Only one condition provided; no between-condition test._")
    elif "note" in stat_test:
        lines.append(f"### Wilcoxon Signed-Rank Test ({run_labels[0]} vs {run_labels[1]})")
        lines.append("")
        lines.append(f"_{stat_test['note']}_")
    else:
        lines.append(f"### Wilcoxon Signed-Rank Test ({run_labels[0]} vs {run_labels[1]})")
        lines.append("")
        p = stat_test.get("p_value", 1.0)
        sig = ""
        if p < 0.01:
            sig = " **"
        elif p < 0.05:
            sig = " *"
        lines.append(f"- N pairs: {stat_test['n_pairs']}")
        lines.append(f"- Test statistic: {stat_test['statistic']}")
        lines.append(f"- p-value: {stat_test['p_value']}{sig}")
        lines.append(f"- Mean score (condition 1): {stat_test['mean_a']}")
        lines.append(f"- Mean score (condition 2): {stat_test['mean_b']}")
        lines.append(f"- Mean difference: {stat_test['mean_diff']}")
        lines.append(f"- Effect size (r): {stat_test['effect_r']}")
    lines.append("")
    lines.append("\\* p < 0.05, \\*\\* p < 0.01")
    lines.append("")

    # --- Judge / cache stats ---
    lines.append("## Judge & Cache Statistics")
    lines.append("")
    lines.append("| Stat |" + "".join(f" {l} |" for l in run_labels))
    lines.append("|---|" + "---|" * len(run_labels))

    judge_rows = [
        ("Judge calls", lambda r: str(r["judge_stats"]["total_calls"])),
        ("Cache hits", lambda r: str(r["judge_stats"]["cache_hits"])),
        ("Judge errors", lambda r: str(r["judge_stats"]["errors"])),
        (
            "Cache hit rate",
            lambda r: fmt_pct(
                r["judge_stats"]["cache_hits"] / r["judge_stats"]["total_calls"]
            )
            if r["judge_stats"]["total_calls"] > 0
            else "N/A",
        ),
    ]

    for label, fn in judge_rows:
        row = f"| {label} |"
        for rl in run_labels:
            r = results[rl]
            if "error" in r:
                row += " ERROR |"
            else:
                row += f" {fn(r)} |"
        lines.append(row)
    lines.append("")

    # --- Parse failure warning ---
    for rl in run_labels:
        r = results[rl]
        if "error" not in r and r["parse_fail_rate"] > 0.10:
            lines.append(
                f"> **WARNING**: Parse failure rate for {rl} is "
                f"{fmt_pct(r['parse_fail_rate'])} (> 10%). Results may be unreliable."
            )
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score Dimension 2: Metacognitive Knowledge (Strategy Selection)."
    )
    parser.add_argument(
        "--runs",
        nargs="+",
        type=Path,
        required=True,
        help="Run directories to score (e.g. runs/v2-sonnet-baseline runs/v2-sonnet-kyl)",
    )
    parser.add_argument(
        "--tasks",
        type=Path,
        required=True,
        help="Directory containing v2 knowledge task YAML files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=BENCHMARKS_DIR / "results" / "RESULTS-knowledge.md",
        help="Output path for markdown results",
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        default="haiku",
        help="Model to use for LLM-as-judge scoring (default: haiku)",
    )
    args = parser.parse_args()

    # Resolve paths relative to BENCHMARKS_DIR if not absolute
    tasks_dir = args.tasks if args.tasks.is_absolute() else BENCHMARKS_DIR / args.tasks
    if not tasks_dir.is_dir():
        print(f"Error: tasks directory not found: {tasks_dir}", file=sys.stderr)
        sys.exit(1)

    run_dirs = []
    for r in args.runs:
        p = r if r.is_absolute() else BENCHMARKS_DIR / r
        if not p.is_dir():
            print(f"Warning: run directory not found: {p}", file=sys.stderr)
        run_dirs.append(p)

    output_path = args.output if args.output.is_absolute() else BENCHMARKS_DIR / args.output

    # Load tasks
    tasks = load_tasks(tasks_dir)
    if not tasks:
        print(f"Error: no knowledge tasks found in {tasks_dir}", file=sys.stderr)
        sys.exit(1)
    print(f"Loaded {len(tasks)} knowledge tasks from {tasks_dir}")

    # Score each run
    results: dict[str, dict] = {}
    run_labels: list[str] = []

    for run_dir in run_dirs:
        label = run_dir.name
        run_labels.append(label)

        if not run_dir.is_dir():
            results[label] = {"error": f"Run directory not found: {run_dir}"}
            continue

        responses = load_run_responses(run_dir)
        matched = sum(1 for tid in tasks if tid in responses)
        print(f"  {label}: {matched}/{len(tasks)} tasks matched")

        results[label] = score_condition(
            responses, tasks, label, args.judge_model
        )

        r = results[label]
        if "error" in r:
            print(f"  Error scoring {label}: {r['error']}", file=sys.stderr)
        else:
            m = r["metrics"]
            js = r["judge_stats"]
            print(
                f"  {label}: match_rate={fmt(m['strategy_match_rate'])}, "
                f"exact={fmt_pct(m['exact_match_rate'])}, "
                f"judge_calls={js['total_calls']}, "
                f"cache_hits={js['cache_hits']}"
            )

    if not run_labels:
        print("No valid run directories found.", file=sys.stderr)
        sys.exit(1)

    # Wilcoxon test between first two conditions
    stat_test = None
    if len(run_labels) >= 2:
        label_a, label_b = run_labels[0], run_labels[1]
        r_a = results[label_a]
        r_b = results[label_b]
        if "error" not in r_a and "error" not in r_b:
            scores_a = {
                d["task_id"]: d["judge_score"]
                for d in r_a["details"]
            }
            scores_b = {
                d["task_id"]: d["judge_score"]
                for d in r_b["details"]
            }
            stat_test = wilcoxon_test(scores_a, scores_b)
            if "p_value" in stat_test:
                print(
                    f"  Wilcoxon: p={stat_test['p_value']}, "
                    f"diff={stat_test['mean_diff']}, "
                    f"r={stat_test['effect_r']}"
                )
            elif "note" in stat_test:
                print(f"  Wilcoxon: {stat_test['note']}")

    # Generate report
    report = generate_report(results, stat_test, run_labels)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report)
    print(f"\nResults written to {output_path}")


if __name__ == "__main__":
    main()
