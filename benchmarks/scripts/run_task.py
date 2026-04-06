#!/usr/bin/env python3
"""Runner script that executes KYL benchmark tasks via the claude CLI."""

import argparse
import json
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


def load_task(task_path: Path) -> dict:
    """Load a YAML task file and return its contents."""
    with open(task_path) as f:
        return yaml.safe_load(f)


def find_all_tasks() -> list[Path]:
    """Find all YAML task files under benchmarks/tasks/."""
    return sorted(TASKS_DIR.rglob("*.yaml"))


def build_command(mode: str, model: str) -> list[str]:
    """Build the claude CLI command for the given mode."""
    cmd = ["claude", "-p", "--model", model, "--output-format", "json"]
    if mode == "baseline":
        cmd.append("--bare")
    elif mode == "kyl":
        plugin_dir = PROJECT_ROOT / "plugins" / "metacognition"
        cmd.extend(["--plugin-dir", str(plugin_dir)])
    return cmd


def build_prompt(task: dict, mode: str) -> str:
    """Build the full prompt for the given task and mode."""
    prompt = task["prompt"]
    if mode == "kyl" and task.get("treatment_prefix"):
        prompt = task["treatment_prefix"] + "\n\n" + prompt
    return prompt


def run_single_task(
    task_path: Path,
    mode: str,
    model: str,
    timeout: int,
    dry_run: bool,
) -> dict | None:
    """Run a single benchmark task and return the result dict."""
    task = load_task(task_path)
    task_id = task["id"]
    prompt = build_prompt(task, mode)
    cmd = build_command(mode, model)

    output_path = RUNS_DIR / mode / f"{task_id}.json"

    if dry_run:
        print(f"[DRY RUN] {task_id}")
        print(f"  Command: {' '.join(cmd)}")
        print(f"  Prompt length: {len(prompt)} chars")
        print(f"  Output: {output_path}")
        print()
        return None

    print(f"[RUN] {task_id} (mode={mode}, model={model})")
    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            input=prompt,
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

    status = "OK" if output["returncode"] == 0 else f"ERR({output['returncode']})"
    print(f"  {status} in {output['duration_seconds']}s -> {output_path}")
    return output


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
        default=300,
        help="Seconds per session (default: 300)",
    )
    args = parser.parse_args()

    if args.all:
        task_paths = find_all_tasks()
        if not task_paths:
            print(f"No .yaml files found under {TASKS_DIR}", file=sys.stderr)
            sys.exit(1)
        print(f"Found {len(task_paths)} task(s)")
    else:
        task_path = args.task.resolve()
        if not task_path.exists():
            print(f"Task file not found: {task_path}", file=sys.stderr)
            sys.exit(1)
        task_paths = [task_path]

    if args.parallel <= 1:
        for i, tp in enumerate(task_paths):
            if i > 0 and not args.dry_run:
                time.sleep(args.delay)
            run_single_task(tp, args.mode, args.model, args.timeout, args.dry_run)
    else:
        with ThreadPoolExecutor(max_workers=args.parallel) as executor:
            futures = {}
            for i, tp in enumerate(task_paths):
                if i > 0 and not args.dry_run:
                    time.sleep(args.delay)
                future = executor.submit(
                    run_single_task, tp, args.mode, args.model, args.timeout, args.dry_run
                )
                futures[future] = tp

            for future in as_completed(futures):
                tp = futures[future]
                try:
                    future.result()
                except Exception as e:
                    print(f"Error running {tp}: {e}", file=sys.stderr)

    print("\nDone.")


if __name__ == "__main__":
    main()
