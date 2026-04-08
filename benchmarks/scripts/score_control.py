#!/usr/bin/env python3
"""Score Dimension 3: Metacognitive Control (Appropriate Abstention).

Compares baseline and KYL conditions on the abstain/answer decision quality.

Usage:
    python scripts/score_control.py \
      --runs runs/v2-sonnet-baseline runs/v2-sonnet-kyl \
      --tasks tasks/v2/control/ \
      --output results/RESULTS-control.md
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
from sklearn.metrics import confusion_matrix as sk_confusion_matrix, f1_score

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS_DIR = PROJECT_ROOT / "benchmarks"

# ---------------------------------------------------------------------------
# Task loading
# ---------------------------------------------------------------------------

ANSWERABILITY_CATEGORIES = {"known", "unknown", "unanswerable"}


def load_tasks(tasks_dir: Path) -> dict[str, dict]:
    """Load all v2 control task YAML files and flatten questions.

    Returns a dict keyed by qid with fields: question, answer, answerability.
    """
    questions: dict[str, dict] = {}
    for yaml_path in sorted(tasks_dir.rglob("*.yaml")):
        with open(yaml_path) as f:
            task = yaml.safe_load(f)
        if task is None:
            continue
        # Support both batch format (questions list) and single-task format
        if "questions" in task:
            for q in task["questions"]:
                qid = q["qid"]
                questions[qid] = {
                    "question": q["question"],
                    "answer": q.get("correct_answers", q.get("answer", "")),
                    "answerability": q.get("answerability", q.get("category", "known")),
                }
        else:
            # Single-task format
            tid = task.get("id", yaml_path.stem)
            questions[tid] = {
                "question": task.get("prompt", ""),
                "answer": task.get("correct_answers", task.get("answer", "")),
                "answerability": task.get("answerability", "known"),
            }
    return questions


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)

ABSTENTION_PHRASES = [
    "i don't know",
    "i do not know",
    "i cannot answer",
    "unanswerable",
    "insufficient information",
    "not enough information",
]


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
    # Try to find a JSON object in the text
    for start in range(len(text)):
        if text[start] == "{":
            for end in range(len(text), start, -1):
                if text[end - 1] == "}":
                    try:
                        return json.loads(text[start:end])
                    except json.JSONDecodeError:
                        continue
    return None


def classify_abstention(parsed: dict | None, raw_text: str) -> bool:
    """Return True if the response is an abstention.

    Checks in priority order:
    1. Explicit abstain flag
    2. Confidence < 10
    3. Answer text contains abstention phrases
    4. Otherwise: answered
    """
    if parsed is not None:
        # 1. Explicit abstain flag
        if parsed.get("abstain") is True:
            return True
        # 2. Low confidence
        confidence = parsed.get("confidence")
        if confidence is not None:
            try:
                if float(confidence) < 10:
                    return True
            except (TypeError, ValueError):
                pass
        # 3. Answer text phrases
        answer_text = str(parsed.get("answer", "")).lower()
        for phrase in ABSTENTION_PHRASES:
            if phrase in answer_text:
                return True
        return False

    # No parsed JSON -- fall back to raw text analysis
    lower = raw_text.lower()
    for phrase in ABSTENTION_PHRASES:
        if phrase in lower:
            return True
    return False


def check_correctness(model_answer: str, ground_truth: str | list[str]) -> bool:
    """Case-insensitive substring match against one or more accepted answers.

    *ground_truth* may be a single string or a list of alternative correct
    phrasings (e.g. from TruthfulQA).  Returns ``True`` if **any** alternative
    appears as a substring of *model_answer*.
    """
    if not model_answer:
        return False
    model_lower = model_answer.strip().lower()
    if isinstance(ground_truth, str):
        ground_truth = [ground_truth]
    return any(
        alt.strip().lower() in model_lower
        for alt in ground_truth
        if alt and alt.strip()
    )


# ---------------------------------------------------------------------------
# Run loading
# ---------------------------------------------------------------------------


def load_run_responses(run_dir: Path) -> dict[str, dict]:
    """Load all response JSON files from a run directory.

    Returns dict keyed by qid with fields: parsed (dict|None), raw (str),
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

        # v2 batch runs store one file per question with qid in the filename
        # or a task_id field. The response text lives in the `response` field
        # which itself may be a JSON envelope from `claude -p --output-format json`.
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

        # Determine qid: prefer explicit qid field, then task_id
        qid = data.get("qid", data.get("task_id", json_path.stem))

        responses[qid] = {
            "parsed": parsed,
            "raw": result_text if isinstance(result_text, str) else str(result_text),
            "parse_ok": parsed is not None,
        }

    return responses


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score_condition(
    responses: dict[str, dict],
    tasks: dict[str, dict],
) -> dict:
    """Score a single condition (baseline or KYL).

    Returns a dict with all metrics and per-question details.
    """
    details: list[dict] = []
    parse_failures = 0
    total = 0

    for qid, task_info in tasks.items():
        if qid not in responses:
            continue
        total += 1
        resp = responses[qid]
        parsed = resp["parsed"]

        if not resp["parse_ok"]:
            parse_failures += 1

        abstained = classify_abstention(parsed, resp["raw"])

        # Correctness (only meaningful if answered)
        correct = False
        if not abstained and parsed is not None:
            model_answer = str(parsed.get("answer", ""))
            correct = check_correctness(model_answer, task_info["answer"])
        elif not abstained:
            # No parsed JSON but didn't abstain -- check raw text
            correct = check_correctness(resp["raw"], task_info["answer"])

        confidence = None
        if parsed is not None and "confidence" in parsed:
            try:
                confidence = float(parsed["confidence"])
            except (TypeError, ValueError):
                pass

        details.append({
            "qid": qid,
            "answerability": task_info["answerability"],
            "abstained": abstained,
            "correct": correct,
            "confidence": confidence,
            "parse_ok": resp["parse_ok"],
        })

    if total == 0:
        return {"error": "No matching questions found between run and tasks"}

    # --- Compute metrics ---

    # Group by answerability
    by_cat: dict[str, list[dict]] = {"known": [], "unknown": [], "unanswerable": []}
    for d in details:
        cat = d["answerability"]
        if cat in by_cat:
            by_cat[cat].append(d)

    # 1. Appropriate abstention rate: % of unanswerable correctly refused
    unanswerable = by_cat["unanswerable"]
    appropriate_abstention = (
        sum(1 for d in unanswerable if d["abstained"]) / len(unanswerable)
        if unanswerable else float("nan")
    )

    # 2. Inappropriate abstention rate: % of known questions incorrectly refused
    known = by_cat["known"]
    inappropriate_abstention = (
        sum(1 for d in known if d["abstained"]) / len(known)
        if known else float("nan")
    )

    # 3. Confident-wrong rate: % of answers with confidence >= 70 that are wrong
    confident_answers = [
        d for d in details
        if not d["abstained"] and d["confidence"] is not None and d["confidence"] >= 70
    ]
    confident_wrong = (
        sum(1 for d in confident_answers if not d["correct"]) / len(confident_answers)
        if confident_answers else float("nan")
    )

    # 4. F1 of abstain/answer decision
    #    Positive class = "should abstain": unanswerable + (unknown and wrong)
    y_true = []  # 1 = should abstain, 0 = should answer
    y_pred = []  # 1 = abstained, 0 = answered
    for d in details:
        should_abstain = (
            d["answerability"] == "unanswerable"
            or (d["answerability"] == "unknown" and not d["correct"] and not d["abstained"])
        )
        # For unknown questions that were abstained, we also consider them
        # "should abstain" if the model couldn't have gotten them right.
        # But we can only judge correctness on answered questions.
        # Re-define: should_abstain = unanswerable, OR unknown-category
        # where the model would be wrong (approximated by: unknown + answered + wrong).
        # For abstained unknowns, we treat "should abstain" as True since
        # the model had no confident answer.
        if d["answerability"] == "unanswerable":
            y_true.append(1)
        elif d["answerability"] == "unknown":
            if d["abstained"]:
                # Model abstained on unknown -- we give benefit of the doubt:
                # count as "should abstain" since the model judged it unknowable
                y_true.append(1)
            elif not d["correct"]:
                # Answered wrong on unknown -- should have abstained
                y_true.append(1)
            else:
                # Answered correctly on unknown -- should have answered
                y_true.append(0)
        else:
            # known -- should answer
            y_true.append(0)

        y_pred.append(1 if d["abstained"] else 0)

    abstention_f1 = f1_score(y_true, y_pred, zero_division=0.0)

    # 5. Dunning-Kruger index: (confident + correct) / (confident + wrong)
    confident_correct = sum(
        1 for d in confident_answers if d["correct"]
    )
    confident_wrong_count = sum(
        1 for d in confident_answers if not d["correct"]
    )
    dk_index = (
        confident_correct / confident_wrong_count
        if confident_wrong_count > 0
        else float("inf") if confident_correct > 0 else float("nan")
    )

    # 6. Confusion matrix: (known/unknown/unanswerable) x (answered/abstained)
    cm = {}
    for cat in ("known", "unknown", "unanswerable"):
        items = by_cat[cat]
        cm[cat] = {
            "answered": sum(1 for d in items if not d["abstained"]),
            "abstained": sum(1 for d in items if d["abstained"]),
            "total": len(items),
        }

    return {
        "metrics": {
            "appropriate_abstention_rate": appropriate_abstention,
            "inappropriate_abstention_rate": inappropriate_abstention,
            "confident_wrong_rate": confident_wrong,
            "abstention_f1": abstention_f1,
            "dunning_kruger_index": dk_index,
        },
        "confusion_matrix": cm,
        "details": details,
        "parse_failure_rate": parse_failures / total if total > 0 else 0.0,
        "total_questions": total,
        "y_true": y_true,
        "y_pred": y_pred,
    }


