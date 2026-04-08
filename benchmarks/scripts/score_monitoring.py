#!/usr/bin/env python3
"""Scoring script for Dimension 1: Metacognitive Monitoring (Failure Prediction).

Computes calibration metrics from (confidence, correctness) pairs extracted
from v2 monitoring benchmark runs.

Metrics:
  - Expected Calibration Error (ECE)
  - AUROC (confidence as classifier for correctness)
  - Brier Score
  - Selective prediction accuracy at 80% coverage
  - Per-difficulty stratification (if difficulty labels exist)
  - Statistical comparison between conditions (paired t-test, bootstrap AUROC CI)
"""

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import yaml
from scipy import stats
from sklearn.metrics import roc_auc_score

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS_DIR = PROJECT_ROOT / "benchmarks"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_task_ground_truth(tasks_dir: Path) -> dict:
    """Load ground truth from v2 batch YAML files.

    Returns a dict keyed by qid -> {answer, difficulty, category, source, batch_id}.
    """
    ground_truth = {}
    for yaml_path in sorted(tasks_dir.rglob("*.yaml")):
        with open(yaml_path) as f:
            task = yaml.safe_load(f)
        if not task or task.get("dimension") != "monitoring":
            continue
        batch_id = task.get("id", yaml_path.stem)
        source = task.get("source", "unknown")
        for q in task.get("questions", []):
            qid = q["qid"]
            ground_truth[qid] = {
                "answer": q["answer"],
                "difficulty": q.get("difficulty", "unknown"),
                "category": q.get("category", "unknown"),
                "source": source,
                "batch_id": batch_id,
            }
    return ground_truth


def parse_model_response(raw_response: str) -> dict | None:
    """Extract the parsed JSON from a claude CLI JSON response.

    The run output .json has a `response` field containing the claude CLI
    JSON envelope, which has a `result` field containing the model's text.
    The model's text should be JSON with `answer` and `confidence` fields.
    """
    # The raw_response is the full claude CLI JSON string
    try:
        cli_output = json.loads(raw_response)
    except (json.JSONDecodeError, TypeError):
        return None

    result_text = cli_output.get("result", "")
    if not result_text:
        return None

    return extract_json_from_text(result_text)


def extract_json_from_text(text: str) -> dict | None:
    """Extract a JSON object from text that may contain markdown fences or prose."""
    # Try stripping markdown code fences first
    fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    # Try the whole text as JSON
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Find the first { ... } block
    brace_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def check_correctness(model_answer: str, ground_truth_answer: str) -> bool:
    """Case-insensitive substring match: ground truth in model answer."""
    if not model_answer or not ground_truth_answer:
        return False
    return ground_truth_answer.strip().lower() in model_answer.strip().lower()


