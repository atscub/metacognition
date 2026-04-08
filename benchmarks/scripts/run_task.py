#!/usr/bin/env python3
"""Runner script that executes KYL benchmark tasks via the claude CLI.

Supports both v1 tasks (single prompt) and v2 tasks (batch and single-task
formats with structured JSON output parsing).
"""

import argparse
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS_DIR = PROJECT_ROOT / "benchmarks"
TASKS_DIR = BENCHMARKS_DIR / "tasks"
RUNS_DIR = BENCHMARKS_DIR / "runs"

V2_DIMENSIONS = ["monitoring", "control", "knowledge", "bias_awareness", "wild"]


def load_task(task_path: Path) -> dict:
    """Load a YAML task file and return its contents."""
    with open(task_path) as f:
        return yaml.safe_load(f)


def find_all_tasks(dimension: str | None = None) -> list[Path]:
    """Find all YAML task files under benchmarks/tasks/.

    If *dimension* is set, only return v2 tasks whose ``dimension`` field
    matches.  v1 tasks (no ``dimension`` field) are excluded when a dimension
    filter is active.
    """
    all_paths = sorted(TASKS_DIR.rglob("*.yaml"))
    if dimension is None:
        return all_paths

    filtered: list[Path] = []
    for p in all_paths:
        task = load_task(p)
        if task.get("dimension") == dimension:
            filtered.append(p)
    return filtered


def build_command(mode: str, model: str, prompt: str) -> list[str]:
    """Build the claude CLI command for the given mode.

    The prompt is passed as a positional argument to ``claude -p``.
    """
    cmd = [
        "claude", "-p",
        "--model", model,
        "--output-format", "json",
        "--no-session-persistence",
        "--disable-slash-commands",
    ]
    if mode == "kyl":
        plugin_dir = PROJECT_ROOT / "plugins" / "metacognition"
        cmd.extend(["--plugin-dir", str(plugin_dir)])
        # Remove --disable-slash-commands so KYL skills can be invoked
        cmd.remove("--disable-slash-commands")
    cmd.append(prompt)
    return cmd


def build_prompt(task: dict, mode: str) -> str:
    """Build the full prompt for the given task and mode."""
    prompt = task["prompt"]
    if mode == "kyl" and task.get("treatment_prefix"):
        prompt = task["treatment_prefix"] + "\n\n" + prompt
    return prompt


# ---------------------------------------------------------------------------
# v2 helpers
# ---------------------------------------------------------------------------

def parse_structured_response(raw_text: str) -> tuple[dict | None, bool]:
    """Extract a JSON object from *raw_text*.

    Handles markdown code fences (````` ```json ... ``` `````) and extra
    surrounding text.  Returns ``(parsed_dict, True)`` on success or
    ``(None, False)`` on failure.
    """
    if not raw_text or not raw_text.strip():
        return None, False

    # First try to extract the claude CLI result text from the JSON wrapper
    text = raw_text
    try:
        cli_json = json.loads(raw_text)
        if isinstance(cli_json, dict) and "result" in cli_json:
            text = cli_json["result"]
    except (json.JSONDecodeError, TypeError):
        pass

    # Strip markdown code fences
    fence_pattern = re.compile(
        r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL
    )
    fence_match = fence_pattern.search(text)
    if fence_match:
        candidate = fence_match.group(1).strip()
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed, True
        except json.JSONDecodeError:
            pass

    # Try to find first { ... } block (greedy from first { to last })
    brace_start = text.find("{")
    if brace_start == -1:
        return None, False

    brace_end = text.rfind("}")
    if brace_end == -1 or brace_end <= brace_start:
        return None, False

    candidate = text[brace_start : brace_end + 1]
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed, True
    except json.JSONDecodeError:
        pass

    return None, False


