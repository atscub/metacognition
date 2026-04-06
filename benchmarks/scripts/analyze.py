#!/usr/bin/env python3
"""Analyze KYL benchmark scores and generate results report."""

import argparse
import json
import math
from pathlib import Path

import pandas as pd
import yaml
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS_DIR = PROJECT_ROOT / "benchmarks"
EVAL_DIR = BENCHMARKS_DIR / "eval"
TASKS_DIR = BENCHMARKS_DIR / "tasks"
RUNS_DIR = BENCHMARKS_DIR / "runs"

METRICS = [
    "ungrounded_claims",
    "assumption_ack",
    "alternatives",
    "error_detection",
    "rework",
    "confidence_cal",
    "correctness",
]

METRIC_LABELS = {
    "ungrounded_claims": "Ungrounded claims",
    "assumption_ack": "Assumption acknowledgment",
    "alternatives": "Alternative consideration",
    "error_detection": "Error detection",
    "rework": "Rework cycles",
    "confidence_cal": "Confidence calibration",
    "correctness": "Final correctness",
}


def load_mapping() -> dict:
    """Load the A/B mapping file."""
    mapping_path = EVAL_DIR / ".mapping.json"
    with open(mapping_path) as f:
        return json.load(f)


def load_scores() -> pd.DataFrame:
    """Load and validate scores.csv."""
    scores_path = EVAL_DIR / "scores.csv"
    df = pd.read_csv(scores_path)
    required_cols = {"task_id", "response"} | set(METRICS)
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in scores.csv: {missing}")
    return df