def load_run_data(run_dir: Path, ground_truth: dict) -> list[dict]:
    """Load all question-level results from a run directory.

    Returns a list of dicts with keys: qid, confidence, correctness,
    difficulty, category, source, parse_ok.
    """
    records = []
    parse_failures = 0
    total = 0

    for json_path in sorted(run_dir.rglob("*.json")):
        # Skip metadata files
        if json_path.name.startswith("_"):
            continue

        with open(json_path) as f:
            try:
                run_output = json.load(f)
            except json.JSONDecodeError:
                continue

        # v2 batch runs produce one JSON per question with a qid field.
        # Also handle the case where the run JSON has a task_id matching
        # a batch and a `results` list inside it, or a single question.

        # Check if this is a single-question output with a qid
        qid = run_output.get("qid")
        if qid and qid in ground_truth:
            total += 1
            parsed = parse_model_response(run_output.get("response", ""))
            if parsed and "confidence" in parsed and "answer" in parsed:
                gt = ground_truth[qid]
                conf = float(parsed["confidence"])
                conf = max(0.0, min(100.0, conf))
                correct = check_correctness(str(parsed["answer"]), gt["answer"])
                records.append({
                    "qid": qid,
                    "confidence": conf,
                    "correctness": 1 if correct else 0,
                    "difficulty": gt["difficulty"],
                    "category": gt["category"],
                    "source": gt["source"],
                    "parse_ok": True,
                })
            else:
                parse_failures += 1
                records.append({
                    "qid": qid,
                    "confidence": None,
                    "correctness": None,
                    "difficulty": ground_truth[qid]["difficulty"],
                    "category": ground_truth[qid]["category"],
                    "source": ground_truth[qid]["source"],
                    "parse_ok": False,
                })
            continue

        # Check if this is a batch output with a results list
        results_list = run_output.get("results", [])
        if results_list:
            for item in results_list:
                item_qid = item.get("qid")
                if not item_qid or item_qid not in ground_truth:
                    continue
                total += 1
                parsed = parse_model_response(item.get("response", ""))
                if parsed and "confidence" in parsed and "answer" in parsed:
                    gt = ground_truth[item_qid]
                    conf = float(parsed["confidence"])
                    conf = max(0.0, min(100.0, conf))
                    correct = check_correctness(str(parsed["answer"]), gt["answer"])
                    records.append({
                        "qid": item_qid,
                        "confidence": conf,
                        "correctness": 1 if correct else 0,
                        "difficulty": gt["difficulty"],
                        "category": gt["category"],
                        "source": gt["source"],
                        "parse_ok": True,
                    })
                else:
                    parse_failures += 1
                    records.append({
                        "qid": item_qid,
                        "confidence": None,
                        "correctness": None,
                        "difficulty": ground_truth[item_qid]["difficulty"],
                        "category": ground_truth[item_qid]["category"],
                        "source": ground_truth[item_qid]["source"],
                        "parse_ok": False,
                    })
            continue

        # Fallback: check if response contains a parsed field directly
        # (future-proofing for when run_task.py adds a `parsed` field)
        parsed_field = run_output.get("parsed")
        task_id = run_output.get("task_id", "")
        if parsed_field and isinstance(parsed_field, dict):
            p_qid = parsed_field.get("qid", task_id)
            if p_qid in ground_truth:
                total += 1
                if "confidence" in parsed_field and "answer" in parsed_field:
                    gt = ground_truth[p_qid]
                    conf = float(parsed_field["confidence"])
                    conf = max(0.0, min(100.0, conf))
                    correct = check_correctness(
                        str(parsed_field["answer"]), gt["answer"]
                    )
                    records.append({
                        "qid": p_qid,
                        "confidence": conf,
                        "correctness": 1 if correct else 0,
                        "difficulty": gt["difficulty"],
                        "category": gt["category"],
                        "source": gt["source"],
                        "parse_ok": True,
                    })
                else:
                    parse_failures += 1
                    records.append({
                        "qid": p_qid,
                        "confidence": None,
                        "correctness": None,
                        "difficulty": ground_truth[p_qid]["difficulty"],
                        "category": ground_truth[p_qid]["category"],
                        "source": ground_truth[p_qid]["source"],
                        "parse_ok": False,
                    })

    return records


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_ece(confidences: np.ndarray, correctness: np.ndarray,
                n_bins: int = 10) -> tuple[float, list[dict]]:
    """Expected Calibration Error with 10 equal-width bins.

    Returns (ece, bin_details) where bin_details is a list of dicts with
    bin_lower, bin_upper, mean_confidence, accuracy, count.
    """
    bin_boundaries = np.linspace(0, 100, n_bins + 1)
    bin_details = []
    total = len(confidences)

    weighted_sum = 0.0
    for i in range(n_bins):
        lo, hi = bin_boundaries[i], bin_boundaries[i + 1]
        if i == n_bins - 1:
            mask = (confidences >= lo) & (confidences <= hi)
        else:
            mask = (confidences >= lo) & (confidences < hi)

        count = mask.sum()
        if count == 0:
            bin_details.append({
                "bin_lower": lo,
                "bin_upper": hi,
                "mean_confidence": None,
                "accuracy": None,
                "count": 0,
            })
            continue

        mean_conf = confidences[mask].mean() / 100.0  # normalize to [0,1]
        acc = correctness[mask].mean()
        weighted_sum += (count / total) * abs(acc - mean_conf)

        bin_details.append({
            "bin_lower": lo,
            "bin_upper": hi,
            "mean_confidence": round(confidences[mask].mean(), 2),
            "accuracy": round(acc, 4),
            "count": int(count),
        })

    return round(weighted_sum, 4), bin_details


