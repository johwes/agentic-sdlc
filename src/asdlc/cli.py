"""
Command-line interface for asdlc (Agentic SDLC).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from asdlc.core import (
    init_project,
    run_sdd,
    run_tdd,
    run_eval,
    TestTamperingError,
    InitialTestsAlreadyPassingError,
)
from asdlc.adapters import get_adapter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="asdlc",
        description="Nested-Loop Agentic SDLC Reference Harness (SDD x TDD x EDD)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # asdlc init
    p_init = subparsers.add_parser("init", help="Initialize asdlc project state")
    p_init.add_argument("--dir", default=".", help="Root project directory")

    # asdlc sdd
    p_sdd = subparsers.add_parser("sdd", help="Run Specification-Driven Development intake")
    p_sdd.add_argument("--intent", default="intent.md", help="Path to intent.md")
    p_sdd.add_argument("--out", default="spec.md", help="Path for output spec.md")

    # asdlc tdd
    p_tdd = subparsers.add_parser("tdd", help="Run Test-Driven Development inner loop")
    p_tdd.add_argument("--spec", default="spec.md", help="Path to spec.md")
    p_tdd.add_argument("--test-file", default="tests/test_spec.py", help="Test file for verification")
    p_tdd.add_argument("--test-cmd", default=None, help="Deterministic test command")
    p_tdd.add_argument("--allow-green", action="store_true", help="Allow execution if tests already pass initially")
    p_tdd.add_argument("--agent", default="mock", help="Agent adapter (mock, opencode, claude, antigravity)")
    p_tdd.add_argument("--max-turns", type=int, default=5, help="Maximum agent iteration turns")
    p_tdd.add_argument("--timeout", type=int, default=None, help="Subprocess timeout in seconds")

    # asdlc run
    p_run = subparsers.add_parser("run", help="Run end-to-end inner loop (init -> sdd -> tdd)")
    p_run.add_argument("--intent", default="intent.md", help="Path to intent.md")
    p_run.add_argument("--test-cmd", default=None, help="Deterministic test command")
    p_run.add_argument("--allow-green", action="store_true", help="Allow execution if tests already pass initially")
    p_run.add_argument("--agent", default="mock", help="Agent adapter")
    p_run.add_argument("--max-turns", type=int, default=5, help="Maximum agent turns")
    p_run.add_argument("--timeout", type=int, default=None, help="Subprocess timeout in seconds")

    # asdlc eval
    p_eval = subparsers.add_parser("eval", help="Run outer-loop CI evaluation judge")
    p_eval.add_argument("--spec", default="spec.md", help="Path to spec.md")
    p_eval.add_argument("--diff", required=True, help="Path to git diff file")
    p_eval.add_argument("--out", default="release-evidence.json", help="Path for release evidence")
    p_eval.add_argument("--task-id", default="ASDLC-001", help="Task ID")
    p_eval.add_argument("--sha", default="HEAD", help="Commit SHA")
    p_eval.add_argument("--target-rev", default="main", help="Target head revision")
    p_eval.add_argument("--risk-class", default="Low", choices=["Low", "Medium", "High", "Critical"])
    p_eval.add_argument("--tests-passed", action="store_true", help="Flag if test suite passed")
    p_eval.add_argument("--allow-test-changes", action="store_true", help="Permit modifications to protected tests/ directory")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cwd = Path.cwd()

    try:
        if args.command == "init":
            target_dir = Path(args.dir).resolve()
            init_project(target_dir)
            print(f"✓ Initialized asdlc project in {target_dir}")
            return 0

        elif args.command == "sdd":
            intent_file = Path(args.intent).resolve()
            spec_file = Path(args.out).resolve()
            res = run_sdd(intent_file, spec_file, root_dir=cwd)
            print(f"✓ SDD complete: {res['status']} -> {spec_file.name}")
            return 0

        elif args.command == "tdd":
            spec_file = Path(args.spec).resolve()
            test_file = Path(args.test_file).resolve()
            adapter = get_adapter(args.agent)
            if getattr(args, "timeout", None) and hasattr(adapter, "timeout_seconds"):
                adapter.timeout_seconds = args.timeout
            res = run_tdd(
                root_dir=cwd,
                spec_path=spec_file,
                test_file=test_file,
                agent=adapter,
                max_turns=args.max_turns,
                test_cmd=args.test_cmd,
                allow_green=args.allow_green,
            )
            if res["success"]:
                print(f"✓ TDD GREEN: Iteration succeeded in {res['turns_taken']} turn(s).")
                return 0
            else:
                print(f"✗ TDD RED: Max turns ({args.max_turns}) reached without achieving green.")
                return 1

        elif args.command == "run":
            init_project(cwd)
            intent_file = Path(args.intent).resolve()
            spec_file = cwd / "spec.md"
            run_sdd(intent_file, spec_file, root_dir=cwd)
            test_file = cwd / "tests" / "test_spec.py"
            adapter = get_adapter(args.agent)
            if getattr(args, "timeout", None) and hasattr(adapter, "timeout_seconds"):
                adapter.timeout_seconds = args.timeout
            res = run_tdd(
                root_dir=cwd,
                spec_path=spec_file,
                test_file=test_file,
                agent=adapter,
                max_turns=args.max_turns,
                test_cmd=args.test_cmd,
                allow_green=args.allow_green,
            )
            return 0 if res["success"] else 1

        elif args.command == "eval":
            spec_file = Path(args.spec).resolve()
            diff_file = Path(args.diff).resolve()
            out_file = Path(args.out).resolve()
            evidence = run_eval(
                spec_path=spec_file,
                diff_path=diff_file,
                out_path=out_file,
                task_id=args.task_id,
                git_commit_sha=args.sha,
                target_head_revision=args.target_rev,
                risk_class=args.risk_class,
                tests_passed=args.tests_passed,
                allow_test_changes=args.allow_test_changes,
            )
            print(f"✓ Evaluated outer loop. Verdict: {evidence['gate_verdict']}")
            print(f"  Evidence written to: {out_file}")
            return 0

    except TestTamperingError as e:
        print(f"FATAL SECURITY VIOLATION: {e}", file=sys.stderr)
        return 2
    except InitialTestsAlreadyPassingError as e:
        print(f"RED INVARIANT FAILURE: {e}", file=sys.stderr)
        return 3
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