# ---------------------------------------------------------------------------
# McNemar's test
# ---------------------------------------------------------------------------


def mcnemar_test(
    y_pred_a: list[int],
    y_pred_b: list[int],
) -> dict:
    """McNemar's test comparing two conditions' abstain/answer decisions.

    Both lists must be aligned (same question order).
    """
    if len(y_pred_a) != len(y_pred_b):
        return {"error": "Prediction lists have different lengths"}

    # Build the 2x2 contingency table
    # b=0 (answered)  b=1 (abstained)
    # a=0   n00          n01
    # a=1   n10          n11
    n00 = n01 = n10 = n11 = 0
    for a, b in zip(y_pred_a, y_pred_b):
        if a == 0 and b == 0:
            n00 += 1
        elif a == 0 and b == 1:
            n01 += 1
        elif a == 1 and b == 0:
            n10 += 1
        else:
            n11 += 1

    # McNemar's test uses the off-diagonal elements
    n_discordant = n01 + n10
    if n_discordant == 0:
        return {
            "statistic": 0.0,
            "p_value": 1.0,
            "n01": n01,
            "n10": n10,
            "n_discordant": 0,
            "note": "No discordant pairs",
        }

    # Use exact binomial test if discordant count < 25, chi-squared otherwise
    if n_discordant < 25:
        # Exact binomial: test whether n01 ~ Binomial(n_discordant, 0.5)
        result = stats.binomtest(n01, n_discordant, 0.5)
        p_value = result.pvalue
        stat_name = "exact_binomial"
        statistic = float(n01)
    else:
        # Chi-squared with continuity correction
        statistic = (abs(n01 - n10) - 1) ** 2 / (n01 + n10)
        p_value = 1 - stats.chi2.cdf(statistic, df=1)
        stat_name = "chi2_corrected"

    return {
        "test": stat_name,
        "statistic": round(float(statistic), 4),
        "p_value": round(float(p_value), 4),
        "n01": n01,
        "n10": n10,
        "n_discordant": n_discordant,
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
    mcnemar: dict | None,
    run_labels: list[str],
) -> str:
    """Generate a markdown report from scored results."""
    lines: list[str] = []
    lines.append("# Dimension 3: Metacognitive Control (Appropriate Abstention)")
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
        "appropriate_abstention_rate": "Appropriate abstention rate (unanswerable refused)",
        "inappropriate_abstention_rate": "Inappropriate abstention rate (known refused)",
        "confident_wrong_rate": "Confident-wrong rate (conf >= 70, wrong)",
        "abstention_f1": "F1 (abstain/answer decision)",
        "dunning_kruger_index": "Dunning-Kruger index (confident-correct / confident-wrong)",
    }

    for key, label in metric_labels.items():
        row = f"| {label} |"
        for run_label in run_labels:
            val = results[run_label]["metrics"][key]
            if key in ("abstention_f1", "dunning_kruger_index"):
                row += f" {fmt(val)} |"
            else:
                row += f" {fmt_pct(val)} |"
        lines.append(row)

    # Parse failure rate
    row = "| Parse failure rate |"
    for run_label in run_labels:
        row += f" {fmt_pct(results[run_label]['parse_failure_rate'])} |"
    lines.append(row)

    # Total questions
    row = "| Total questions |"
    for run_label in run_labels:
        row += f" {results[run_label]['total_questions']} |"
    lines.append(row)

    lines.append("")

    # --- Confusion matrix per condition ---
    lines.append("## Confusion Matrix (Category x Decision)")
    lines.append("")

    for run_label in run_labels:
        cm = results[run_label]["confusion_matrix"]
        lines.append(f"### {run_label}")
        lines.append("")
        lines.append("| Category | Answered | Abstained | Total |")
        lines.append("|---|---|---|---|")
        for cat in ("known", "unknown", "unanswerable"):
            if cat in cm:
                c = cm[cat]
                lines.append(f"| {cat} | {c['answered']} | {c['abstained']} | {c['total']} |")
        lines.append("")

    # --- Per-category breakdown ---
    lines.append("## Per-Category Breakdown")
    lines.append("")

    for cat in ("known", "unknown", "unanswerable"):
        lines.append(f"### {cat.capitalize()}")
        lines.append("")
        lines.append("| Metric |" + "".join(f" {l} |" for l in run_labels))
        lines.append("|---|" + "---|" * len(run_labels))

        for run_label in run_labels:
            details = results[run_label]["details"]
            cat_items = [d for d in details if d["answerability"] == cat]
            if not cat_items:
                continue

        # Compute per-category stats for each run
        rows_data: dict[str, list[str]] = {
            "N": [],
            "Answered": [],
            "Abstained": [],
            "Correct (of answered)": [],
            "Abstention rate": [],
        }

        for run_label in run_labels:
            details = results[run_label]["details"]
            cat_items = [d for d in details if d["answerability"] == cat]
            n = len(cat_items)
            answered = [d for d in cat_items if not d["abstained"]]
            abstained_items = [d for d in cat_items if d["abstained"]]
            correct = [d for d in answered if d["correct"]]

            rows_data["N"].append(str(n))
            rows_data["Answered"].append(str(len(answered)))
            rows_data["Abstained"].append(str(len(abstained_items)))
            rows_data["Correct (of answered)"].append(
                f"{len(correct)}/{len(answered)}" if answered else "N/A"
            )
            rows_data["Abstention rate"].append(
                fmt_pct(len(abstained_items) / n) if n > 0 else "N/A"
            )

        for metric_name, vals in rows_data.items():
            lines.append(f"| {metric_name} | " + " | ".join(vals) + " |")
        lines.append("")

    # --- Statistical test ---
    lines.append("## Statistical Comparison (McNemar's Test)")
    lines.append("")

    if mcnemar is None:
        lines.append("McNemar's test requires exactly two conditions. Skipped.")
    elif "error" in mcnemar:
        lines.append(f"Error: {mcnemar['error']}")
    else:
        lines.append(f"- **Test**: {mcnemar.get('test', 'N/A')}")
        lines.append(f"- **Statistic**: {mcnemar.get('statistic', 'N/A')}")
        p = mcnemar.get("p_value", None)
        sig = ""
        if isinstance(p, (int, float)):
            if p < 0.01:
                sig = " **"
            elif p < 0.05:
                sig = " *"
        lines.append(f"- **p-value**: {p}{sig}")
        lines.append(f"- **Discordant pairs**: {mcnemar.get('n_discordant', 'N/A')}")
        lines.append(f"  - Condition 1 abstained, Condition 2 answered: {mcnemar.get('n01', 'N/A')}")
        lines.append(f"  - Condition 1 answered, Condition 2 abstained: {mcnemar.get('n10', 'N/A')}")
        if mcnemar.get("note"):
            lines.append(f"- **Note**: {mcnemar['note']}")
        lines.append("")
        lines.append("\\* p < 0.05, \\*\\* p < 0.01")

    lines.append("")

    # --- Parse failure warning ---
    for run_label in run_labels:
        pfr = results[run_label]["parse_failure_rate"]
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
        description="Score Dimension 3: Metacognitive Control (Appropriate Abstention)."
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
        help="Directory containing v2 control task YAML files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=BENCHMARKS_DIR / "results" / "RESULTS-control.md",
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
        print(f"Error: no questions found in {tasks_dir}", file=sys.stderr)
        sys.exit(1)
    print(f"Loaded {len(tasks)} questions from {tasks_dir}")

    # Validate answerability labels
    for qid, t in tasks.items():
        if t["answerability"] not in ANSWERABILITY_CATEGORIES:
            print(
                f"Warning: qid={qid} has unknown answerability '{t['answerability']}', "
                f"expected one of {ANSWERABILITY_CATEGORIES}",
                file=sys.stderr,
            )

    # Score each run
    results: dict[str, dict] = {}
    run_labels: list[str] = []
    for run_dir in run_dirs:
        label = run_dir.name
        run_labels.append(label)
        responses = load_run_responses(run_dir)
        matched = sum(1 for qid in tasks if qid in responses)
        print(f"  {label}: {matched}/{len(tasks)} questions matched")
        results[label] = score_condition(responses, tasks)

        if "error" in results[label]:
            print(f"  Error scoring {label}: {results[label]['error']}", file=sys.stderr)

    # McNemar's test (only if exactly 2 runs and both have predictions)
    mcnemar = None
    if len(run_labels) == 2:
        r0 = results[run_labels[0]]
        r1 = results[run_labels[1]]
        if "y_pred" in r0 and "y_pred" in r1:
            # Align predictions on the same question set
            qids_0 = [d["qid"] for d in r0["details"]]
            qids_1 = [d["qid"] for d in r1["details"]]
            common_qids = [q for q in qids_0 if q in set(qids_1)]

            if common_qids:
                pred_map_0 = {
                    d["qid"]: (1 if d["abstained"] else 0) for d in r0["details"]
                }
                pred_map_1 = {
                    d["qid"]: (1 if d["abstained"] else 0) for d in r1["details"]
                }
                aligned_0 = [pred_map_0[q] for q in common_qids]
                aligned_1 = [pred_map_1[q] for q in common_qids]
                mcnemar = mcnemar_test(aligned_0, aligned_1)
                print(f"  McNemar's test on {len(common_qids)} common questions")
            else:
                mcnemar = {"error": "No common questions between the two runs"}

    # Generate report
    report = generate_report(results, mcnemar, run_labels)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report)
    print(f"\nResults written to {output_path}")


if __name__ == "__main__":
    main()