def compute_auroc(confidences: np.ndarray, correctness: np.ndarray) -> float | None:
    """AUROC of confidence as a classifier for correctness."""
    unique = np.unique(correctness)
    if len(unique) < 2:
        return None  # Need both classes
    return round(roc_auc_score(correctness, confidences), 4)


def compute_brier(confidences: np.ndarray, correctness: np.ndarray) -> float:
    """Mean Brier score: mean of (confidence/100 - correctness)^2."""
    probs = confidences / 100.0
    return round(float(np.mean((probs - correctness) ** 2)), 4)


def compute_selective_accuracy(confidences: np.ndarray,
                               correctness: np.ndarray,
                               coverage: float = 0.8) -> tuple[float, int]:
    """Accuracy on the top `coverage` fraction of questions by confidence.

    Returns (accuracy, n_selected).
    """
    n = len(confidences)
    n_select = max(1, int(np.ceil(n * coverage)))

    # Sort by confidence descending
    order = np.argsort(-confidences)
    selected = correctness[order[:n_select]]
    acc = float(selected.mean())
    return round(acc, 4), n_select


def per_question_brier(confidences: np.ndarray,
                       correctness: np.ndarray) -> np.ndarray:
    """Per-question Brier scores for paired statistical testing."""
    probs = confidences / 100.0
    return (probs - correctness) ** 2


# ---------------------------------------------------------------------------
# Statistical tests
# ---------------------------------------------------------------------------

def paired_brier_ttest(brier_a: np.ndarray, brier_b: np.ndarray,
                       qids_a: list[str], qids_b: list[str]) -> dict:
    """Paired t-test on per-question Brier scores between two conditions.

    Pairs questions by qid.  Returns test results dict.
    """
    map_a = dict(zip(qids_a, brier_a))
    map_b = dict(zip(qids_b, brier_b))
    common = sorted(set(map_a) & set(map_b))

    if len(common) < 5:
        return {
            "test": "paired_t_test_brier",
            "n_pairs": len(common),
            "note": "Insufficient paired data (need >= 5 pairs)",
        }

    vals_a = np.array([map_a[q] for q in common])
    vals_b = np.array([map_b[q] for q in common])

    t_stat, p_value = stats.ttest_rel(vals_a, vals_b)
    mean_diff = float(np.mean(vals_a - vals_b))

    return {
        "test": "paired_t_test_brier",
        "n_pairs": len(common),
        "t_statistic": round(float(t_stat), 4),
        "p_value": round(float(p_value), 4),
        "mean_diff": round(mean_diff, 4),
        "direction": "first lower (better)" if mean_diff < 0 else "second lower (better)",
    }


def bootstrap_auroc_ci(confidences: np.ndarray, correctness: np.ndarray,
                       n_bootstrap: int = 2000, alpha: float = 0.05,
                       rng_seed: int = 42) -> dict:
    """Bootstrap confidence interval for AUROC."""
    unique = np.unique(correctness)
    if len(unique) < 2:
        return {"note": "Cannot compute AUROC CI: only one class present"}

    rng = np.random.default_rng(rng_seed)
    n = len(confidences)
    aurocs = []

    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        c_boot = correctness[idx]
        if len(np.unique(c_boot)) < 2:
            continue
        aurocs.append(roc_auc_score(c_boot, confidences[idx]))

    if len(aurocs) < 100:
        return {"note": f"Too few valid bootstrap samples ({len(aurocs)})"}

    aurocs = np.array(aurocs)
    lo = round(float(np.percentile(aurocs, 100 * alpha / 2)), 4)
    hi = round(float(np.percentile(aurocs, 100 * (1 - alpha / 2))), 4)
    return {
        "test": "bootstrap_auroc_ci",
        "n_bootstrap": len(aurocs),
        "ci_lower": lo,
        "ci_upper": hi,
        "alpha": alpha,
        "mean": round(float(aurocs.mean()), 4),
    }


