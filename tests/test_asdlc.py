"""
Deterministic verification test suite for asdlc (Agentic SDLC Harness).
Asserts compliance with technical specification: spec.md.
"""

import json
from pathlib import Path
import pytest

from asdlc.core import (
    init_project,
    run_sdd,
    run_tdd,
    run_eval,
    TestTamperingError,
    InitialTestsAlreadyPassingError,
    SDLCState,
)
from asdlc.adapters import MockAgentAdapter


def test_init_creates_scaffold(tmp_path: Path):
    """
    Scenario: Run asdlc init on clean temp dir.
    Expected: Creates .asdlc/ directory, state.json with status INITIALIZED.
    """
    state_file = init_project(tmp_path)
    assert (tmp_path / ".asdlc").is_dir()
    assert state_file.is_file()

    with open(state_file, "r") as f:
        state = json.load(f)
    assert state.get("status") == SDLCState.INITIALIZED.value

    # Verify .gitignore entry
    gitignore_file = tmp_path / ".gitignore"
    assert gitignore_file.is_file()
    assert ".asdlc/" in gitignore_file.read_text()


def test_sdd_validates_intent(tmp_path: Path):
    """
    Scenario: Run asdlc sdd with valid and invalid intent.md.
    Expected: Passes on valid intent; raises ValueError if required sections are missing.
    """
    init_project(tmp_path)

    # Missing required sections
    bad_intent = tmp_path / "bad_intent.md"
    bad_intent.write_text("# Just a title without required sections")
    with pytest.raises(ValueError, match="Missing required sections"):
        run_sdd(intent_path=bad_intent, out_spec_path=tmp_path / "spec.md", root_dir=tmp_path)

    # Valid intent
    good_intent = tmp_path / "good_intent.md"
    good_intent.write_text(
        "# Intent: Test Feature\n\n"
        "## Problem Statement\nNeed a test feature.\n\n"
        "## Scope\nBounded to unit tests.\n\n"
        "## Acceptance Criteria\n- [ ] It works\n"
    )
    spec_out = tmp_path / "spec.md"
    result = run_sdd(intent_path=good_intent, out_spec_path=spec_out, root_dir=tmp_path)
    assert spec_out.is_file()
    assert result.get("status") == SDLCState.SPECIFIED.value


def test_tdd_halts_on_green(tmp_path: Path):
    """
    Scenario: Run asdlc tdd with MockAgentAdapter.
    Expected: Starts RED -> Agent modifies code on turn 1 -> achieves GREEN -> halts exit 0.
    """
    init_project(tmp_path)

    # Setup initial RED state in dummy workspace
    src_dir = tmp_path / "src"
    tests_dir = tmp_path / "tests"
    src_dir.mkdir()
    tests_dir.mkdir()

    app_py = src_dir / "app.py"
    app_py.write_text("def add(a, b):\n    return 0  # Buggy implementation\n")

    test_py = tests_dir / "test_spec.py"
    test_py.write_text("from src.app import add\ndef test_add():\n    assert add(2, 3) == 5\n")

    # Mock adapter that fixes the code on turn 1
    def fix_app(workdir: Path):
        (workdir / "src" / "app.py").write_text("def add(a, b):\n    return a + b\n")

    adapter = MockAgentAdapter(name="mock", solver_fn=fix_app)

    result = run_tdd(
        root_dir=tmp_path,
        spec_path=tmp_path / "spec.md",
        test_file=test_py,
        agent=adapter,
        max_turns=3,
    )

    assert result["success"] is True
    assert result["turns_taken"] == 1
    assert result["status"] == SDLCState.INTEGRATED.value

    # Verify agent-trace.jsonl was written
    trace_file = tmp_path / ".asdlc" / "agent-trace.jsonl"
    assert trace_file.is_file()
    with open(trace_file) as f:
        traces = [json.loads(line) for line in f]
    assert len(traces) == 1
    assert traces[0]["agent"] == "mock"


def test_tdd_detects_tampering(tmp_path: Path):
    """
    Scenario: Agent attempts to modify tests/test_spec.py to fake a green exit.
    Expected: Anti-tampering gate detects SHA-256 hash mismatch and raises TestTamperingError.
    """
    init_project(tmp_path)

    src_dir = tmp_path / "src"
    tests_dir = tmp_path / "tests"
    src_dir.mkdir()
    tests_dir.mkdir()

    (src_dir / "app.py").write_text("def add(a, b):\n    return 0\n")
    test_py = tests_dir / "test_spec.py"
    test_py.write_text("from src.app import add\ndef test_add():\n    assert add(2, 3) == 5\n")

    # Tampering agent: instead of fixing app.py, changes test_spec.py to assert 0 == 0!
    def cheat_agent(workdir: Path):
        (workdir / "tests" / "test_spec.py").write_text("def test_add():\n    assert True\n")

    adapter = MockAgentAdapter(name="cheater", solver_fn=cheat_agent)

    with pytest.raises(TestTamperingError, match="Test suite modified by agent"):
        run_tdd(
            root_dir=tmp_path,
            spec_path=tmp_path / "spec.md",
            test_file=test_py,
            agent=adapter,
            max_turns=3,
        )