def build_v2_prompt(task: dict, mode: str, question_text: str | None = None) -> str:
    """Build a prompt for a v2 task.

    For batch tasks, *question_text* is substituted into ``prompt_template``.
    For single-task v2 tasks, the regular ``prompt`` field is used (same as v1).
    """
    if question_text is not None:
        # Batch format — substitute {question} into template
        template = task["prompt_template"]
        prompt = template.replace("{question}", question_text)
    else:
        prompt = task["prompt"]

    if mode == "kyl" and task.get("treatment_prefix"):
        prompt = task["treatment_prefix"] + "\n\n" + prompt
    return prompt


def _run_claude_session(
    cmd: list[str],
    timeout: int,
) -> tuple[str, str, int, float]:
    """Run a single ``claude -p`` session and return (stdout, stderr, returncode, duration)."""
    start = time.monotonic()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        duration = time.monotonic() - start
        return result.stdout, result.stderr, result.returncode, round(duration, 2)
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start
        return "", f"TIMEOUT after {timeout}s", -1, round(duration, 2)


def run_v2_batch_task(
    task: dict,
    mode: str,
    model: str,
    timeout: int,
    dry_run: bool,
    output_dir: str | None = None,
) -> list[dict]:
    """Run a v2 batch-format task (one session per question).

    Returns a list of per-question result dicts.
    """
    task_id = task["id"]
    questions = task["questions"]
    run_dir = output_dir if output_dir else mode
    results: list[dict] = []

    for q in questions:
        qid = q["qid"]
        question_text = q["question"]
        prompt = build_v2_prompt(task, mode, question_text=question_text)
        cmd = build_command(mode, model, prompt)
        file_id = f"{task_id}_{qid}"
        output_path = RUNS_DIR / run_dir / f"{file_id}.json"

        if dry_run:
            print(f"[DRY RUN] {file_id}")
            print(f"  Command: claude -p --model {model} ... [{len(prompt)} chars]")
            print(f"  Output: {output_path}")
            print()
            continue

        print(f"[RUN] {file_id} (mode={mode}, model={model})")
        stdout, stderr, returncode, duration = _run_claude_session(cmd, timeout)

        if returncode == -1 and "TIMEOUT" in stderr:
            print(f"  TIMEOUT: {file_id} after {timeout}s")

        parsed, parse_success = parse_structured_response(stdout)

        output = {
            "task_id": task_id,
            "qid": qid,
            "mode": mode,
            "prompt": prompt,
            "response": stdout,
            "stderr": stderr,
            "returncode": returncode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": duration,
            "parsed": parsed,
            "parse_success": parse_success,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)

        # Write readable .md
        md_path = output_path.with_suffix(".md")
        result_text = ""
        if stdout:
            try:
                resp_json = json.loads(stdout)
                result_text = resp_json.get("result", "")
            except (json.JSONDecodeError, TypeError):
                result_text = stdout
        with open(md_path, "w") as f:
            f.write(result_text)

        status = "OK" if returncode == 0 else f"ERR({returncode})"
        print(f"  {status} in {duration}s -> {md_path}")
        results.append(output)

    return results


