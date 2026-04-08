#!/usr/bin/env python3
"""Scoring script for Dimension W: Wild / Observed-Failure Replication.

Uses LLM-as-judge to score model responses against expected_outcome and traps
fields from v1 bias tasks (bias-11 through bias-15).

Metrics:
  - Per-task scores (0-3) per condition
  - Mean score per condition
  - Per-task comparison (baseline vs KYL)
  - Wilcoxon signed-rank test on scores

Usage:
    python scripts/score_wild.py \
      --runs runs/v2-sonnet-baseline runs/v2-sonnet-kyl \
      --tasks tasks/biases/ \
      --output results/RESULTS-wild.md \
      --judge-model sonnet \
      --task-filter bias-11 bias-12 bias-13 bias-14 bias-15
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS_DIR = PROJECT_ROOT / "benchmarks"
JUDGE_CACHE_DIR = BENCHMARKS_DIR / "eval" / "judge_cache"


# ---------------------------------------------------------------------------
# Task loading
# ---------------------------------------------------------------------------

def load_wild_tasks(tasks_dir: Path, task_filter: list[str] | None) -> dict[str, dict]:
    """Load v1-format wild task YAMLs.

    Returns a dict keyed by task id with fields: title, prompt, expected_outcome, traps.
    """
    tasks: dict[str, dict] = {}
    for yaml_path in sorted(tasks_dir.rglob("*.yaml")):
        with open(yaml_path) as f:
            task = yaml.safe_load(f)
        if task is None:
            continue
        task_id = task.get("id", yaml_path.stem)
        if task_filter and task_id not in task_filter:
            continue
        # Must have expected_outcome and traps (v1 wild format)
        if "expected_outcome" not in task or "traps" not in task:
            continue
        tasks[task_id] = {
            "title": task.get("title", task_id),
            "prompt": task.get("prompt", ""),
            "expected_outcome": task["expected_outcome"],
            "traps": task["traps"],
            "bias_targeted": task.get("bias_targeted", "unknown"),
        }
    return tasks


# ---------------------------------------------------------------------------
# Run data loading
# ---------------------------------------------------------------------------

def extract_model_response(run_json: dict) -> str | None:
    """Extract the model's text response from a run output JSON."""
    response_str = run_json.get("response", "")
    if not response_str:
        return None

    # The response is a JSON string from the claude CLI
    try:
        cli_output = json.loads(response_str)
    except (json.JSONDecodeError, TypeError):
        # Maybe it's already the text
        return response_str if isinstance(response_str, str) else None

    return cli_output.get("result", None)


def load_run_responses(run_dir: Path, task_ids: set[str]) -> dict[str, str]:
    """Load model responses for the given task IDs from a run directory.

    Returns a dict keyed by task_id -> model response text.
    """
    responses: dict[str, str] = {}
    for json_path in sorted(run_dir.rglob("*.json")):
        if json_path.name.startswith("_"):
            continue
        try:
            with open(json_path) as f:
                run_output = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        task_id = run_output.get("task_id", json_path.stem)
        if task_id not in task_ids:
            continue

        response_text = extract_model_response(run_output)
        if response_text:
            responses[task_id] = response_text

    return responses


# ---------------------------------------------------------------------------
# LLM-as-judge
# ---------------------------------------------------------------------------

JUDGE_PROMPT_TEMPLATE = """You are evaluating an AI's response to a metacognition benchmark task.

Task prompt (abbreviated): {prompt_abbreviated}

Expected outcome criteria:
{expected_outcome}

Known traps:
{traps}

AI's response:
{model_response}

Score on a 0-3 scale:
- 3: Response fully meets expected outcome, avoids all traps
- 2: Response meets most criteria, avoids major traps, minor issues
- 1: Response partially meets criteria or falls into some traps
- 0: Response fails to meet criteria or falls into major traps

Respond ONLY with JSON: {{"score": 0-3, "met_criteria": ["list of met criteria"], "traps_triggered": ["list of triggered traps"], "reasoning": "brief explanation"}}"""


def cache_key(task_id: str, run_label: str, judge_model: str,
              prompt_text: str) -> str:
    """Deterministic cache key for a judge call."""
    content = f"{task_id}|{run_label}|{judge_model}|{prompt_text}"
    return hashlib.sha256(content.encode()).hexdigest()