def test_tdd_max_turns_exceeded(tmp_path: Path):
    """
    Scenario: Agent never fixes the code and fails every turn.
    Expected: Exits with success=False after exactly max_turns.
    """
    init_project(tmp_path)

    src_dir = tmp_path / "src"
    tests_dir = tmp_path / "tests"
    src_dir.mkdir()
    tests_dir.mkdir()

    (src_dir / "app.py").write_text("def add(a, b):\n    return 0\n")
    test_py = tests_dir / "test_spec.py"
    test_py.write_text("from src.app import add\ndef test_add():\n    assert add(2, 3) == 5\n")

    # Ineffective agent
    def do_nothing(workdir: Path):
        pass

    adapter = MockAgentAdapter(name="idle", solver_fn=do_nothing)

    result = run_tdd(
        root_dir=tmp_path,
        spec_path=tmp_path / "spec.md",
        test_file=test_py,
        agent=adapter,
        max_turns=2,
    )

    assert result["success"] is False
    assert result["turns_taken"] == 2
    assert result["status"] == SDLCState.ABORTED.value

    # Verify state.json was updated to ABORTED
    with open(tmp_path / ".asdlc" / "state.json") as f:
        state = json.load(f)
    assert state["status"] == SDLCState.ABORTED.value


def test_tdd_fails_if_initial_tests_already_passing(tmp_path: Path):
    """
    REQ-TDD-002: Asserts that run_tdd halts and raises InitialTestsAlreadyPassingError
    if the verification suite passes before the agent touches the code (RED invariant),
    unless allow_green=True is specified.
    """
    init_project(tmp_path)

    src_dir = tmp_path / "src"
    tests_dir = tmp_path / "tests"
    src_dir.mkdir()
    tests_dir.mkdir()

    # Implementation is already working (GREEN from the start)
    (src_dir / "app.py").write_text("def add(a, b):\n    return a + b\n")
    test_py = tests_dir / "test_spec.py"
    test_py.write_text("from src.app import add\ndef test_add():\n    assert add(2, 3) == 5\n")

    adapter = MockAgentAdapter(name="idle", solver_fn=lambda w: None)

    with pytest.raises(InitialTestsAlreadyPassingError, match="Tests are already passing before agent invocation"):
        run_tdd(
            root_dir=tmp_path,
            spec_path=tmp_path / "spec.md",
            test_file=test_py,
            agent=adapter,
            allow_green=False,
        )


def test_tdd_allows_green_when_flagged(tmp_path: Path):
    """
    REQ-TDD-002: When allow_green=True, run_tdd is permitted to halt immediately on green.
    """
    init_project(tmp_path)

    src_dir = tmp_path / "src"
    tests_dir = tmp_path / "tests"
    src_dir.mkdir()
    tests_dir.mkdir()

    (src_dir / "app.py").write_text("def add(a, b):\n    return a + b\n")
    test_py = tests_dir / "test_spec.py"
    test_py.write_text("from src.app import add\ndef test_add():\n    assert add(2, 3) == 5\n")

    adapter = MockAgentAdapter(name="idle", solver_fn=lambda w: None)

    result = run_tdd(
        root_dir=tmp_path,
        spec_path=tmp_path / "spec.md",
        test_file=test_py,
        agent=adapter,
        allow_green=True,
    )

    assert result["success"] is True
    assert result["turns_taken"] == 0
    assert result["status"] == SDLCState.INTEGRATED.value


def test_adapter_subprocess_timeout(tmp_path: Path):
    """
    REQ-EXEC-001: Asserts that an agent CLI command that hangs will timeout
    rather than blocking the harness indefinitely.
    """
    import sys
    from asdlc.adapters import SubprocessAgentAdapter
    adapter = SubprocessAgentAdapter(
        name="hanging",
        cli_command=[sys.executable, "-c", "import time; time.sleep(10)"],
        timeout_seconds=1,
    )
    
    traces = []
    returncode = adapter.run_turn(
        prompt="Test prompt",
        workdir=tmp_path,
        trace_logger=lambda t: traces.append(t),
    )
    assert returncode == 124  # Standard timeout exit code
    assert len(traces) == 1
    assert "timeout" in traces[0]["action"].lower()


