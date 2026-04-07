#!/usr/bin/env python3
"""Generate blind A/B evaluation pairs from baseline and kyl benchmark runs."""

import argparse
import json
import random
import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS_DIR = PROJECT_ROOT / "benchmarks"
RUNS_DIR = BENCHMARKS_DIR / "runs"
EVAL_DIR = BENCHMARKS_DIR / "eval"
PAIRS_DIR = EVAL_DIR / "pairs"
TASKS_DIR = BENCHMARKS_DIR / "tasks"


def load_run(path: Path) -> dict:
    """Load a JSON run file."""
    with open(path) as f:
        return json.load(f)


def find_task_yaml(task_id: str) -> dict | None:
    """Find and load the YAML task file for a given task_id."""
    for yaml_path in TASKS_DIR.rglob("*.yaml"):
        with open(yaml_path) as f:
            task = yaml.safe_load(f)
        if task and task.get("id") == task_id:
            return task
    return None


def strip_metadata(response_text: str) -> str:
    """Strip metadata that could reveal condition (plugin mentions, system prompts)."""
    # Remove references to metacognition plugin
    text = re.sub(r"(?i)metacognition\s*plugin", "[plugin]", response_text)
    text = re.sub(r"(?i)plugins?/metacognition", "[plugin-path]", text)
    # Remove treatment prefix echoes
    text = re.sub(
        r"(?i)(know\s+your\s+limits|epistemic\s+humility|KYL)\s*(mode|protocol|framework)",
        "[treatment]",
        text,
    )
    # Remove system prompt content if leaked
    text = re.sub(r"<system>.*?</system>", "[system-content-removed]", text, flags=re.DOTALL)
    return text


def extract_response_text(run_data: dict) -> str:
    """Extract the response text from a run, handling JSON output format."""
    response = run_data.get("response", "")
    # Try to parse as JSON (claude --output-format json wraps output)
    try:
        parsed = json.loads(response)
        if isinstance(parsed, dict):
            # Common keys in claude JSON output
            for key in ("result", "text", "content", "response"):
                if key in parsed:
                    return str(parsed[key])
            return json.dumps(parsed, indent=2)
        return str(parsed)
    except (json.JSONDecodeError, TypeError):
        return response


def generate_pairs(seed: int | None = None, baseline: str = "baseline", kyl: str = "kyl", output_suffix: str = "") -> None:
    """Generate anonymized A/B pairs for all tasks present in both run dirs."""
    if seed is not None:
        random.seed(seed)

    baseline_dir = RUNS_DIR / baseline
    kyl_dir = RUNS_DIR / kyl

    pairs_dir = EVAL_DIR / f"pairs{output_suffix}"
    mapping_filename = f".mapping{output_suffix}.json"

    baseline_files = {p.stem: p for p in baseline_dir.glob("*.json")}
    kyl_files = {p.stem: p for p in kyl_dir.glob("*.json")}

    common_ids = sorted(set(baseline_files) & set(kyl_files))

    if not common_ids:
        print("No matching task_ids found in both runs/baseline/ and runs/kyl/.")
        return

    print(f"Found {len(common_ids)} task(s) with both baseline and kyl runs.")

    mapping = {}
    pairs_dir.mkdir(parents=True, exist_ok=True)

    for task_id in common_ids:
        baseline_run = load_run(baseline_files[task_id])
        kyl_run = load_run(kyl_files[task_id])

        # Randomly assign A/B
        if random.random() < 0.5:
            a_label, b_label = "baseline", "kyl"
            a_run, b_run = baseline_run, kyl_run
        else:
            a_label, b_label = "kyl", "baseline"
            a_run, b_run = kyl_run, baseline_run

        mapping[task_id] = {"A": a_label, "B": b_label}

        # Get the shared prompt (use baseline prompt without treatment prefix)
        prompt = baseline_run.get("prompt", "[prompt not available]")

        # Extract and anonymize responses
        a_text = strip_metadata(extract_response_text(a_run))
        b_text = strip_metadata(extract_response_text(b_run))

        # Get title from task YAML if available
        task_yaml = find_task_yaml(task_id)
        title = task_yaml.get("title", task_id) if task_yaml else task_id

        # Write the pair file
        pair_content = f"""# Task: {task_id} — {title}

## Prompt
{prompt}

## Response A
{a_text}

## Response B
{b_text}

---
Score each response on the following metrics (0-3):

| Metric | Response A | Response B |
|---|---|---|
| Ungrounded claims | | |
| Assumption acknowledgment | | |
| Alternative consideration | | |
| Error detection | | |
| Rework cycles | | |
| Confidence calibration | | |
| Final correctness | | |
| **Total** | | |
"""
        pair_path = pairs_dir / f"{task_id}.md"
        pair_path.write_text(pair_content)
        print(f"  Written: {pair_path}")

    # Save mapping (hidden file)
    mapping_path = EVAL_DIR / mapping_filename
    with open(mapping_path, "w") as f:
        json.dump(mapping, f, indent=2)
    print(f"\nMapping saved to {mapping_path}")
    print(f"Generated {len(common_ids)} evaluation pair(s).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate blind A/B evaluation pairs from benchmark runs."
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible A/B assignment",
    )
    parser.add_argument(
        "--baseline-dir",
        default="baseline",
        help="Baseline runs directory name under runs/ (default: baseline)",
    )
    parser.add_argument(
        "--kyl-dir",
        default="kyl",
        help="KYL runs directory name under runs/ (default: kyl)",
    )
    parser.add_argument(
        "--output-suffix",
        default="",
        help="Suffix for output pairs dir and mapping file (e.g. '-haiku')",
    )
    args = parser.parse_args()

    generate_pairs(seed=args.seed, baseline=args.baseline_dir, kyl=args.kyl_dir, output_suffix=args.output_suffix)


if __name__ == "__main__":
    main()