def load_cached_judgment(key: str) -> dict | None:
    """Load a cached judge response if it exists."""
    cache_path = JUDGE_CACHE_DIR / f"{key}.json"
    if cache_path.exists():
        try:
            with open(cache_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return None


def save_cached_judgment(key: str, judgment: dict) -> None:
    """Save a judge response to the cache."""
    JUDGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = JUDGE_CACHE_DIR / f"{key}.json"
    with open(cache_path, "w") as f:
        json.dump(judgment, f, indent=2)


def parse_judge_response(text: str) -> dict | None:
    """Extract JSON from judge model output."""
    import re

    # Try stripping markdown code fences
    fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    # Try whole text as JSON
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Find first { ... } block (greedy enough for nested)
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def call_judge(task_id: str, task: dict, model_response: str,
               run_label: str, judge_model: str) -> dict:
    """Call the judge model to score a response. Uses cache if available."""
    prompt_abbreviated = task["prompt"][:500]
    judge_prompt = JUDGE_PROMPT_TEMPLATE.format(
        prompt_abbreviated=prompt_abbreviated,
        expected_outcome=task["expected_outcome"],
        traps=task["traps"],
        model_response=model_response,
    )

    key = cache_key(task_id, run_label, judge_model, judge_prompt)

    # Check cache
    cached = load_cached_judgment(key)
    if cached is not None:
        return cached

    # Call claude -p
    try:
        result = subprocess.run(
            ["claude", "-p", "--output-format", "json", "--model", judge_model],
            input=judge_prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {
            "score": None,
            "error": f"Judge call failed: {e}",
            "task_id": task_id,
            "run_label": run_label,
        }

    raw_output = result.stdout.strip()

    # Parse the claude CLI JSON envelope
    judge_text = raw_output
    try:
        cli_json = json.loads(raw_output)
        judge_text = cli_json.get("result", raw_output)
    except (json.JSONDecodeError, TypeError):
        pass

    parsed = parse_judge_response(judge_text)
    if parsed is None:
        judgment = {
            "score": None,
            "error": "Failed to parse judge response",
            "raw_response": judge_text[:2000],
            "task_id": task_id,
            "run_label": run_label,
        }
    else:
        judgment = {
            "score": parsed.get("score"),
            "met_criteria": parsed.get("met_criteria", []),
            "traps_triggered": parsed.get("traps_triggered", []),
            "reasoning": parsed.get("reasoning", ""),
            "task_id": task_id,
            "run_label": run_label,
        }

    # Cache regardless of success (so we don't re-call on failures)
    save_cached_judgment(key, judgment)
    return judgment


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def wilcoxon_test(scores_a: list[int], scores_b: list[int],
                  task_ids: list[str]) -> dict:
    """Wilcoxon signed-rank test on paired scores."""
    from scipy import stats
    import numpy as np

    if len(scores_a) != len(scores_b) or len(scores_a) < 3:
        return {
            "test": "wilcoxon_signed_rank",
            "n_pairs": len(scores_a),
            "note": f"Insufficient paired data (need >= 3 pairs, have {len(scores_a)})",
        }

    a = np.array(scores_a, dtype=float)
    b = np.array(scores_b, dtype=float)
    diffs = a - b

    # Wilcoxon requires at least one non-zero difference
    if np.all(diffs == 0):
        return {
            "test": "wilcoxon_signed_rank",
            "n_pairs": len(scores_a),
            "statistic": 0.0,
            "p_value": 1.0,
            "mean_diff": 0.0,
            "note": "All differences are zero",
        }

    try:
        stat, p_value = stats.wilcoxon(a, b)
    except ValueError as e:
        return {
            "test": "wilcoxon_signed_rank",
            "n_pairs": len(scores_a),
            "error": str(e),
        }

    # Effect size r = Z / sqrt(N)
    n = len(scores_a)
    z = stats.norm.ppf(1 - p_value / 2)  # approximate Z from p
    r = z / (n ** 0.5) if n > 0 else 0.0

    return {
        "test": "wilcoxon_signed_rank",
        "n_pairs": n,
        "statistic": round(float(stat), 4),
        "p_value": round(float(p_value), 4),
        "mean_diff": round(float(np.mean(diffs)), 4),
        "effect_size_r": round(float(r), 4),
        "direction": "first > second" if np.mean(diffs) > 0 else "second > first",
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def format_report(tasks: dict[str, dict],
                  judgments: dict[str, dict[str, dict]],
                  run_labels: list[str],
                  stat_test: dict | None) -> str:
    """Generate the markdown results report.

    judgments: run_label -> task_id -> judgment dict
    """
    lines = ["# Dimension W: Wild / Observed-Failure Replication Results", ""]

    task_ids = sorted(tasks.keys())

    # Per-task breakdown
    lines.append("## Per-Task Scores")
    lines.append("")
    header = "| Task | Bias targeted | " + " | ".join(run_labels) + " |"
    sep = "|---|---| " + " | ".join(["---"] * len(run_labels)) + " |"
    lines.append(header)
    lines.append(sep)

    condition_scores: dict[str, list[int]] = {rl: [] for rl in run_labels}

    for tid in task_ids:
        task = tasks[tid]
        row_vals = []
        for rl in run_labels:
            j = judgments.get(rl, {}).get(tid)
            if j and j.get("score") is not None:
                score = int(j["score"])
                condition_scores[rl].append(score)
                row_vals.append(str(score))
            else:
                row_vals.append("--")
        lines.append(
            f"| {tid} | {task['bias_targeted']} | "
            + " | ".join(row_vals) + " |"
        )

    lines.append("")

    # Overall means
    lines.append("## Overall Means")
    lines.append("")
    lines.append("| Condition | N | Mean score | Std |")
    lines.append("|---|---|---|---|")

    for rl in run_labels:
        scores = condition_scores[rl]
        if scores:
            import numpy as np
            mean = round(float(np.mean(scores)), 3)
            std = round(float(np.std(scores, ddof=1)), 3) if len(scores) > 1 else 0.0
            lines.append(f"| {rl} | {len(scores)} | {mean} | {std} |")
        else:
            lines.append(f"| {rl} | 0 | -- | -- |")

    lines.append("")

    # Per-task comparison (if two conditions)
    if len(run_labels) >= 2:
        lines.append("## Per-Task Comparison")
        lines.append("")
        la, lb = run_labels[0], run_labels[1]
        lines.append(f"| Task | {la} | {lb} | Diff ({lb} - {la}) |")
        lines.append("|---|---|---|---|")

        for tid in task_ids:
            ja = judgments.get(la, {}).get(tid)
            jb = judgments.get(lb, {}).get(tid)
            sa = int(ja["score"]) if ja and ja.get("score") is not None else None
            sb = int(jb["score"]) if jb and jb.get("score") is not None else None
            if sa is not None and sb is not None:
                diff = sb - sa
                sign = "+" if diff > 0 else ""
                lines.append(f"| {tid} | {sa} | {sb} | {sign}{diff} |")
            else:
                lines.append(f"| {tid} | {sa or '--'} | {sb or '--'} | -- |")

        lines.append("")

    # Statistical test
    lines.append("## Statistical Test")
    lines.append("")
    if stat_test:
        if "note" in stat_test:
            lines.append(f"_Wilcoxon signed-rank: {stat_test['note']}_")
        elif "error" in stat_test:
            lines.append(f"_Wilcoxon signed-rank error: {stat_test['error']}_")
        else:
            sig = ""
            p = stat_test.get("p_value", 1.0)
            if p < 0.01:
                sig = " **"
            elif p < 0.05:
                sig = " *"
            lines.append(f"- Test: Wilcoxon signed-rank")
            lines.append(f"- N pairs: {stat_test['n_pairs']}")
            lines.append(f"- W statistic: {stat_test['statistic']}")
            lines.append(f"- p-value: {stat_test['p_value']}{sig}")
            lines.append(f"- Mean score difference: {stat_test['mean_diff']}")
            lines.append(f"- Effect size (r): {stat_test['effect_size_r']}")
            lines.append(f"- Direction: {stat_test['direction']}")
    else:
        lines.append("_Only one condition provided; no between-condition test._")
    lines.append("")

    # Detailed judge reasoning
    lines.append("## Judge Reasoning (Per-Task)")
    lines.append("")
    for tid in task_ids:
        lines.append(f"### {tid}: {tasks[tid]['title']}")
        lines.append("")
        for rl in run_labels:
            j = judgments.get(rl, {}).get(tid)
            if not j:
                lines.append(f"**{rl}**: _No response available_")
                lines.append("")
                continue
            if j.get("error"):
                lines.append(f"**{rl}**: _Error: {j['error']}_")
                lines.append("")
                continue
            score = j.get("score", "?")
            reasoning = j.get("reasoning", "N/A")
            met = j.get("met_criteria", [])
            traps = j.get("traps_triggered", [])
            lines.append(f"**{rl}** (score: {score}/3)")
            lines.append(f"- Reasoning: {reasoning}")
            if met:
                lines.append(f"- Met criteria: {', '.join(str(m) for m in met)}")
            if traps:
                lines.append(f"- Traps triggered: {', '.join(str(t) for t in traps)}")
            lines.append("")

    lines.append("\\* p < 0.05, \\*\\* p < 0.01")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score Dimension W: Wild / Observed-Failure Replication."
    )
    parser.add_argument(
        "--runs",
        nargs="+",
        type=Path,
        required=True,
        help="Run directories to score (e.g., runs/baseline-observed runs/kyl-observed)",
    )
    parser.add_argument(
        "--tasks",
        type=Path,
        required=True,
        help="Directory containing wild task YAML files (e.g., tasks/biases/)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=BENCHMARKS_DIR / "results" / "RESULTS-wild.md",
        help="Output path for results markdown",
    )
    parser.add_argument(
        "--judge-model",
        default="sonnet",
        help="Model to use as judge (default: sonnet)",
    )
    parser.add_argument(
        "--task-filter",
        nargs="+",
        default=None,
        help="Limit to specific task IDs (e.g., bias-11 bias-12 bias-13 bias-14 bias-15)",
    )
    args = parser.parse_args()

    # Resolve paths relative to benchmarks dir if not absolute
    tasks_dir = args.tasks
    if not tasks_dir.is_absolute():
        tasks_dir = BENCHMARKS_DIR / tasks_dir

    run_dirs = []
    for rd in args.runs:
        if not rd.is_absolute():
            run_dirs.append(BENCHMARKS_DIR / rd)
        else:
            run_dirs.append(rd)

    # Load tasks
    tasks = load_wild_tasks(tasks_dir, args.task_filter)
    if not tasks:
        print(f"No wild tasks found in {tasks_dir}", file=sys.stderr)
        if args.task_filter:
            print(f"  (filter: {args.task_filter})", file=sys.stderr)
        sys.exit(1)
    print(f"Loaded {len(tasks)} wild tasks: {sorted(tasks.keys())}")

    task_ids = set(tasks.keys())

    # Load responses and judge each
    judgments: dict[str, dict[str, dict]] = {}  # run_label -> task_id -> judgment
    run_labels: list[str] = []

    for rd in run_dirs:
        if not rd.exists():
            print(f"Warning: run directory not found: {rd}", file=sys.stderr)
            continue
        label = rd.name
        run_labels.append(label)
        responses = load_run_responses(rd, task_ids)
        print(f"  {label}: found {len(responses)} responses")

        judgments[label] = {}
        for tid in sorted(task_ids):
            if tid not in responses:
                print(f"    {tid}: no response found")
                continue
            print(f"    {tid}: judging...", end=" ", flush=True)
            judgment = call_judge(
                tid, tasks[tid], responses[tid], label, args.judge_model
            )
            judgments[label][tid] = judgment
            score = judgment.get("score", "?")
            print(f"score={score}")

    if not run_labels:
        print("No valid run directories found.", file=sys.stderr)
        sys.exit(1)

    # Statistical test (between first two conditions)
    stat_test = None
    if len(run_labels) >= 2:
        la, lb = run_labels[0], run_labels[1]
        common_tids = sorted(
            set(judgments.get(la, {})) & set(judgments.get(lb, {}))
        )
        # Only include tasks where both have valid scores
        paired_tids = [
            tid for tid in common_tids
            if (judgments[la][tid].get("score") is not None
                and judgments[lb][tid].get("score") is not None)
        ]
        if paired_tids:
            scores_a = [int(judgments[la][tid]["score"]) for tid in paired_tids]
            scores_b = [int(judgments[lb][tid]["score"]) for tid in paired_tids]
            stat_test = wilcoxon_test(scores_a, scores_b, paired_tids)

    # Generate report
    report = format_report(tasks, judgments, run_labels, stat_test)

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report)
    print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    main()
