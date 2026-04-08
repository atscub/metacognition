#!/usr/bin/env python3
"""Synthesize all per-dimension results into RESULTS-v2.md.

Scans a results directory for RESULTS-*.md files, extracts key metrics
from their markdown tables, and produces a combined report. Works with
whatever dimensions exist — produces a partial report if some are missing.

Usage:
    python scripts/synthesize.py \
      --results-dir benchmarks/results/ \
      --output benchmarks/RESULTS-v2.md \
      --v1-results benchmarks/RESULTS-sonnet.md
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS_DIR = PROJECT_ROOT / "benchmarks"

# ---------------------------------------------------------------------------
# Dimension registry — maps filename patterns to dimension metadata
# ---------------------------------------------------------------------------

DIMENSION_REGISTRY = {
    "monitoring": {
        "name": "Dim 1: Metacognitive Monitoring",
        "short": "Monitoring",
        "key_metrics": ["ECE (lower is better)", "AUROC (higher is better)",
                        "Brier score (lower is better)", "Accuracy"],
        "primary_metric": "ECE (lower is better)",
        "direction": "lower",  # lower is better for the primary metric
    },
    "knowledge": {
        "name": "Dim 2: Metacognitive Knowledge",
        "short": "Knowledge",
        "key_metrics": ["Strategy match (exact)", "Strategy match (partial+exact)",
                        "Difficulty correlation"],
        "primary_metric": "Strategy match (exact)",
        "direction": "higher",
    },
    "control": {
        "name": "Dim 3: Metacognitive Control",
        "short": "Control",
        "key_metrics": ["F1 (abstain/answer decision)",
                        "Appropriate abstention rate (unanswerable refused)",
                        "Confident-wrong rate (conf >= 70, wrong)"],
        "primary_metric": "F1 (abstain/answer decision)",
        "direction": "higher",
    },
    "bias-awareness": {
        "name": "Dim 4: Bias Awareness",
        "short": "Bias Awareness",
        "key_metrics": ["Detection accuracy", "Naming accuracy",
                        "False positive rate"],
        "primary_metric": "Detection accuracy",
        "direction": "higher",
    },
    "wild": {
        "name": "Dim W: Observed-Failure Replication",
        "short": "Wild",
        "key_metrics": ["Mean score"],
        "primary_metric": "Mean score",
        "direction": "higher",
    },
}


# ---------------------------------------------------------------------------
# Markdown table parsing
# ---------------------------------------------------------------------------

def parse_markdown_tables(text: str) -> list[dict]:
    """Parse all markdown tables from text.

    Returns a list of dicts, each with:
      - section: the heading text above the table (or "")
      - headers: list of column header strings
      - rows: list of lists of cell strings
    """
    tables = []
    lines = text.split("\n")
    i = 0
    current_section = ""

    while i < len(lines):
        line = lines[i].strip()

        # Track section headings
        heading_match = re.match(r"^(#{1,6})\s+(.*)", line)
        if heading_match:
            current_section = heading_match.group(2).strip()
            i += 1
            continue

        # Detect table: line starts with |, next line is a separator (|---|)
        if line.startswith("|") and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if re.match(r"^\|[\s\-:|]+\|$", next_line):
                # Parse header row
                headers = [
                    c.strip() for c in line.strip("|").split("|")
                ]
                # Skip separator
                j = i + 2
                rows = []
                while j < len(lines) and lines[j].strip().startswith("|"):
                    row_line = lines[j].strip()
                    # Skip if it's another separator
                    if re.match(r"^\|[\s\-:|]+\|$", row_line):
                        j += 1
                        continue
                    cells = [c.strip() for c in row_line.strip("|").split("|")]
                    rows.append(cells)
                    j += 1

                tables.append({
                    "section": current_section,
                    "headers": headers,
                    "rows": rows,
                })
                i = j
                continue

        i += 1

    return tables


def extract_metric_from_tables(tables: list[dict], metric_name: str,
                               section_hint: str = "") -> dict[str, str]:
    """Search tables for a row matching metric_name.

    Returns a dict of condition_label -> value string.
    If section_hint is provided, prefer tables under matching sections.
    """
    results: dict[str, str] = {}

    # Sort tables: matching section first
    sorted_tables = sorted(
        tables,
        key=lambda t: (0 if section_hint and section_hint.lower() in t["section"].lower() else 1),
    )

    for table in sorted_tables:
        headers = table["headers"]
        if len(headers) < 2:
            continue

        # Check if metric_name appears in the first column of any row
        for row in table["rows"]:
            if not row:
                continue
            # Case-insensitive partial match on metric name
            row_label = row[0].strip().rstrip("*").strip()
            if metric_name.lower() in row_label.lower() or row_label.lower() in metric_name.lower():
                # Map remaining columns to their headers
                for col_idx in range(1, min(len(headers), len(row))):
                    condition = headers[col_idx].strip()
                    value = row[col_idx].strip()
                    if value and value != "--":
                        results[condition] = value
                if results:
                    return results

    return results


def extract_overall_means_wild(tables: list[dict]) -> dict[str, str]:
    """Special extraction for wild dimension: get mean scores from Overall Means table."""
    for table in tables:
        if "overall means" in table["section"].lower() or "overall" in table["section"].lower():
            headers = table["headers"]
            # Wild table has: Condition | N | Mean score | Std
            for row in table["rows"]:
                if len(row) >= 3:
                    condition = row[0].strip()
                    mean_score = row[2].strip() if len(row) > 2 else "--"
                    if mean_score != "--":
                        yield condition, mean_score


def extract_stat_test(text: str) -> dict | None:
    """Extract p-value and test name from statistical test section."""
    # Look for p-value pattern
    p_match = re.search(r"p[_-]?value:\s*([\d.]+)", text)
    if p_match:
        try:
            p = float(p_match.group(1))
            return {"p_value": p}
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# Dimension result extraction
# ---------------------------------------------------------------------------

def extract_dimension_results(filepath: Path, dim_key: str) -> dict | None:
    """Extract key metrics from a dimension results file.

    Returns a dict with:
      - dimension: dim_key
      - file: filepath
      - conditions: dict of condition_label -> {metric_name: value}
      - p_value: float or None
      - raw_text: the full file text
    """
    try:
        text = filepath.read_text()
    except OSError:
        return None

    if not text.strip():
        return None

    dim_info = DIMENSION_REGISTRY.get(dim_key)
    if not dim_info:
        return None

    tables = parse_markdown_tables(text)
    if not tables:
        return None

    # Build condition -> metrics dict
    conditions: dict[str, dict[str, str]] = {}

    if dim_key == "wild":
        # Wild dimension uses a different table structure
        for condition, mean_score in extract_overall_means_wild(tables):
            conditions.setdefault(condition, {})["Mean score"] = mean_score
    else:
        for metric in dim_info["key_metrics"]:
            metric_values = extract_metric_from_tables(
                tables, metric, section_hint="Overall"
            )
            for cond, val in metric_values.items():
                conditions.setdefault(cond, {})[metric] = val

    # Also try to extract primary metric specifically
    primary = dim_info["primary_metric"]
    primary_values = extract_metric_from_tables(tables, primary, section_hint="Overall")
    for cond, val in primary_values.items():
        conditions.setdefault(cond, {})[primary] = val

    stat = extract_stat_test(text)

    return {
        "dimension": dim_key,
        "dim_info": dim_info,
        "file": filepath,
        "conditions": conditions,
        "p_value": stat["p_value"] if stat else None,
        "raw_text": text,
    }


# ---------------------------------------------------------------------------
# v1 results extraction
# ---------------------------------------------------------------------------

def extract_v1_results(filepath: Path) -> dict | None:
    """Extract key findings from a v1 results file."""
    try:
        text = filepath.read_text()
    except OSError:
        return None

    tables = parse_markdown_tables(text)

    # Look for the statistical tests table
    stat_rows = []
    for table in tables:
        if "statistical" in table["section"].lower() or "wilcoxon" in table["section"].lower():
            for row in table["rows"]:
                if len(row) >= 5:
                    metric = row[0].strip()
                    p_val = row[2].strip() if len(row) > 2 else ""
                    direction = row[5].strip() if len(row) > 5 else ""
                    stat_rows.append({
                        "metric": metric,
                        "p_value": p_val,
                        "direction": direction,
                    })

    # Look for overall summary table
    overall_metrics: dict[str, dict[str, str]] = {}
    for table in tables:
        if "overall" in table["section"].lower() or "summary" in table["section"].lower():
            headers = table["headers"]
            for row in table["rows"]:
                if len(row) >= 2 and len(headers) >= 2:
                    condition = row[0].strip()
                    for ci in range(1, min(len(headers), len(row))):
                        overall_metrics.setdefault(condition, {})[headers[ci].strip()] = row[ci].strip()

    return {
        "file": filepath,
        "stat_tests": stat_rows,
        "overall_metrics": overall_metrics,
        "raw_text": text,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def format_synthesized_report(dimension_results: list[dict],
                              v1_results: dict | None) -> str:
    """Generate the combined RESULTS-v2.md report."""
    lines = ["# KYL Metacognition Benchmark v2 — Combined Results", ""]

    dim_count = len(dimension_results)

    # ----- Executive Summary -----
    lines.append("## Executive Summary")
    lines.append("")

    if dim_count == 0:
        lines.append("No dimension results available yet.")
        lines.append("")
        return "\n".join(lines)

    # Build a summary from actual numbers
    improvements = []
    no_effects = []
    regressions = []

    for dr in dimension_results:
        dim_info = dr["dim_info"]
        primary = dim_info["primary_metric"]
        direction = dim_info["direction"]
        conditions = dr["conditions"]
        p_value = dr.get("p_value")

        cond_labels = sorted(conditions.keys())
        if len(cond_labels) < 2:
            # Single condition — just note its existence
            if cond_labels:
                val = conditions[cond_labels[0]].get(primary, "N/A")
                no_effects.append(
                    f"{dim_info['short']}: single condition ({cond_labels[0]}), "
                    f"{primary} = {val}"
                )
            continue

        # Assume first condition alphabetically is baseline, second is KYL
        # (or use naming heuristic)
        baseline_label = None
        kyl_label = None
        for cl in cond_labels:
            cl_lower = cl.lower()
            if "baseline" in cl_lower:
                baseline_label = cl
            elif "kyl" in cl_lower:
                kyl_label = cl

        if not baseline_label:
            baseline_label = cond_labels[0]
        if not kyl_label:
            kyl_label = cond_labels[1] if len(cond_labels) > 1 else cond_labels[0]

        base_val = conditions.get(baseline_label, {}).get(primary)
        kyl_val = conditions.get(kyl_label, {}).get(primary)

        if base_val and kyl_val:
            # Try to compute difference
            try:
                # Strip percentage signs and other formatting
                bv = float(re.sub(r"[^\d.\-]", "", base_val.split("(")[0]))
                kv = float(re.sub(r"[^\d.\-]", "", kyl_val.split("(")[0]))
                diff = kv - bv
                sig = p_value is not None and p_value < 0.05

                if direction == "lower":
                    # Lower is better, so negative diff = improvement
                    if diff < 0:
                        pct = abs(diff / bv) * 100 if bv != 0 else 0
                        note = f"{dim_info['short']}: KYL improved {primary} by {pct:.1f}% ({base_val} -> {kyl_val})"
                        if sig:
                            note += f" (p = {p_value})"
                        else:
                            note += " (not significant)" if p_value else ""
                        improvements.append(note)
                    elif diff > 0:
                        note = f"{dim_info['short']}: KYL worsened {primary} ({base_val} -> {kyl_val})"
                        if sig:
                            note += f" (p = {p_value})"
                        regressions.append(note)
                    else:
                        no_effects.append(f"{dim_info['short']}: no difference on {primary}")
                else:
                    # Higher is better
                    if diff > 0:
                        pct = abs(diff / bv) * 100 if bv != 0 else 0
                        note = f"{dim_info['short']}: KYL improved {primary} by {pct:.1f}% ({base_val} -> {kyl_val})"
                        if sig:
                            note += f" (p = {p_value})"
                        else:
                            note += " (not significant)" if p_value else ""
                        improvements.append(note)
                    elif diff < 0:
                        note = f"{dim_info['short']}: KYL worsened {primary} ({base_val} -> {kyl_val})"
                        if sig:
                            note += f" (p = {p_value})"
                        regressions.append(note)
                    else:
                        no_effects.append(f"{dim_info['short']}: no difference on {primary}")
            except (ValueError, ZeroDivisionError):
                no_effects.append(
                    f"{dim_info['short']}: {primary} baseline={base_val}, KYL={kyl_val}"
                )
        else:
            no_effects.append(f"{dim_info['short']}: metric values not fully extracted")

    summary_parts = []
    if improvements:
        summary_parts.append(
            "KYL showed improvements on: " + "; ".join(improvements) + "."
        )
    if regressions:
        summary_parts.append(
            "KYL showed regressions on: " + "; ".join(regressions) + "."
        )
    if no_effects:
        summary_parts.append(
            "No significant KYL effect observed on: " + "; ".join(no_effects) + "."
        )
    if not summary_parts:
        summary_parts.append(
            f"{dim_count} dimension(s) scored. See per-dimension details below."
        )

    lines.append(" ".join(summary_parts))
    lines.append("")

    scored_dims = [dr["dim_info"]["short"] for dr in dimension_results]
    all_dims = [v["short"] for v in DIMENSION_REGISTRY.values()]
    missing = [d for d in all_dims if d not in scored_dims]
    if missing:
        lines.append(f"**Not yet scored**: {', '.join(missing)}.")
        lines.append("")

    # ----- Per-Dimension Summary Table -----
    lines.append("## Per-Dimension Summary")
    lines.append("")

    # Collect all condition labels across dimensions
    all_conditions: set[str] = set()
    for dr in dimension_results:
        all_conditions.update(dr["conditions"].keys())
    cond_list = sorted(all_conditions)

    if cond_list:
        header = "| Dimension | Primary metric | " + " | ".join(cond_list) + " | p-value |"
        sep = "|---|---|" + "|".join(["---"] * len(cond_list)) + "|---|"
        lines.append(header)
        lines.append(sep)

        for dr in dimension_results:
            dim_info = dr["dim_info"]
            primary = dim_info["primary_metric"]
            vals = []
            for cl in cond_list:
                v = dr["conditions"].get(cl, {}).get(primary, "--")
                vals.append(v)
            p_str = f"{dr['p_value']}" if dr.get("p_value") is not None else "--"
            lines.append(
                f"| {dim_info['short']} | {primary} | "
                + " | ".join(vals) + f" | {p_str} |"
            )

        lines.append("")
    else:
        lines.append("_No condition data extracted._")
        lines.append("")

    # ----- Cross-Dimension Patterns -----
    lines.append("## Cross-Dimension Patterns")
    lines.append("")

    if dim_count >= 2:
        # Note where KYL helps most vs least
        lines.append(
            "The following patterns emerge from comparing KYL effects across dimensions:"
        )
        lines.append("")
        for dr in dimension_results:
            dim_info = dr["dim_info"]
            primary = dim_info["primary_metric"]
            conditions = dr["conditions"]
            p = dr.get("p_value")
            sig_note = f"(p = {p})" if p is not None else "(no stat test)"
            cond_strs = [
                f"{cl}: {conditions[cl].get(primary, '?')}"
                for cl in sorted(conditions.keys())
            ]
            lines.append(
                f"- **{dim_info['short']}** ({primary}): "
                + ", ".join(cond_strs) + f" {sig_note}"
            )
        lines.append("")
    else:
        lines.append(
            "Only one dimension scored. Cross-dimension analysis requires at "
            "least two completed dimensions."
        )
        lines.append("")

    # ----- v1 Comparison -----
    if v1_results:
        lines.append("## Comparison with v1 Results")
        lines.append("")
        lines.append(f"v1 results loaded from: `{v1_results['file']}`")
        lines.append("")

        if v1_results.get("stat_tests"):
            lines.append("### v1 Statistical Tests")
            lines.append("")
            lines.append("| Metric | p-value | Direction |")
            lines.append("|---|---|---|")
            for st in v1_results["stat_tests"]:
                lines.append(
                    f"| {st['metric']} | {st['p_value']} | {st['direction']} |"
                )
            lines.append("")

        lines.append("### v1 vs v2 Key Differences")
        lines.append("")
        lines.append(
            "v1 measured cognition and metacognition together on a single "
            "rubric. v2 decouples them into separate dimensions with "
            "established academic metrics. Direct numerical comparison is "
            "not appropriate — the measures are fundamentally different."
        )
        lines.append("")
        lines.append("**v1 finding**: KYL reliably improves epistemic process "
                      "metrics (assumption acknowledgment, alternative "
                      "consideration, confidence calibration) but does NOT "
                      "improve error detection or final correctness.")
        lines.append("")
        lines.append(
            "**v2 question**: Does decoupling metacognition from cognition "
            "reveal effects that were masked — or confirm that KYL's impact "
            "is limited to process improvements?"
        )
        lines.append("")

    # ----- Methodology -----
    lines.append("## Methodology")
    lines.append("")
    lines.append("### Benchmark Design")
    lines.append("")
    lines.append(
        "v2 measures metacognition independently from cognition across "
        "four academic dimensions plus observed-failure replication:"
    )
    lines.append("")
    for dim_key, dim_info in DIMENSION_REGISTRY.items():
        lines.append(f"- **{dim_info['name']}**: {dim_info['primary_metric']}")
    lines.append("")
    lines.append("### Conditions")
    lines.append("")
    lines.append("- **Baseline**: `claude -p --disable-slash-commands --no-session-persistence`")
    lines.append("- **KYL**: `claude -p --plugin-dir plugins/metacognition --no-session-persistence`")
    lines.append("")
    lines.append("### Dimensions Scored")
    lines.append("")
    for dr in dimension_results:
        dim_info = dr["dim_info"]
        n_conditions = len(dr["conditions"])
        cond_names = ", ".join(sorted(dr["conditions"].keys()))
        lines.append(f"- {dim_info['name']}: {n_conditions} condition(s) ({cond_names})")
    lines.append("")

    # Source files
    lines.append("### Source Files")
    lines.append("")
    for dr in dimension_results:
        lines.append(f"- {dr['dim_info']['short']}: `{dr['file']}`")
    if v1_results:
        lines.append(f"- v1 results: `{v1_results['file']}`")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synthesize per-dimension results into RESULTS-v2.md."
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=BENCHMARKS_DIR / "results",
        help="Directory containing RESULTS-*.md files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=BENCHMARKS_DIR / "RESULTS-v2.md",
        help="Output path for combined results",
    )
    parser.add_argument(
        "--v1-results",
        type=Path,
        default=None,
        help="Optional v1 results file for comparison (e.g., RESULTS-sonnet.md)",
    )
    args = parser.parse_args()

    # Resolve paths
    results_dir = args.results_dir
    if not results_dir.is_absolute():
        results_dir = BENCHMARKS_DIR / results_dir

    output_path = args.output
    if not output_path.is_absolute():
        output_path = BENCHMARKS_DIR / output_path

    # Scan for dimension result files
    dimension_results = []
    result_files = sorted(results_dir.glob("RESULTS-*.md"))

    if not result_files:
        print(f"No RESULTS-*.md files found in {results_dir}", file=sys.stderr)
        print("Producing empty report.", file=sys.stderr)

    for rf in result_files:
        # Extract dimension key from filename: RESULTS-monitoring.md -> monitoring
        stem = rf.stem  # e.g. "RESULTS-monitoring"
        dim_key = stem.replace("RESULTS-", "").lower()

        # Skip non-dimension files (e.g. RESULTS-hard5)
        if dim_key not in DIMENSION_REGISTRY:
            print(f"  Skipping {rf.name} (no matching dimension: {dim_key})")
            continue

        dr = extract_dimension_results(rf, dim_key)
        if dr:
            n_conds = len(dr["conditions"])
            print(f"  {dim_key}: {n_conds} condition(s) extracted from {rf.name}")
            dimension_results.append(dr)
        else:
            print(f"  {dim_key}: failed to extract results from {rf.name}")

    print(f"Found {len(dimension_results)} dimension result(s)")

    # Load v1 results if provided
    v1_results = None
    if args.v1_results:
        v1_path = args.v1_results
        if not v1_path.is_absolute():
            v1_path = BENCHMARKS_DIR / v1_path
        v1_results = extract_v1_results(v1_path)
        if v1_results:
            print(f"Loaded v1 results from {v1_path}")
        else:
            print(f"Warning: could not load v1 results from {v1_path}",
                  file=sys.stderr)

    # Generate report
    report = format_synthesized_report(dimension_results, v1_results)

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report)
    print(f"\nCombined results written to {output_path}")


if __name__ == "__main__":
    main()