def bootstrap_auroc_comparison(conf_a: np.ndarray, corr_a: np.ndarray,
                               conf_b: np.ndarray, corr_b: np.ndarray,
                               qids_a: list[str], qids_b: list[str],
                               n_bootstrap: int = 2000,
                               rng_seed: int = 42) -> dict:
    """Bootstrap test for AUROC difference between two conditions.

    Pairs on common qids, then bootstraps the AUROC difference.
    """
    map_conf_a = dict(zip(qids_a, conf_a))
    map_corr_a = dict(zip(qids_a, corr_a))
    map_conf_b = dict(zip(qids_b, conf_b))
    map_corr_b = dict(zip(qids_b, corr_b))
    common = sorted(set(map_conf_a) & set(map_conf_b))

    if len(common) < 20:
        return {
            "test": "bootstrap_auroc_diff",
            "n_pairs": len(common),
            "note": "Insufficient paired data for bootstrap AUROC comparison",
        }

    ca = np.array([map_conf_a[q] for q in common])
    ra = np.array([map_corr_a[q] for q in common])
    cb = np.array([map_conf_b[q] for q in common])
    rb = np.array([map_corr_b[q] for q in common])

    # Check both conditions have both classes
    if len(np.unique(ra)) < 2 or len(np.unique(rb)) < 2:
        return {
            "test": "bootstrap_auroc_diff",
            "n_pairs": len(common),
            "note": "One condition has only one correctness class",
        }

    rng = np.random.default_rng(rng_seed)
    n = len(common)
    diffs = []

    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        ra_boot = ra[idx]
        rb_boot = rb[idx]
        if len(np.unique(ra_boot)) < 2 or len(np.unique(rb_boot)) < 2:
            continue
        auroc_a = roc_auc_score(ra_boot, ca[idx])
        auroc_b = roc_auc_score(rb_boot, cb[idx])
        diffs.append(auroc_a - auroc_b)

    if len(diffs) < 100:
        return {
            "test": "bootstrap_auroc_diff",
            "n_pairs": len(common),
            "note": f"Too few valid bootstrap samples ({len(diffs)})",
        }

    diffs = np.array(diffs)
    lo = round(float(np.percentile(diffs, 2.5)), 4)
    hi = round(float(np.percentile(diffs, 97.5)), 4)
    p_value = round(float(2 * min(np.mean(diffs > 0), np.mean(diffs < 0))), 4)

    return {
        "test": "bootstrap_auroc_diff",
        "n_pairs": len(common),
        "n_bootstrap": len(diffs),
        "mean_diff": round(float(diffs.mean()), 4),
        "ci_lower": lo,
        "ci_upper": hi,
        "p_value": p_value,
    }


# ---------------------------------------------------------------------------
# Condition-level computation
# ---------------------------------------------------------------------------