def unmask_scores(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    """Replace A/B response labels with baseline/kyl condition labels."""
    rows = []
    for _, row in df.iterrows():
        task_id = row["task_id"]
        response_label = row["response"]  # "A" or "B"
        if task_id not in mapping:
            continue
        condition = mapping[task_id].get(response_label)
        if condition is None:
            continue
        new_row = row.copy()
        new_row["condition"] = condition
        rows.append(new_row)
    return pd.DataFrame(rows)


def load_task_metadata() -> dict:
    """Load category and primary_skill from all task YAML files."""
    meta = {}
    for yaml_path in TASKS_DIR.rglob("*.yaml"):
        with open(yaml_path) as f:
            task = yaml.safe_load(f)
        if task and "id" in task:
            meta[task["id"]] = {
                "category": task.get("category", "unknown"),
                "primary_skill": task.get("primary_skill", "unknown"),
            }
    return meta


def compute_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Add a total column summing all metrics."""
    df = df.copy()
    df["total"] = df[METRICS].sum(axis=1)
    return df


def summary_table(df: pd.DataFrame, group_col: str | None = None) -> pd.DataFrame:
    """Compute mean and std per condition, optionally grouped."""
    all_metrics = METRICS + ["total"]
    if group_col:
        grouped = df.groupby([group_col, "condition"])[all_metrics]
    else:
        grouped = df.groupby("condition")[all_metrics]
    return grouped.agg(["mean", "std"]).round(3)


def wilcoxon_tests(df: pd.DataFrame) -> list[dict]:
    """Run Wilcoxon signed-rank tests for each metric and total."""
    all_metrics = METRICS + ["total"]
    results = []

    baseline = df[df["condition"] == "baseline"].set_index("task_id")
    kyl = df[df["condition"] == "kyl"].set_index("task_id")
    common = sorted(set(baseline.index) & set(kyl.index))

    if len(common) < 5:
        return results

    for metric in all_metrics:
        b_vals = baseline.loc[common, metric].values
        k_vals = kyl.loc[common, metric].values
        diff = k_vals - b_vals

        # Skip if all differences are zero
        if all(d == 0 for d in diff):
            results.append({
                "metric": metric,
                "statistic": None,
                "p_value": 1.0,
                "effect_size_r": 0.0,
                "n": len(common),
                "direction": "none",
            })
            continue

        try:
            stat_result = stats.wilcoxon(k_vals, b_vals, alternative="two-sided")
            statistic = stat_result.statistic
            p_value = stat_result.pvalue

            # Effect size: rank-biserial correlation r = Z / sqrt(N)
            n = len(common)
            z = stats.norm.ppf(1 - p_value / 2)
            r = z / math.sqrt(n) if n > 0 else 0.0

            mean_diff = k_vals.mean() - b_vals.mean()
            direction = "kyl > baseline" if mean_diff > 0 else "baseline > kyl"

            results.append({
                "metric": metric,
                "statistic": round(statistic, 4),
                "p_value": round(p_value, 4),
                "effect_size_r": round(r, 4),
                "n": n,
                "direction": direction,
            })
        except ValueError:
            results.append({
                "metric": metric,
                "statistic": None,
                "p_value": None,
                "effect_size_r": None,
                "n": len(common),
                "direction": "error",
            })

    return results


def token_comparison() -> dict | None:
    """Compare token counts between baseline and kyl runs if available."""
    totals = {"baseline": [], "kyl": []}
    for mode in ("baseline", "kyl"):
        run_dir = RUNS_DIR / mode
        for json_path in run_dir.glob("*.json"):
            with open(json_path) as f:
                data = json.load(f)
            # Check common token count fields
            tokens = (
                data.get("token_count")
                or data.get("tokens")
                or data.get("usage", {}).get("total_tokens")
            )
            if tokens is not None:
                totals[mode].append(int(tokens))

    if not totals["baseline"] or not totals["kyl"]:
        return None

    return {
        "baseline_mean": round(sum(totals["baseline"]) / len(totals["baseline"]), 1),
        "kyl_mean": round(sum(totals["kyl"]) / len(totals["kyl"]), 1),
        "baseline_n": len(totals["baseline"]),
        "kyl_n": len(totals["kyl"]),
    }


def format_summary_md(summary: pd.DataFrame, title: str) -> str:
    """Format a summary DataFrame as a markdown table."""
    lines = [f"### {title}", ""]
    lines.append(summary.to_markdown())
    lines.append("")
    return "\n".join(lines)


def format_wilcoxon_md(results: list[dict]) -> str:
    """Format Wilcoxon test results as a markdown table."""
    lines = [
        "### Statistical Tests (Wilcoxon signed-rank)",
        "",
        "| Metric | W | p-value | Effect size (r) | N | Direction |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        label = METRIC_LABELS.get(r["metric"], r["metric"])
        w = r["statistic"] if r["statistic"] is not None else "-"
        p = r["p_value"] if r["p_value"] is not None else "-"
        eff = r["effect_size_r"] if r["effect_size_r"] is not None else "-"
        sig = ""
        if isinstance(p, float):
            if p < 0.01:
                sig = " **"
            elif p < 0.05:
                sig = " *"
        lines.append(f"| {label} | {w} | {p}{sig} | {eff} | {r['n']} | {r['direction']} |")
    lines.append("")
    lines.append("\\* p < 0.05, \\*\\* p < 0.01")
    lines.append("")
    return "\n".join(lines)


def generate_report(df: pd.DataFrame, task_meta: dict) -> str:
    """Generate the full RESULTS.md content."""
    df = compute_totals(df)

    # Enrich with metadata
    df["category"] = df["task_id"].map(lambda tid: task_meta.get(tid, {}).get("category", "unknown"))
    df["primary_skill"] = df["task_id"].map(lambda tid: task_meta.get(tid, {}).get("primary_skill", "unknown"))

    sections = ["# KYL Benchmark Results", ""]

    # Overall summary
    overall = summary_table(df)
    sections.append(format_summary_md(overall, "Overall Summary"))

    # Per-category breakdown
    categories = sorted(df["category"].unique())
    if len(categories) > 1 or categories != ["unknown"]:
        cat_summary = summary_table(df, "category")
        sections.append(format_summary_md(cat_summary, "By Category"))

    # Per-skill breakdown
    skills = sorted(df["primary_skill"].unique())
    if len(skills) > 1 or skills != ["unknown"]:
        skill_summary = summary_table(df, "primary_skill")
        sections.append(format_summary_md(skill_summary, "By Primary Skill"))

    # Statistical tests
    test_results = wilcoxon_tests(df)
    if test_results:
        sections.append(format_wilcoxon_md(test_results))

    # Token comparison
    tokens = token_comparison()
    if tokens:
        sections.append("### Token Usage")
        sections.append("")
        sections.append(f"| Condition | Mean tokens | N runs |")
        sections.append(f"|---|---|---|")
        sections.append(f"| Baseline | {tokens['baseline_mean']} | {tokens['baseline_n']} |")
        sections.append(f"| KYL | {tokens['kyl_mean']} | {tokens['kyl_n']} |")
        sections.append("")

    # Interpretation
    sections.append("### Interpretation")
    sections.append("")
    if test_results:
        sig_metrics = [r for r in test_results if isinstance(r.get("p_value"), float) and r["p_value"] < 0.05]
        if sig_metrics:
            sections.append(f"Significant differences (p < 0.05) found in {len(sig_metrics)} metric(s):")
            for r in sig_metrics:
                label = METRIC_LABELS.get(r["metric"], r["metric"])
                sections.append(f"- **{label}**: {r['direction']} (p={r['p_value']}, r={r['effect_size_r']})")
        else:
            sections.append("No statistically significant differences found at p < 0.05.")
    else:
        sections.append("Insufficient paired data for statistical testing (need at least 5 pairs).")

    sections.append("")
    return "\n".join(sections)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze KYL benchmark scores and generate results."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=BENCHMARKS_DIR / "RESULTS.md",
        help="Output path for results (default: benchmarks/RESULTS.md)",
    )
    args = parser.parse_args()

    mapping = load_mapping()
    scores = load_scores()
    df = unmask_scores(scores, mapping)

    if df.empty:
        print("No matched scores found. Check scores.csv and .mapping.json.")
        return

    task_meta = load_task_metadata()
    report = generate_report(df, task_meta)

    args.output.write_text(report)
    print(f"Results written to {args.output}")


if __name__ == "__main__":
    main()
