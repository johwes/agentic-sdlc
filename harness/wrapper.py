#!/usr/bin/env python3
"""Cell harness command (skeleton).

Invoked explicitly per attempt via `openshell sandbox exec` (see
specs/04-worker-cell.md) — never PID 1. One invocation = one attempt = one
fresh agent process (the Ralph freshness unit).

Usage:
    cell-harness --attempt N --frame /sandbox/.task/current_task.json \
        --receipt /sandbox/.task/task_receipt.json

Stage order per invocation:

1. Load --frame (read-only).
2. Dispatch the agent CLI (opencode / claude) with the contract prompt.
3. Capture stdout/stderr; collect the agent's summary trailer.
4. Run forbidden_paths diff assertion -> BLOCKED / HALT:BLOCKED (no retry).
5. Run tactile_command (timeout, 50-line tail) -> nonzero means FAILED.
6. Collect git rev-parse HEAD + git diff --name-only + token telemetry
   (nullable, best-effort).
7. Serialize schema-valid task_receipt.json to --receipt.

Exit code mirrors the receipt outcome for `sandbox exec` propagation.

Auth note: OpenCode reads OPENCODE_API_KEY from env (provider-injected,
placeholder-masked) natively — no auth.json seeding required.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path, PurePath


# Exit codes mirror receipt outcome for `sandbox exec` propagation.
EXIT_SUCCESS = 0
EXIT_FAILED = 1
EXIT_BLOCKED = 2

REQUIRED_FIELDS = [
    "task_id",
    "title",
    "acceptance_criteria",
    "target_branch",
    "allowed_paths",
    "forbidden_paths",
    "sensor_context",
    "attempt",
    "max_attempts",
    "tactile_command",
]

# Verification path exception per specs/07-contracts.md
# These paths are part of the clean-commit set even if outside allowed_paths
# and must not be treated as forbidden when they appear in the diff solely as
# wrapper outputs (e.g. receipt write). Current_task.json is read-only.
VERIFICATION_EXEMPT = {
    "PROGRESS.md",
    "sandbox/PROGRESS.md",
    "/sandbox/PROGRESS.md",
    ".task/task_receipt.json",
    "sandbox/.task/task_receipt.json",
    "/sandbox/.task/task_receipt.json",
    "task_receipt.json",
}


def _load_frame(frame_path: Path) -> tuple[dict | None, str | None]:
    """Load and validate current_task.json. Returns (frame, error)."""
    try:
        raw = frame_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, f"frame not found: {frame_path}"
    except OSError as e:
        return None, f"frame read error: {e}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"frame JSON invalid: {e}"
    if not isinstance(data, dict):
        return None, "frame JSON must be an object"
    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        return None, f"frame missing required fields: {', '.join(missing)}"
    # Type sanity for core fields (lightweight, no external schema lib per stdlib-only rule)
    if not isinstance(data.get("forbidden_paths"), list):
        return None, "frame forbidden_paths must be a list"
    if not isinstance(data.get("allowed_paths"), list):
        return None, "frame allowed_paths must be a list"
    return data, None


def _get_commit_sha() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0:
            sha = r.stdout.strip()
            if sha:
                return sha
    except Exception:
        pass
    return "unknown"


def _get_files_changed() -> list[str]:
    """Collect changed files vs HEAD: staged, unstaged, and untracked."""
    files: set[str] = set()
    # Tracked changes (staged + unstaged) vs HEAD
    for cmd in (
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "diff", "--name-only"],
        ["git", "diff", "--cached", "--name-only"],
    ):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                for line in r.stdout.splitlines():
                    line = line.strip()
                    if line:
                        files.add(line)
        except Exception:
            continue
    # Untracked files
    try:
        r = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            for line in r.stdout.splitlines():
                line = line.strip()
                if line:
                    files.add(line)
    except Exception:
        pass
    # Fallback: git status --porcelain if above produced nothing but repo is dirty
    if not files:
        try:
            r = subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                for line in r.stdout.splitlines():
                    # format: " M file" or "?? file" or "A  file"
                    parts = line.strip().split()
                    if parts:
                        # last token is file path (handles renames "R  old -> new" we take new)
                        f = parts[-1]
                        if f != "->":
                            # for renames, last part is new path
                            files.add(f)
        except Exception:
            pass
    return sorted(files)


def _is_exempt(file_path: str, receipt_path: Path | None) -> bool:
    # Direct exemption set
    if file_path in VERIFICATION_EXEMPT:
        return True
    # Receipt file itself (absolute or repo-relative) is exempt
    if receipt_path is not None:
        try:
            # compare both absolute and relative forms
            rp_str = str(receipt_path)
            if file_path == rp_str:
                return True
            # if receipt_path is absolute, compare basename-relative
            if Path(file_path).name == Path(rp_str).name and "task_receipt.json" in file_path:
                return True
        except Exception:
            pass
    # PROGRESS.md anywhere is exempt (PoC shortcut per 07-contracts.md)
    if file_path == "PROGRESS.md" or file_path.endswith("/PROGRESS.md"):
        return True
    if file_path == ".task/task_receipt.json" or file_path.endswith(".task/task_receipt.json"):
        return True
    return False


def _matches_forbidden(file_path: str, pattern: str) -> bool:
    """Glob match supporting **, * and ? via fnmatch + PurePath.match + prefix rule."""
    # Normalize: strip leading ./ and /
    fp = file_path.lstrip("./")
    pat = pattern.lstrip("./")
    # Direct fnmatch
    if fnmatch.fnmatch(fp, pat):
        return True
    # PurePath.match handles ** correctly
    try:
        if PurePath(fp).match(pat):
            return True
    except Exception:
        pass
    # Also try Path.match with Posix
    try:
        if Path(fp).match(pat):
            return True
    except Exception:
        pass
    # Explicit /** prefix rule: pattern "a/**" matches "a/file" and "a"
    if pat.endswith("/**"):
        prefix = pat[:-3]
        if fp == prefix or fp.startswith(prefix + "/"):
            return True
    # Pattern without slash should match basename as well
    if "/" not in pat:
        if fnmatch.fnmatch(Path(fp).name, pat):
            return True
    return False


def _check_forbidden(files_changed: list[str], forbidden_paths: list[str], receipt_path: Path | None) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    for f in files_changed:
        if _is_exempt(f, receipt_path):
            continue
        for pat in forbidden_paths:
            if _matches_forbidden(f, pat):
                violations.append((f, pat))
                break
    return violations


def _write_receipt(
    receipt_path: Path,
    *,
    task_id: str,
    status: str,
    exit_promise: str,
    commit_sha: str,
    files_changed: list[str],
    tactile_execution: dict,
    agent_summary: str,
    token_metrics: dict,
) -> None:
    receipt = {
        "task_id": task_id,
        "status": status,
        "exit_promise": exit_promise,
        "commit_sha": commit_sha,
        "files_changed": files_changed,
        "tactile_execution": tactile_execution,
        "agent_summary": agent_summary,
        "token_metrics": token_metrics,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    # Write atomically via tmp + rename
    tmp = receipt_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    tmp.replace(receipt_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Cell harness stage 1: frame load + forbidden_paths -> BLOCKED")
    parser.add_argument("--attempt", required=True, help="Attempt index (1-indexed)")
    parser.add_argument("--frame", required=True, help="Path to current_task.json (read-only)")
    parser.add_argument("--receipt", required=True, help="Path to write task_receipt.json")
    args = parser.parse_args()

    frame_path = Path(args.frame)
    receipt_path = Path(args.receipt)

    # 1. Load frame (read-only)
    frame, err = _load_frame(frame_path)
    if err is not None or frame is None:
        # Frame load failure is BLOCKED / HALT:BLOCKED per 07 contracts (system failure)
        commit_sha = _get_commit_sha()
        files_changed: list[str] = _get_files_changed()
        task_id = "unknown"
        # Try to extract task_id from raw file if possible
        try:
            if frame_path.exists():
                raw = json.loads(frame_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and isinstance(raw.get("task_id"), str):
                    task_id = raw["task_id"]
        except Exception:
            pass
        _write_receipt(
            receipt_path,
            task_id=task_id,
            status="BLOCKED",
            exit_promise="HALT:BLOCKED",
            commit_sha=commit_sha,
            files_changed=files_changed,
            tactile_execution={"command_run": "", "exit_code": 0, "summary_output": ""},
            agent_summary=f"BLOCKED: frame load failed: {err}",
            token_metrics={"input_tokens": None, "output_tokens": None, "cost": None},
        )
        print(f"BLOCKED: frame load failed: {err}", file=sys.stderr)
        return EXIT_BLOCKED

    task_id = str(frame["task_id"])
    forbidden_paths = list(frame.get("forbidden_paths") or [])
    tactile_command = str(frame.get("tactile_command") or "")

    # Collect git state
    commit_sha = _get_commit_sha()
    files_changed = _get_files_changed()

    # 4. Forbidden_paths diff assertion -> BLOCKED / HALT:BLOCKED (no retry)
    violations = _check_forbidden(files_changed, forbidden_paths, receipt_path)
    if violations:
        detail = ", ".join(f"{f} matched {pat}" for f, pat in violations)
        summary = f"BLOCKED: forbidden_paths violation: {detail}"
        print(summary, file=sys.stderr)
        _write_receipt(
            receipt_path,
            task_id=task_id,
            status="BLOCKED",
            exit_promise="HALT:BLOCKED",
            commit_sha=commit_sha,
            files_changed=files_changed,
            tactile_execution={"command_run": tactile_command, "exit_code": 0, "summary_output": ""},
            agent_summary=summary,
            token_metrics={"input_tokens": None, "output_tokens": None, "cost": None},
        )
        return EXIT_BLOCKED

    # No LLM dispatch yet per stage 1. If clean, emit a provisional receipt so the
    # envelope is schema-valid. Future stages will replace this with tactile/AST
    # grounded results; stage 1 only guarantees that a clean diff is not BLOCKED.
    summary = f"stage 1: frame loaded (task {task_id} attempt {args.attempt}), no forbidden_paths violation; LLM dispatch not yet wired"
    print(summary)
    _write_receipt(
        receipt_path,
        task_id=task_id,
        status="SUCCESS",
        exit_promise="COMPLETE",
        commit_sha=commit_sha,
        files_changed=files_changed,
        tactile_execution={"command_run": tactile_command, "exit_code": 0, "summary_output": ""},
        agent_summary=summary,
        token_metrics={"input_tokens": None, "output_tokens": None, "cost": None},
    )
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