def compute_condition_metrics(records: list[dict]) -> dict:
    """Compute all metrics for a single condition's records.

    Only uses records where parse_ok is True.
    """
    valid = [r for r in records if r["parse_ok"]]
    total = len(records)
    n_valid = len(valid)
    n_parse_fail = total - n_valid

    if n_valid == 0:
        return {
            "n_total": total,
            "n_valid": 0,
            "n_parse_fail": n_parse_fail,
            "parse_fail_rate": 1.0 if total > 0 else 0.0,
            "error": "No valid parsed responses",
        }

    confidences = np.array([r["confidence"] for r in valid])
    correctness = np.array([r["correctness"] for r in valid])

    ece, bin_details = compute_ece(confidences, correctness)
    auroc = compute_auroc(confidences, correctness)
    brier = compute_brier(confidences, correctness)
    sel_acc, n_selected = compute_selective_accuracy(confidences, correctness)
    accuracy = round(float(correctness.mean()), 4)
    mean_conf = round(float(confidences.mean()), 2)

    # Per-difficulty breakdown
    difficulties = sorted(set(r["difficulty"] for r in valid))
    per_difficulty = {}
    if len(difficulties) > 1 or (len(difficulties) == 1 and difficulties[0] != "unknown"):
        for diff in difficulties:
            diff_records = [r for r in valid if r["difficulty"] == diff]
            if len(diff_records) < 3:
                continue
            d_conf = np.array([r["confidence"] for r in diff_records])
            d_corr = np.array([r["correctness"] for r in diff_records])
            d_ece, _ = compute_ece(d_conf, d_corr)
            d_auroc = compute_auroc(d_conf, d_corr)
            d_brier = compute_brier(d_conf, d_corr)
            per_difficulty[diff] = {
                "n": len(diff_records),
                "accuracy": round(float(d_corr.mean()), 4),
                "mean_confidence": round(float(d_conf.mean()), 2),
                "ece": d_ece,
                "auroc": d_auroc,
                "brier": d_brier,
            }

    auroc_ci = bootstrap_auroc_ci(confidences, correctness)

    return {
        "n_total": total,
        "n_valid": n_valid,
        "n_parse_fail": n_parse_fail,
        "parse_fail_rate": round(n_parse_fail / total, 4) if total > 0 else 0.0,
        "accuracy": accuracy,
        "mean_confidence": mean_conf,
        "ece": ece,
        "auroc": auroc,
        "auroc_ci": auroc_ci,
        "brier": brier,
        "selective_accuracy_80": sel_acc,
        "selective_n": n_selected,
        "calibration_bins": bin_details,
        "per_difficulty": per_difficulty,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def format_report(condition_results: dict[str, dict],
                  stat_tests: dict,
                  run_labels: list[str]) -> str:
    """Generate the markdown results report."""
    lines = ["# Dimension 1: Metacognitive Monitoring Results", ""]

    # Overall metrics table
    lines.append("## Overall Metrics")
    lines.append("")
    lines.append("| Metric | " + " | ".join(run_labels) + " |")
    lines.append("|---|" + "|".join(["---"] * len(run_labels)) + "|")

    metric_rows = [
        ("N (valid / total)", lambda m: f"{m['n_valid']} / {m['n_total']}"),
        ("Parse failure rate", lambda m: f"{m['parse_fail_rate']:.1%}"),
        ("Accuracy", lambda m: f"{m.get('accuracy', 'N/A')}"),
        ("Mean confidence", lambda m: f"{m.get('mean_confidence', 'N/A')}"),
        ("ECE (lower is better)", lambda m: f"{m.get('ece', 'N/A')}"),
        ("AUROC (higher is better)", lambda m: f"{m.get('auroc', 'N/A')}"),
        ("Brier score (lower is better)", lambda m: f"{m.get('brier', 'N/A')}"),
        ("Selective accuracy @80%", lambda m: f"{m.get('selective_accuracy_80', 'N/A')} (n={m.get('selective_n', '?')})"),
    ]

    for label, fn in metric_rows:
        vals = []
        for rl in run_labels:
            m = condition_results[rl]
            if "error" in m:
                vals.append("ERROR")
            else:
                vals.append(fn(m))
        lines.append(f"| {label} | " + " | ".join(vals) + " |")

    lines.append("")

    # AUROC confidence intervals
    lines.append("## AUROC Bootstrap Confidence Intervals")
    lines.append("")
    for rl in run_labels:
        m = condition_results[rl]
        ci = m.get("auroc_ci", {})
        if "ci_lower" in ci:
            lines.append(f"- **{rl}**: {ci['mean']} [{ci['ci_lower']}, {ci['ci_upper']}] (n_bootstrap={ci['n_bootstrap']})")
        elif "note" in ci:
            lines.append(f"- **{rl}**: {ci['note']}")
    lines.append("")

    # Per-difficulty breakdown
    has_difficulty = any(
        condition_results[rl].get("per_difficulty")
        for rl in run_labels
        if "error" not in condition_results[rl]
    )

    if has_difficulty:
        lines.append("## Per-Difficulty Breakdown")
        lines.append("")

        # Collect all difficulty levels
        all_diffs = set()
        for rl in run_labels:
            m = condition_results[rl]
            all_diffs.update(m.get("per_difficulty", {}).keys())

        for diff in sorted(all_diffs):
            lines.append(f"### Difficulty: {diff}")
            lines.append("")
            lines.append("| Metric | " + " | ".join(run_labels) + " |")
            lines.append("|---|" + "|".join(["---"] * len(run_labels)) + "|")

            diff_metrics = [
                ("N", lambda d: str(d["n"])),
                ("Accuracy", lambda d: f"{d['accuracy']}"),
                ("Mean confidence", lambda d: f"{d['mean_confidence']}"),
                ("ECE", lambda d: f"{d['ece']}"),
                ("AUROC", lambda d: f"{d['auroc']}" if d["auroc"] is not None else "N/A"),
                ("Brier", lambda d: f"{d['brier']}"),
            ]

            for label, fn in diff_metrics:
                vals = []
                for rl in run_labels:
                    pd_data = condition_results[rl].get("per_difficulty", {})
                    if diff in pd_data:
                        vals.append(fn(pd_data[diff]))
                    else:
                        vals.append("--")
                lines.append(f"| {label} | " + " | ".join(vals) + " |")
            lines.append("")

    # Calibration curve data
    lines.append("## Calibration Curves")
    lines.append("")
    for rl in run_labels:
        m = condition_results[rl]
        bins = m.get("calibration_bins", [])
        if not bins:
            continue

        lines.append(f"### {rl}")
        lines.append("")
        lines.append("| Bin | Mean confidence | Accuracy | Count |")
        lines.append("|---|---|---|---|")
        for b in bins:
            lo = int(b["bin_lower"])
            hi = int(b["bin_upper"])
            mc = f"{b['mean_confidence']}" if b["mean_confidence"] is not None else "--"
            acc = f"{b['accuracy']}" if b["accuracy"] is not None else "--"
            lines.append(f"| {lo}-{hi} | {mc} | {acc} | {b['count']} |")
        lines.append("")

    # Statistical tests
    lines.append("## Statistical Tests")
    lines.append("")

    if len(run_labels) >= 2:
        # Brier paired t-test
        bt = stat_tests.get("brier_ttest", {})
        if bt:
            lines.append(f"### Paired t-test on Brier scores ({run_labels[0]} vs {run_labels[1]})")
            lines.append("")
            if "note" in bt:
                lines.append(f"_{bt['note']}_")
            else:
                sig = ""
                p = bt.get("p_value", 1.0)
                if p < 0.01:
                    sig = " **"
                elif p < 0.05:
                    sig = " *"
                lines.append(f"- N pairs: {bt['n_pairs']}")
                lines.append(f"- t-statistic: {bt['t_statistic']}")
                lines.append(f"- p-value: {bt['p_value']}{sig}")
                lines.append(f"- Mean Brier difference: {bt['mean_diff']}")
                lines.append(f"- Direction: {bt['direction']}")
            lines.append("")

        # Bootstrap AUROC comparison
        ba = stat_tests.get("auroc_bootstrap", {})
        if ba:
            lines.append(f"### Bootstrap AUROC comparison ({run_labels[0]} vs {run_labels[1]})")
            lines.append("")
            if "note" in ba:
                lines.append(f"_{ba['note']}_")
            else:
                lines.append(f"- N pairs: {ba['n_pairs']}")
                lines.append(f"- Mean AUROC difference: {ba['mean_diff']}")
                lines.append(f"- 95% CI: [{ba['ci_lower']}, {ba['ci_upper']}]")
                lines.append(f"- p-value: {ba['p_value']}")
            lines.append("")
    else:
        lines.append("_Only one condition provided; no between-condition tests._")
        lines.append("")

    # Parse failure note
    lines.append("## Parse Failure Rates")
    lines.append("")
    for rl in run_labels:
        m = condition_results[rl]
        rate = m.get("parse_fail_rate", 0)
        flag = " **WARNING: >10% parse failures -- data unreliable**" if rate > 0.1 else ""
        lines.append(f"- **{rl}**: {rate:.1%} ({m['n_parse_fail']}/{m['n_total']}){flag}")
    lines.append("")

    lines.append("\\* p < 0.05, \\*\\* p < 0.01")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score Dimension 1: Metacognitive Monitoring (Failure Prediction)."
    )
    parser.add_argument(
        "--runs",
        nargs="+",
        type=Path,
        required=True,
        help="Run directories to score (e.g., runs/v2-sonnet-baseline runs/v2-sonnet-kyl)",
    )
    parser.add_argument(
        "--tasks",
        type=Path,
        required=True,
        help="Directory containing v2 monitoring task YAML files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=BENCHMARKS_DIR / "results" / "RESULTS-monitoring.md",
        help="Output path for results markdown",
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

    # Load ground truth
    ground_truth = load_task_ground_truth(tasks_dir)
    if not ground_truth:
        print(f"No monitoring questions found in {tasks_dir}", file=sys.stderr)
        sys.exit(1)
    print(f"Loaded {len(ground_truth)} ground-truth questions from {tasks_dir}")

    # Load and score each run
    condition_results = {}
    all_records = {}  # label -> records list
    run_labels = []

    for rd in run_dirs:
        if not rd.exists():
            print(f"Warning: run directory not found: {rd}", file=sys.stderr)
            continue
        label = rd.name
        run_labels.append(label)
        records = load_run_data(rd, ground_truth)
        all_records[label] = records
        metrics = compute_condition_metrics(records)
        condition_results[label] = metrics
        print(f"  {label}: {metrics['n_valid']}/{metrics['n_total']} valid, "
              f"ECE={metrics.get('ece', 'N/A')}, "
              f"AUROC={metrics.get('auroc', 'N/A')}, "
              f"Brier={metrics.get('brier', 'N/A')}")

    if not run_labels:
        print("No valid run directories found.", file=sys.stderr)
        sys.exit(1)

    # Statistical comparisons (between first two conditions)
    stat_tests = {}
    if len(run_labels) >= 2:
        label_a, label_b = run_labels[0], run_labels[1]
        valid_a = [r for r in all_records[label_a] if r["parse_ok"]]
        valid_b = [r for r in all_records[label_b] if r["parse_ok"]]

        if valid_a and valid_b:
            qids_a = [r["qid"] for r in valid_a]
            qids_b = [r["qid"] for r in valid_b]
            conf_a = np.array([r["confidence"] for r in valid_a])
            corr_a = np.array([r["correctness"] for r in valid_a])
            conf_b = np.array([r["confidence"] for r in valid_b])
            corr_b = np.array([r["correctness"] for r in valid_b])

            brier_a = per_question_brier(conf_a, corr_a)
            brier_b = per_question_brier(conf_b, corr_b)

            stat_tests["brier_ttest"] = paired_brier_ttest(
                brier_a, brier_b, qids_a, qids_b
            )
            stat_tests["auroc_bootstrap"] = bootstrap_auroc_comparison(
                conf_a, corr_a, conf_b, corr_b, qids_a, qids_b
            )

    # Generate report
    report = format_report(condition_results, stat_tests, run_labels)

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report)
    print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    main()