def run_v2_single_task(
    task: dict,
    mode: str,
    model: str,
    timeout: int,
    dry_run: bool,
    output_dir: str | None = None,
) -> dict | None:
    """Run a v2 single-task format (one session, with JSON parsing)."""
    task_id = task["id"]
    prompt = build_v2_prompt(task, mode)
    cmd = build_command(mode, model, prompt)
    run_dir = output_dir if output_dir else mode
    output_path = RUNS_DIR / run_dir / f"{task_id}.json"

    if dry_run:
        print(f"[DRY RUN] {task_id}")
        print(f"  Command: claude -p --model {model} ... [{len(prompt)} chars]")
        print(f"  Output: {output_path}")
        print()
        return None

    print(f"[RUN] {task_id} (mode={mode}, model={model})")
    stdout, stderr, returncode, duration = _run_claude_session(cmd, timeout)

    if returncode == -1 and "TIMEOUT" in stderr:
        print(f"  TIMEOUT: {task_id} after {timeout}s")

    parsed, parse_success = parse_structured_response(stdout)

    output = {
        "task_id": task_id,
        "mode": mode,
        "prompt": prompt,
        "response": stdout,
        "stderr": stderr,
        "returncode": returncode,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": duration,
        "parsed": parsed,
        "parse_success": parse_success,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    md_path = output_path.with_suffix(".md")
    result_text = ""
    if stdout:
        try:
            resp_json = json.loads(stdout)
            result_text = resp_json.get("result", "")
        except (json.JSONDecodeError, TypeError):
            result_text = stdout
    with open(md_path, "w") as f:
        f.write(result_text)

    status = "OK" if returncode == 0 else f"ERR({returncode})"
    print(f"  {status} in {duration}s -> {md_path}")
    return output


def run_v2_task(
    task_path: Path,
    mode: str,
    model: str,
    timeout: int,
    dry_run: bool,
    output_dir: str | None = None,
) -> list[dict]:
    """Dispatch a v2 task — batch or single-task format.

    Returns a list of result dicts (one per question for batch, one-element
    list for single-task).
    """
    task = load_task(task_path)

    if "questions" in task:
        return run_v2_batch_task(task, mode, model, timeout, dry_run, output_dir)
    else:
        result = run_v2_single_task(task, mode, model, timeout, dry_run, output_dir)
        return [result] if result else []


def write_parse_report(results: list[dict], output_dir: str) -> None:
    """Write ``_parse_report.json`` summarising parse success/failure rates.

    Only considers v2 results (those with a ``parse_success`` key).
    """
    v2_results = [r for r in results if r is not None and "parse_success" in r]
    if not v2_results:
        return

    total = len(v2_results)
    failed_ids = []
    for r in v2_results:
        if not r["parse_success"]:
            # Use qid if present (batch), otherwise task_id
            failed_ids.append(r.get("qid", r["task_id"]))

    parsed = total - len(failed_ids)
    failure_rate = round(len(failed_ids) / total, 4) if total > 0 else 0.0

    report = {
        "total": total,
        "parsed": parsed,
        "failed": len(failed_ids),
        "failure_rate": failure_rate,
        "failed_ids": failed_ids,
    }

    report_path = RUNS_DIR / output_dir / "_parse_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n[PARSE REPORT] {report_path}")
    print(f"  Total: {total}, Parsed: {parsed}, Failed: {len(failed_ids)}")
    if failure_rate > 0.1:
        print(
            f"  WARNING: Parse failure rate {failure_rate:.1%} exceeds 10% threshold!",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# v1 runner (unchanged)
# ---------------------------------------------------------------------------

def run_single_task(
    task_path: Path,
    mode: str,
    model: str,
    timeout: int,
    dry_run: bool,
    output_dir: str | None = None,
) -> dict | None:
    """Run a single v1 benchmark task and return the result dict."""
    task = load_task(task_path)
    task_id = task["id"]
    prompt = build_prompt(task, mode)
    cmd = build_command(mode, model, prompt)

    run_dir = output_dir if output_dir else mode
    output_path = RUNS_DIR / run_dir / f"{task_id}.json"

    if dry_run:
        print(f"[DRY RUN] {task_id}")
        print(f"  Command: claude -p --model {model} ... [{len(prompt)} chars]")
        print(f"  Output: {output_path}")
        print()
        return None

    print(f"[RUN] {task_id} (mode={mode}, model={model})")
    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration = time.monotonic() - start

        output = {
            "task_id": task_id,
            "mode": mode,
            "prompt": prompt,
            "response": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(duration, 2),
        }
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start
        output = {
            "task_id": task_id,
            "mode": mode,
            "prompt": prompt,
            "response": "",
            "stderr": f"TIMEOUT after {timeout}s",
            "returncode": -1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(duration, 2),
        }
        print(f"  TIMEOUT: {task_id} after {timeout}s")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    # Write a readable .md file with just the response text
    md_path = output_path.with_suffix(".md")
    result_text = ""
    if output["response"]:
        try:
            resp_json = json.loads(output["response"])
            result_text = resp_json.get("result", "")
        except (json.JSONDecodeError, TypeError):
            result_text = output["response"]
    with open(md_path, "w") as f:
        f.write(result_text)

    status = "OK" if output["returncode"] == 0 else f"ERR({output['returncode']})"
    print(f"  {status} in {output['duration_seconds']}s -> {md_path}")
    return output


# ---------------------------------------------------------------------------
# Version dispatch
# ---------------------------------------------------------------------------

def dispatch_task(
    task_path: Path,
    mode: str,
    model: str,
    timeout: int,
    dry_run: bool,
    output_dir: str | None = None,
) -> list[dict]:
    """Route to v1 or v2 handler based on the task's ``version`` field.

    Returns a list of result dicts.
    """
    task = load_task(task_path)

    if task.get("version") == 2:
        return run_v2_task(task_path, mode, model, timeout, dry_run, output_dir)
    else:
        result = run_single_task(
            task_path, mode, model, timeout, dry_run, output_dir
        )
        return [result] if result else []


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run KYL benchmark tasks via the claude CLI."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--task", type=Path, help="Path to a single YAML task file")
    group.add_argument(
        "--all", action="store_true", help="Run all tasks under benchmarks/tasks/"
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["baseline", "kyl"],
        help="Run mode: baseline or kyl",
    )
    parser.add_argument(
        "--model", default="sonnet", help="Model to use (default: sonnet)"
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="Number of concurrent sessions (default: 1)",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=2,
        help="Seconds between launches (default: 2)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Seconds per session (default: 600)",
    )
    parser.add_argument(
        "--output-dir",
        help="Override output directory name under runs/ (default: same as --mode)",
    )
    parser.add_argument(
        "--dimension",
        choices=V2_DIMENSIONS,
        default=None,
        help="Only run v2 tasks matching this dimension (used with --all)",
    )
    args = parser.parse_args()

    if args.all:
        task_paths = find_all_tasks(dimension=args.dimension)
        if not task_paths:
            label = f" for dimension={args.dimension}" if args.dimension else ""
            print(
                f"No .yaml files found under {TASKS_DIR}{label}",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"Found {len(task_paths)} task(s)")
    else:
        if args.dimension:
            print(
                "Warning: --dimension is ignored when using --task (only applies to --all)",
                file=sys.stderr,
            )
        task_path = args.task.resolve()
        if not task_path.exists():
            print(f"Task file not found: {task_path}", file=sys.stderr)
            sys.exit(1)
        task_paths = [task_path]

    run_dir = args.output_dir if args.output_dir else args.mode
    all_results: list[dict] = []

    if args.parallel <= 1:
        for i, tp in enumerate(task_paths):
            if i > 0 and not args.dry_run:
                time.sleep(args.delay)
            results = dispatch_task(
                tp, args.mode, args.model, args.timeout, args.dry_run, args.output_dir
            )
            all_results.extend(results)
    else:
        with ThreadPoolExecutor(max_workers=args.parallel) as executor:
            futures = {}
            for i, tp in enumerate(task_paths):
                if i > 0 and not args.dry_run:
                    time.sleep(args.delay)
                future = executor.submit(
                    dispatch_task,
                    tp, args.mode, args.model, args.timeout, args.dry_run, args.output_dir,
                )
                futures[future] = tp

            for future in as_completed(futures):
                tp = futures[future]
                try:
                    results = future.result()
                    all_results.extend(results)
                except Exception as e:
                    print(f"Error running {tp}: {e}", file=sys.stderr)

    # Write parse report for any v2 results
    if not args.dry_run:
        write_parse_report(all_results, run_dir)

    print("\nDone.")


if __name__ == "__main__":
    main()
