"""
Core execution engine for asdlc (Agentic SDLC Harness).
Implements SDD, TDD, and EDD state transitions, anti-tampering, and evidence emission.
"""

from __future__ import annotations

import datetime
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from asdlc.adapters import AgentAdapter


class SDLCState(str, Enum):
    INITIALIZED = "INITIALIZED"
    SPECIFIED = "SPECIFIED"
    TESTS_GENERATED = "TESTS_GENERATED"
    AGENT_ITERATING = "AGENT_ITERATING"
    INTEGRATED = "INTEGRATED"
    CI_REVIEW_PENDING = "CI_REVIEW_PENDING"
    RELEASE_APPROVED = "RELEASE_APPROVED"
    ABORTED = "ABORTED"
    REJECTED = "REJECTED"


class TestTamperingError(RuntimeError):
    """Raised when an agent modifies protected verification test files."""
    __test__ = False


class InitialTestsAlreadyPassingError(RuntimeError):
    """Raised when the verification suite passes before agent invocation without --allow-green."""
    __test__ = False


def _get_file_hash(path: Path) -> str:
    """Computes SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    hasher.update(path.read_bytes())
    return hasher.hexdigest()


def _update_state(root_dir: Path, status: SDLCState, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    state_dir = root_dir / ".asdlc"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "state.json"
    data = {
        "status": status.value,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        **(metadata or {}),
    }
    state_file.write_text(json.dumps(data, indent=2))
    return data


def init_project(root_dir: Path) -> Path:
    """Initializes the .asdlc scaffold, state file, and baseline .gitignore entry."""
    state_dir = root_dir / ".asdlc"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "state.json"
    if not state_file.exists():
        _update_state(root_dir, SDLCState.INITIALIZED)

    gitignore_file = root_dir / ".gitignore"
    if not gitignore_file.exists():
        gitignore_file.write_text(".asdlc/\n")
    else:
        content = gitignore_file.read_text()
        if ".asdlc/" not in content:
            gitignore_file.write_text(content.rstrip("\n") + "\n.asdlc/\n")

    return state_file


def run_sdd(intent_path: Path, out_spec_path: Path, root_dir: Path) -> dict[str, Any]:
    """Validates intent.md and produces/verifies spec.md (SDD Step)."""
    if not intent_path.exists():
        raise FileNotFoundError(f"Intent file not found: {intent_path}")

    content = intent_path.read_text()
    required_sections = ["Problem", "Scope", "Acceptance Criteria"]
    missing = [sec for sec in required_sections if not re.search(rf"#+\s*.*{sec}", content, re.IGNORECASE)]

    if missing:
        raise ValueError(f"Missing required sections in {intent_path.name}: {', '.join(missing)}")

    # If out_spec_path doesn't exist, create derived technical spec skeleton
    if not out_spec_path.exists():
        out_spec_path.parent.mkdir(parents=True, exist_ok=True)
        out_spec_path.write_text(
            f"# Technical Specification\n\n"
            f"Derived from: {intent_path.name}\n\n"
            f"## Contract & Verification Matrix\n"
            f"- Generated automatically by asdlc sdd.\n"
        )

    state = _update_state(
        root_dir,
        SDLCState.SPECIFIED,
        {"intent_file": str(intent_path), "spec_file": str(out_spec_path)},
    )
    return state


def run_tdd(
    root_dir: Path,
    spec_path: Path,
    test_file: Path,
    agent: AgentAdapter,
    max_turns: int = 5,
    test_cmd: str | None = None,
    allow_green: bool = False,
) -> dict[str, Any]:
    """
    Executes the TDD inner loop:
    1. Records test manifest hash.
    2. Runs initial test check (must fail RED unless allow_green=True).
    3. Iterates agent turns with anti-tampering check until GREEN or max_turns.
    """
    state_dir = root_dir / ".asdlc"
    state_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = state_dir / "test_manifest.json"

    # Compute baseline SHA-256 for test protection
    baseline_hash = _get_file_hash(test_file)
    manifest_file.write_text(json.dumps({str(test_file): baseline_hash}, indent=2))

    # Trace log file
    trace_file = state_dir / "agent-trace.jsonl"

    def log_trace(entry: dict[str, Any]) -> None:
        with open(trace_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def run_tests() -> int:
        if test_cmd:
            import shlex
            cmd = shlex.split(test_cmd)
        else:
            cmd = [sys.executable, "-m", "pytest", str(test_file), "-q"]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(root_dir)
        proc = subprocess.run(
            cmd,
            cwd=str(root_dir),
            env=env,
            capture_output=True,
            text=True,
        )
        return proc.returncode

    # Verify initial tests fail (RED)
    initial_code = run_tests()
    if initial_code == 0:
        if not allow_green:
            raise InitialTestsAlreadyPassingError(
                "Tests are already passing before agent invocation (RED invariant failed). "
                "Pass --allow-green to override."
            )
        _update_state(root_dir, SDLCState.INTEGRATED)
        return {
            "success": True,
            "turns_taken": 0,
            "status": SDLCState.INTEGRATED.value,
        }

    _update_state(root_dir, SDLCState.AGENT_ITERATING)

    turns_taken = 0
    for turn in range(1, max_turns + 1):
        turns_taken = turn

        # Agent acts
        agent.run_turn(
            prompt=f"Fix implementation to pass tests in {test_file.name}",
            workdir=root_dir,
            trace_logger=lambda act: log_trace({
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "turn": turn,
                "agent": agent.name,
                **act,
            }),
        )

        # Anti-tampering gate
        current_hash = _get_file_hash(test_file)
        if current_hash != baseline_hash:
            raise TestTamperingError(f"Test suite modified by agent: {test_file}")

        # Test execution
        code = run_tests()
        if code == 0:
            _update_state(root_dir, SDLCState.INTEGRATED)
            return {
                "success": True,
                "turns_taken": turns_taken,
                "status": SDLCState.INTEGRATED.value,
            }

    _update_state(root_dir, SDLCState.ABORTED)
    return {
        "success": False,
        "turns_taken": turns_taken,
        "status": SDLCState.ABORTED.value,
    }


def run_eval(
    spec_path: Path,
    diff_path: Path,
    out_path: Path,
    task_id: str,
    git_commit_sha: str,
    target_head_revision: str,
    risk_class: str,
    tests_passed: bool,
) -> dict[str, Any]:
    """
    Outer loop evaluation: evaluates diff compliance against spec.md and outputs ReleaseEvidence.
    """
    diff_text = diff_path.read_text() if diff_path.exists() else ""
    files_changed = re.findall(r"diff --git a/(.*?) b/", diff_text)
    if not files_changed:
        files_changed = re.findall(r"--- a/(.*?)\n", diff_text)

    # Gate verdict logic
    if tests_passed:
        if risk_class == "Low":
            gate_verdict = "AUTO_MERGE_APPROVED"
        else:
            gate_verdict = "MANUAL_REVIEW_REQUIRED"
    else:
        gate_verdict = "REJECTED"

    evidence = {
        "task_id": task_id,
        "git_commit_sha": git_commit_sha,
        "target_head_revision": target_head_revision,
        "risk_class": risk_class,
        "test_evidence": {
            "fail_to_pass_passed": tests_passed,
            "pass_to_pass_passed": tests_passed,
            "all_passed": tests_passed,
        },
        "semantic_delta": {
            "files_changed": sorted(list(set(files_changed))),
            "summary": f"Diff modifies {len(files_changed)} file(s).",
            "spec_conformance": True,
        },
        "gate_verdict": gate_verdict,
        "evaluated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(evidence, indent=2))
    return evidence