def test_eval_emits_valid_evidence(tmp_path: Path):
    """
    Scenario: Run asdlc eval on diff.
    Expected: Produces valid release-evidence.json matching schema in spec.md §5.1.
    """
    init_project(tmp_path)

    spec_file = tmp_path / "spec.md"
    spec_file.write_text("# Spec\nRequirements here")

    diff_content = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return 0
+    return a + b
"""
    diff_file = tmp_path / "pr.diff"
    diff_file.write_text(diff_content)

    evidence_file = tmp_path / "release-evidence.json"

    evidence = run_eval(
        spec_path=spec_file,
        diff_path=diff_file,
        out_path=evidence_file,
        task_id="TASK-001",
        git_commit_sha="abcdef123456",
        target_head_revision="main@178363a",
        risk_class="Low",
        tests_passed=True,
    )

    assert evidence_file.is_file()
    assert evidence["gate_verdict"] == "AUTO_MERGE_APPROVED"
    assert evidence["risk_class"] == "Low"
    assert evidence["test_evidence"]["all_passed"] is True
    assert "src/app.py" in evidence["semantic_delta"]["files_changed"]


def test_eval_rejects_tampered_test_diff(tmp_path: Path):
    """
    REQ-SEC-002: Asserts that asdlc eval rejects diffs that tamper with files in tests/
    even if the tests ostensibly passed, setting gate_verdict='REJECTED'.
    """
    init_project(tmp_path)

    spec_file = tmp_path / "spec.md"
    spec_file.write_text("# Spec\nRequirements here")

    # Tampered diff modifying test file
    tampered_diff = """diff --git a/tests/test_spec.py b/tests/test_spec.py
--- a/tests/test_spec.py
+++ b/tests/test_spec.py
@@ -1,2 +1,2 @@
-def test_add(): assert add(2, 3) == 5
+def test_add(): assert True
"""
    diff_file = tmp_path / "tampered.diff"
    diff_file.write_text(tampered_diff)

    evidence_file = tmp_path / "release-evidence.json"

    evidence = run_eval(
        spec_path=spec_file,
        diff_path=diff_file,
        out_path=evidence_file,
        task_id="TASK-TAMPER",
        git_commit_sha="hack123456",
        target_head_revision="main@178363a",
        risk_class="Low",
        tests_passed=True,  # Even though tests ostensibly passed!
        allow_test_changes=False,
    )

    assert evidence["gate_verdict"] == "REJECTED"
    assert "tests/test_spec.py" in evidence["semantic_delta"]["files_changed"]
    assert any(
        "tamper" in issue.lower() or "protected" in issue.lower() or "security violation" in issue.lower()
        for issue in evidence["evaluator_rubric"]["security_issues"]
    )


def test_examples_hello_workspace_is_runnable():
    """
    Scenario: Verify that examples/hello/ exists, has intent.md, spec.md, src/app.py,
    and tests/test_spec.py, and can be executed via asdlc tdd using MockAgentAdapter.
    """
    import shutil
    import tempfile

    repo_root = Path(__file__).resolve().parent.parent
    hello_dir = repo_root / "examples" / "hello"

    assert hello_dir.is_dir(), "Missing examples/hello/ workspace directory"
    assert (hello_dir / "intent.md").is_file(), "Missing examples/hello/intent.md"
    assert (hello_dir / "spec.md").is_file(), "Missing examples/hello/spec.md"
    assert (hello_dir / "src" / "app.py").is_file(), "Missing examples/hello/src/app.py"
    assert (hello_dir / "tests" / "test_spec.py").is_file(), "Missing examples/hello/tests/test_spec.py"

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_hello = Path(tmp_str) / "hello"
        shutil.copytree(hello_dir, tmp_hello)

        init_project(tmp_hello)

        def fix_calculator(workdir: Path):
            (workdir / "src" / "app.py").write_text(
                "def add(a: int, b: int) -> int:\n"
                "    \"\"\"Returns the sum of two integers.\"\"\"\n"
                "    return a + b\n"
            )

        adapter = MockAgentAdapter(name="mock", solver_fn=fix_calculator)

        res = run_tdd(
            root_dir=tmp_hello,
            spec_path=tmp_hello / "spec.md",
            test_file=tmp_hello / "tests" / "test_spec.py",
            agent=adapter,
            max_turns=3,
        )

        assert res["success"] is True
        assert res["turns_taken"] == 1
        assert res["status"] == SDLCState.INTEGRATED.value
