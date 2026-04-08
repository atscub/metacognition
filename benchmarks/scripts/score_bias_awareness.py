#!/usr/bin/env python3
"""Score Dimension 4: Metacognitive Bias Awareness (Bias Detection in Others).

Compares baseline and KYL conditions on bias detection accuracy across
reasoning traces that may or may not contain cognitive biases.

Usage:
    python scripts/score_bias_awareness.py \
      --runs runs/v2-sonnet-baseline runs/v2-sonnet-kyl \
      --tasks tasks/v2/bias_awareness/ \
      --output results/RESULTS-bias-awareness.md

Metrics:
  - Bias detection accuracy (correctly classified biased vs. clean)
  - Bias naming accuracy (correct bias type among true positives)
  - False positive rate (clean traces flagged as biased)
  - False negative rate (biased traces flagged as clean)
  - Per-bias-type detection rate
  - Wilcoxon signed-rank test on per-task detection scores between conditions
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import yaml
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS_DIR = PROJECT_ROOT / "benchmarks"

# ---------------------------------------------------------------------------
# Bias name fuzzy matching
# ---------------------------------------------------------------------------

BIAS_ALIASES: dict[str, list[str]] = {
    "anchoring": [
        "anchoring", "anchor", "anchoring bias", "anchoring effect",
        "anchor bias",
    ],
    "confirmation": [
        "confirmation", "confirmation bias", "cherry-picking",
        "cherry picking", "selective evidence",
    ],
    "sycophancy": [
        "sycophancy", "sycophantic", "people-pleasing",
        "social desirability", "conformity", "agreement bias",
    ],
    "premature_closure": [
        "premature closure", "premature_closure",
        "jumping to conclusions", "satisficing",
        "premature diagnosis", "early closure",
    ],
    "framing": [
        "framing", "framing effect", "framing bias", "frame",
        "presentation bias",
    ],
    "authority": [
        "authority", "authority bias", "appeal to authority",
        "expert bias", "credential bias",
    ],
}

# Build a reverse lookup: lowered alias -> canonical bias name
_ALIAS_LOOKUP: dict[str, str] = {}
for canonical, aliases in BIAS_ALIASES.items():
    for alias in aliases:
        _ALIAS_LOOKUP[alias.lower()] = canonical


def match_bias_name(model_name: str, ground_truth: str) -> bool:
    """Return True if *model_name* matches *ground_truth* via fuzzy alias lookup.

    Both sides are normalized to their canonical form (if recognized) and then
    compared.  If the model's name doesn't map to any known canonical form, a
    direct substring check against the ground truth aliases is attempted.
    """
    if not model_name or not ground_truth:
        return False

    model_lower = model_name.strip().lower()
    gt_lower = ground_truth.strip().lower()

    # Resolve both to canonical forms
    canonical_model = _ALIAS_LOOKUP.get(model_lower)
    canonical_gt = _ALIAS_LOOKUP.get(gt_lower, gt_lower)

    # If canonical_gt isn't in our alias table, treat it as its own key
    if canonical_gt not in BIAS_ALIASES:
        canonical_gt = gt_lower

    # Direct canonical match
    if canonical_model is not None and canonical_model == canonical_gt:
        return True

    # Fallback: check if the model's raw name contains any alias of the GT bias
    gt_aliases = BIAS_ALIASES.get(canonical_gt, [canonical_gt])
    for alias in gt_aliases:
        if alias.lower() in model_lower:
            return True

    # Reverse fallback: check if any alias of the GT bias contains the model name
    for alias in gt_aliases:
        if model_lower in alias.lower() and len(model_lower) >= 4:
            return True

    return False


# ---------------------------------------------------------------------------
# Task loading
# ---------------------------------------------------------------------------

def load_tasks(tasks_dir: Path) -> dict[str, dict]:
    """Load all v2 bias_awareness task YAML files (single-task format).

    Returns a dict keyed by task id with fields: bias_type, has_bias.
    """
    tasks: dict[str, dict] = {}
    for yaml_path in sorted(tasks_dir.rglob("*.yaml")):
        with open(yaml_path) as f:
            task = yaml.safe_load(f)
        if task is None:
            continue
        if task.get("dimension") != "bias_awareness":
            continue
        tid = task.get("id", yaml_path.stem)
        tasks[tid] = {
            "bias_type": task.get("bias_type", "unknown"),
            "has_bias": bool(task.get("has_bias", False)),
        }
    return tasks


# ---------------------------------------------------------------------------
# Response parsing
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
    # Find the first { ... } block (handles nested braces)
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

    Returns dict keyed by task id with fields: parsed (dict|None), raw (str),
    parse_ok (bool).
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

        # Determine task id: prefer explicit task_id, then qid, then filename stem
        tid = data.get("task_id", data.get("qid", json_path.stem))

        responses[tid] = {
            "parsed": parsed,
            "raw": result_text if isinstance(result_text, str) else str(result_text),
            "parse_ok": parsed is not None,
        }

    return responses


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def interpret_has_bias(parsed: dict | None) -> bool | None:
    """Extract the model's has_bias judgment from parsed JSON.

    Returns True/False if determinable, None if unparseable.
    """
    if parsed is None:
        return None
    val = parsed.get("has_bias")
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "yes", "1")
    return bool(val)


def score_condition(
    responses: dict[str, dict],
    tasks: dict[str, dict],
) -> dict:
    """Score a single condition (baseline or KYL).

    Returns a dict with all metrics and per-task details.
    """
    details: list[dict] = []
    parse_failures = 0
    total = 0

    for tid, task_info in tasks.items():
        if tid not in responses:
            continue
        total += 1
        resp = responses[tid]
        parsed = resp["parsed"]

        if not resp["parse_ok"]:
            parse_failures += 1

        model_has_bias = interpret_has_bias(parsed)
        model_bias_name = parsed.get("bias_name", "") if parsed else ""
        model_explanation = parsed.get("explanation", "") if parsed else ""

        gt_has_bias = task_info["has_bias"]
        gt_bias_type = task_info["bias_type"]

        # Detection correct: model's has_bias matches ground truth
        detection_correct = (
            model_has_bias == gt_has_bias if model_has_bias is not None else None
        )

        # Naming correct: only scored for true positives (GT biased, model detected)
        naming_correct = None
        if gt_has_bias and model_has_bias is True and model_bias_name:
            naming_correct = match_bias_name(model_bias_name, gt_bias_type)

        # Detection score for statistical testing: 1 if correct, 0 if wrong, None if unparseable
        detection_score = None
        if detection_correct is not None:
            detection_score = 1 if detection_correct else 0

        details.append({
            "tid": tid,
            "gt_has_bias": gt_has_bias,
            "gt_bias_type": gt_bias_type,
            "model_has_bias": model_has_bias,
            "model_bias_name": model_bias_name,
            "model_explanation": model_explanation,
            "detection_correct": detection_correct,
            "naming_correct": naming_correct,
            "detection_score": detection_score,
            "parse_ok": resp["parse_ok"],
        })

    if total == 0:
        return {"error": "No matching tasks found between run and tasks"}

    # --- Compute metrics ---
    scorable = [d for d in details if d["detection_correct"] is not None]

    # 1. Bias detection accuracy
    detection_accuracy = (
        sum(1 for d in scorable if d["detection_correct"]) / len(scorable)
        if scorable else float("nan")
    )

    # 2. Bias naming accuracy (among true positives)
    true_positives = [
        d for d in details
        if d["gt_has_bias"] and d["model_has_bias"] is True
    ]
    naming_scorable = [d for d in true_positives if d["naming_correct"] is not None]
    naming_accuracy = (
        sum(1 for d in naming_scorable if d["naming_correct"]) / len(naming_scorable)
        if naming_scorable else float("nan")
    )

    # 3. False positive rate: % of clean traces flagged as biased
    clean_traces = [d for d in details if not d["gt_has_bias"] and d["model_has_bias"] is not None]
    false_positive_rate = (
        sum(1 for d in clean_traces if d["model_has_bias"]) / len(clean_traces)
        if clean_traces else float("nan")
    )

    # 4. False negative rate: % of biased traces flagged as clean
    biased_traces = [d for d in details if d["gt_has_bias"] and d["model_has_bias"] is not None]
    false_negative_rate = (
        sum(1 for d in biased_traces if not d["model_has_bias"]) / len(biased_traces)
        if biased_traces else float("nan")
    )

    # 5. Per-bias-type detection rate
    bias_types = sorted(set(d["gt_bias_type"] for d in details if d["gt_has_bias"]))
    per_bias_type: dict[str, dict] = {}
    for bt in bias_types:
        bt_items = [
            d for d in details
            if d["gt_bias_type"] == bt and d["gt_has_bias"] and d["model_has_bias"] is not None
        ]
        if not bt_items:
            per_bias_type[bt] = {"n": 0, "detected": 0, "detection_rate": float("nan"),
                                 "named_correctly": 0, "naming_rate": float("nan")}
            continue
        detected = sum(1 for d in bt_items if d["model_has_bias"])
        named = sum(1 for d in bt_items if d["model_has_bias"] and d["naming_correct"])
        per_bias_type[bt] = {
            "n": len(bt_items),
            "detected": detected,
            "detection_rate": detected / len(bt_items),
            "named_correctly": named,
            "naming_rate": named / detected if detected > 0 else float("nan"),
        }

    # 6. Confusion matrix: predicted bias type vs actual
    # Rows = actual bias type (+ "clean"), Columns = predicted bias type (+ "none"/"other")
    all_gt_types = sorted(set(d["gt_bias_type"] for d in details))
    predicted_types = set()
    for d in details:
        if d["model_has_bias"] and d["model_bias_name"]:
            # Resolve to canonical name
            canon = _ALIAS_LOOKUP.get(d["model_bias_name"].strip().lower())
            predicted_types.add(canon if canon else "other")
        elif d["model_has_bias"] is False or d["model_has_bias"] is None:
            predicted_types.add("none")
    all_pred_types = sorted(predicted_types - {"none", "other"}) + ["other", "none"]

    confusion: dict[str, dict[str, int]] = {}
    for gt in all_gt_types:
        confusion[gt] = {pt: 0 for pt in all_pred_types}
    for d in details:
        gt = d["gt_bias_type"]
        if gt not in confusion:
            confusion[gt] = {pt: 0 for pt in all_pred_types}
        if d["model_has_bias"] is True and d["model_bias_name"]:
            canon = _ALIAS_LOOKUP.get(d["model_bias_name"].strip().lower())
            pred = canon if canon else "other"
        elif d["model_has_bias"] is False:
            pred = "none"
        else:
            pred = "none"  # parse failures treated as "none"
        if pred not in confusion[gt]:
            confusion[gt][pred] = 0
        confusion[gt][pred] += 1

    return {
        "metrics": {
            "detection_accuracy": detection_accuracy,
            "naming_accuracy": naming_accuracy,
            "false_positive_rate": false_positive_rate,
            "false_negative_rate": false_negative_rate,
        },
        "per_bias_type": per_bias_type,
        "confusion_matrix": confusion,
        "confusion_pred_types": all_pred_types,
        "details": details,
        "parse_failure_rate": parse_failures / total if total > 0 else 0.0,
        "total_tasks": total,
    }


# ---------------------------------------------------------------------------
# Statistical tests
# ---------------------------------------------------------------------------

def wilcoxon_detection_test(
    details_a: list[dict],
    details_b: list[dict],
) -> dict:
    """Wilcoxon signed-rank test on per-task detection scores between conditions.

    Pairs tasks by tid.  Returns test results dict.
    """
    map_a = {d["tid"]: d["detection_score"] for d in details_a if d["detection_score"] is not None}
    map_b = {d["tid"]: d["detection_score"] for d in details_b if d["detection_score"] is not None}
    common = sorted(set(map_a) & set(map_b))

    if len(common) < 5:
        return {
            "test": "wilcoxon_signed_rank",
            "n_pairs": len(common),
            "note": "Insufficient paired data (need >= 5 pairs)",
        }

    vals_a = np.array([map_a[t] for t in common])
    vals_b = np.array([map_b[t] for t in common])

    diffs = vals_a - vals_b
    # Wilcoxon requires non-zero differences
    nonzero = np.count_nonzero(diffs)
    if nonzero == 0:
        return {
            "test": "wilcoxon_signed_rank",
            "n_pairs": len(common),
            "n_nonzero_diffs": 0,
            "note": "All paired differences are zero; conditions identical on matched tasks",
        }

    try:
        stat, p_value = stats.wilcoxon(vals_a, vals_b)
    except ValueError as e:
        return {
            "test": "wilcoxon_signed_rank",
            "n_pairs": len(common),
            "error": str(e),
        }

    # Effect size: r = Z / sqrt(N)
    # Approximate Z from the normal approximation
    n = nonzero
    mean_T = n * (n + 1) / 4
    std_T = np.sqrt(n * (n + 1) * (2 * n + 1) / 24)
    z_approx = (stat - mean_T) / std_T if std_T > 0 else 0.0
    r_effect = abs(z_approx) / np.sqrt(len(common))

    return {
        "test": "wilcoxon_signed_rank",
        "n_pairs": len(common),
        "n_nonzero_diffs": int(nonzero),
        "statistic": round(float(stat), 4),
        "p_value": round(float(p_value), 4),
        "effect_size_r": round(float(r_effect), 4),
        "mean_score_a": round(float(vals_a.mean()), 4),
        "mean_score_b": round(float(vals_b.mean()), 4),
    }


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def fmt(val: float, decimals: int = 3) -> str:
    """Format a float for display, handling inf/nan."""
    if val != val:  # nan
        return "N/A"
    if val == float("inf"):
        return "inf"
    return f"{val:.{decimals}f}"


def fmt_pct(val: float) -> str:
    """Format a float as percentage."""
    if val != val:
        return "N/A"
    return f"{val * 100:.1f}%"


def generate_report(
    results: dict[str, dict],
    wilcoxon: dict | None,
    run_labels: list[str],
) -> str:
    """Generate a markdown report from scored results."""
    lines: list[str] = []
    lines.append("# Dimension 4: Bias Awareness (Bias Detection in Others)")
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

    metric_labels = {
        "detection_accuracy": "Bias detection accuracy",
        "naming_accuracy": "Bias naming accuracy (of true positives)",
        "false_positive_rate": "False positive rate (clean flagged as biased)",
        "false_negative_rate": "False negative rate (biased flagged as clean)",
    }

    for key, label in metric_labels.items():
        row = f"| {label} |"
        for run_label in run_labels:
            r = results[run_label]
            if "error" in r:
                row += " ERROR |"
            else:
                row += f" {fmt_pct(r['metrics'][key])} |"
        lines.append(row)

    # Parse failure rate
    row = "| Parse failure rate |"
    for run_label in run_labels:
        r = results[run_label]
        row += f" {fmt_pct(r.get('parse_failure_rate', 0.0))} |"
    lines.append(row)

    # Total tasks
    row = "| Total tasks |"
    for run_label in run_labels:
        r = results[run_label]
        row += f" {r.get('total_tasks', 0)} |"
    lines.append(row)

    lines.append("")

    # --- Per-bias-type breakdown ---
    lines.append("## Per-Bias-Type Detection Rate")
    lines.append("")

    # Collect all bias types across conditions
    all_bias_types: set[str] = set()
    for run_label in run_labels:
        r = results[run_label]
        if "per_bias_type" in r:
            all_bias_types.update(r["per_bias_type"].keys())

    if all_bias_types:
        header = "| Bias Type | N |"
        sep = "|---|---|"
        for label in run_labels:
            header += f" Detection ({label}) | Naming ({label}) |"
            sep += "---|---|"
        lines.append(header)
        lines.append(sep)

        for bt in sorted(all_bias_types):
            # Get N from first condition that has it
            n = 0
            for run_label in run_labels:
                r = results[run_label]
                if bt in r.get("per_bias_type", {}):
                    n = r["per_bias_type"][bt]["n"]
                    break

            row = f"| {bt} | {n} |"
            for run_label in run_labels:
                r = results[run_label]
                pbt = r.get("per_bias_type", {}).get(bt)
                if pbt:
                    row += f" {fmt_pct(pbt['detection_rate'])} | {fmt_pct(pbt['naming_rate'])} |"
                else:
                    row += " -- | -- |"
            lines.append(row)

        lines.append("")

    # --- Confusion matrix ---
    lines.append("## Confusion Matrix (Actual vs Predicted Bias Type)")
    lines.append("")

    for run_label in run_labels:
        r = results[run_label]
        if "confusion_matrix" not in r:
            continue
        cm = r["confusion_matrix"]
        pred_types = r.get("confusion_pred_types", [])
        if not cm or not pred_types:
            continue

        lines.append(f"### {run_label}")
        lines.append("")

        # Header
        header = "| Actual \\ Predicted |"
        sep = "|---|"
        for pt in pred_types:
            header += f" {pt} |"
            sep += "---|"
        lines.append(header)
        lines.append(sep)

        for gt in sorted(cm.keys()):
            row = f"| {gt} |"
            for pt in pred_types:
                count = cm[gt].get(pt, 0)
                row += f" {count} |"
            lines.append(row)

        lines.append("")

    # --- Statistical test ---
    lines.append("## Statistical Comparison (Wilcoxon Signed-Rank Test)")
    lines.append("")

    if wilcoxon is None:
        lines.append("Wilcoxon test requires exactly two conditions. Skipped.")
    elif "error" in wilcoxon:
        lines.append(f"Error: {wilcoxon['error']}")
    elif "note" in wilcoxon:
        lines.append(f"_{wilcoxon['note']}_")
        lines.append(f"- N pairs: {wilcoxon['n_pairs']}")
    else:
        p = wilcoxon.get("p_value", 1.0)
        sig = ""
        if isinstance(p, (int, float)):
            if p < 0.01:
                sig = " **"
            elif p < 0.05:
                sig = " *"

        lines.append(f"- **N pairs**: {wilcoxon['n_pairs']}")
        lines.append(f"- **Non-zero differences**: {wilcoxon.get('n_nonzero_diffs', 'N/A')}")
        lines.append(f"- **Test statistic**: {wilcoxon.get('statistic', 'N/A')}")
        lines.append(f"- **p-value**: {p}{sig}")
        lines.append(f"- **Effect size (r)**: {wilcoxon.get('effect_size_r', 'N/A')}")
        lines.append(f"- **Mean detection score ({run_labels[0]})**: {wilcoxon.get('mean_score_a', 'N/A')}")
        lines.append(f"- **Mean detection score ({run_labels[1]})**: {wilcoxon.get('mean_score_b', 'N/A')}")

    lines.append("")
    lines.append("\\* p < 0.05, \\*\\* p < 0.01")
    lines.append("")

    # --- Parse failure warning ---
    for run_label in run_labels:
        pfr = results[run_label].get("parse_failure_rate", 0.0)
        if pfr > 0.10:
            lines.append(
                f"> **WARNING**: Parse failure rate for {run_label} is "
                f"{fmt_pct(pfr)} (> 10%). Results may be unreliable."
            )
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score Dimension 4: Bias Awareness (Bias Detection in Others)."
    )
    parser.add_argument(
        "--runs",
        nargs="+",
        type=Path,
        required=True,
        help="One or more run directories (e.g. runs/v2-sonnet-baseline runs/v2-sonnet-kyl)",
    )
    parser.add_argument(
        "--tasks",
        type=Path,
        required=True,
        help="Directory containing v2 bias_awareness task YAML files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=BENCHMARKS_DIR / "results" / "RESULTS-bias-awareness.md",
        help="Output path for markdown results",
    )
    args = parser.parse_args()

    # Resolve paths relative to BENCHMARKS_DIR if not absolute
    run_dirs = []
    for r in args.runs:
        p = r if r.is_absolute() else BENCHMARKS_DIR / r
        if not p.is_dir():
            print(f"Warning: run directory not found: {p}", file=sys.stderr)
        run_dirs.append(p)

    tasks_dir = args.tasks if args.tasks.is_absolute() else BENCHMARKS_DIR / args.tasks
    if not tasks_dir.is_dir():
        print(f"Error: tasks directory not found: {tasks_dir}", file=sys.stderr)
        sys.exit(1)

    output_path = args.output if args.output.is_absolute() else BENCHMARKS_DIR / args.output

    # Load tasks
    tasks = load_tasks(tasks_dir)
    if not tasks:
        print(f"Error: no bias_awareness tasks found in {tasks_dir}", file=sys.stderr)
        sys.exit(1)

    n_biased = sum(1 for t in tasks.values() if t["has_bias"])
    n_clean = sum(1 for t in tasks.values() if not t["has_bias"])
    print(f"Loaded {len(tasks)} tasks from {tasks_dir} ({n_biased} biased, {n_clean} clean)")

    # Score each run
    all_results: dict[str, dict] = {}
    run_labels: list[str] = []
    for run_dir in run_dirs:
        label = run_dir.name
        run_labels.append(label)
        responses = load_run_responses(run_dir)
        matched = sum(1 for tid in tasks if tid in responses)
        print(f"  {label}: {matched}/{len(tasks)} tasks matched")
        all_results[label] = score_condition(responses, tasks)

        r = all_results[label]
        if "error" in r:
            print(f"  Error scoring {label}: {r['error']}", file=sys.stderr)
        else:
            m = r["metrics"]
            print(f"    Detection accuracy: {fmt_pct(m['detection_accuracy'])}")
            print(f"    Naming accuracy:    {fmt_pct(m['naming_accuracy'])}")
            print(f"    FP rate:            {fmt_pct(m['false_positive_rate'])}")
            print(f"    FN rate:            {fmt_pct(m['false_negative_rate'])}")

    # Wilcoxon signed-rank test (only if exactly 2 runs)
    wilcoxon = None
    if len(run_labels) == 2:
        r0 = all_results[run_labels[0]]
        r1 = all_results[run_labels[1]]
        if "details" in r0 and "details" in r1:
            wilcoxon = wilcoxon_detection_test(r0["details"], r1["details"])
            if "p_value" in wilcoxon:
                print(f"  Wilcoxon p={wilcoxon['p_value']}, "
                      f"r={wilcoxon.get('effect_size_r', 'N/A')}")

    # Generate report
    report = generate_report(all_results, wilcoxon, run_labels)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report)
    print(f"\nResults written to {output_path}")


if __name__ == "__main__":
    main()
