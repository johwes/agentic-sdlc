"""Inner-Loop State Engine: Temporal Child Workflow (PoC).

See specs/03-inner-loop.md. PoC stance: laptop-local orchestration, one
sandbox cell per task with exec-per-attempt freshness (see
specs/04-worker-cell.md lifecycle) — files + git persist in the cell across
attempts, conversational context never does.

Attempt lifecycle this module encodes (per-task cell, exec-per-attempt):

  upload frame (attempt N)
    -> exec wrapper (fresh headless run, see harness/wrapper.py)
    -> download receipt (task_receipt.json, see specs/07-contracts.md)
    -> gate (a) forbidden_paths? violation -> BLOCKED / HALT:BLOCKED (no retry)
    -> gate (b) tactile exit 0? nonzero (incl. 124 timeout) -> FAILED
    -> gate (c) AST parses? PoC syntax-validity only (stdlib parsers;
       tree-sitter grammars + hold-out suite are post-PoC slots)
    -> pass -> SUCCESS / COMPLETE (local checkpoint commit, no push)
    -> retryable fail + attempt < max -> reset cell to baseline (default),
       linear backoff, continue_as_new() at attempt N+1 (zero context)
    -> retryable fail + attempt == max -> FAILED / HALT:EXHAUSTED (escalate)

Cell loss mid-task: recreate the cell, re-upload the repo at the last commit
SHA from the ledger, resume at the current attempt. The cell holds no
irreplaceable state — receipts and SHAs live in Temporal history.

Pure helpers below (coerce_*, backoff_delay_seconds, next_frame,
check_file_syntax, gate_c_failures, decide_next) are stdlib-only so they
import and run without the Temporal SDK or a live server. The
@workflow/@activity definitions at the bottom wire them into Temporal when
`temporalio` is installed; without it the module still imports (guarded) for
offline inspection — same pattern as temporal/parent.py.
"""

from __future__ import annotations

import ast
import dataclasses
import datetime as _dt
import json
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Task queue + retry/backoff constants (PoC defaults per 03; tunable w/ evidence)
# ---------------------------------------------------------------------------

TASK_QUEUE = "agentic-sdlc-dev"

# Retry budget: explicit per-task max_attempts always wins; frame omission
# defaults to 5 (see 03 retry budget & backoff).
MAX_ATTEMPTS_DEFAULT = 5

# retry_strategy frame field: "reset" = `git reset --hard baseline_sha` inside
# the cell before the next attempt (clean slate; default); "continue" = keep
# the failed attempt commit and build on top (explicit opt-in only).
RETRY_STRATEGY_DEFAULT = "reset"
VALID_RETRY_STRATEGIES = ("reset", "continue")

# Linear backoff between attempts: delay = 60s x attempt, capped at 5 min.
BACKOFF_BASE_SECONDS = 60
BACKOFF_CAP_SECONDS = 5 * 60

# Gate (c) PoC: syntax validity only. Extension-mapped stdlib parsers below;
# unmapped extensions pass through (tree-sitter grammar pinning is an open
# question in 03; hold-out suite is reserved-but-inactive — the
# tests/evals/** read-only mount + forbidden_paths tripwire stay enforced).
SYNTAX_CHECKED_EXTENSIONS = (".py", ".json")


# ---------------------------------------------------------------------------
# Pure helpers (stdlib-only; no Temporal dependency)
# ---------------------------------------------------------------------------


def coerce_attempt(frame: dict[str, Any]) -> int:
    """Current cycle index, 1-indexed. Falls back to 1 on missing/garbage."""
    try:
        attempt = int(frame.get("attempt", 1))
    except (TypeError, ValueError):
        return 1
    return attempt if attempt >= 1 else 1


def coerce_max_attempts(frame: dict[str, Any]) -> int:
    """Ceiling before escalation. Explicit per-task value wins; default 5."""
    try:
        max_attempts = int(frame.get("max_attempts", MAX_ATTEMPTS_DEFAULT))
    except (TypeError, ValueError):
        return MAX_ATTEMPTS_DEFAULT
    return max_attempts if max_attempts >= 1 else MAX_ATTEMPTS_DEFAULT


def coerce_retry_strategy(frame: dict[str, Any]) -> str:
    """Frame retry_strategy, defaulting to "reset" (see 03).

    Unknown/missing values fall back to "reset" — the clean-slate default
    matching process-per-attempt freshness. "continue" is explicit opt-in.
    """
    strategy = frame.get("retry_strategy", RETRY_STRATEGY_DEFAULT)
    if strategy in VALID_RETRY_STRATEGIES:
        return str(strategy)
    return RETRY_STRATEGY_DEFAULT


def backoff_delay_seconds(attempt: int) -> int:
    """Linear backoff: 60s x attempt, capped at 5 min (see 03)."""
    try:
        n = int(attempt)
    except (TypeError, ValueError):
        n = 1
    if n < 1:
        n = 1
    return min(BACKOFF_BASE_SECONDS * n, BACKOFF_CAP_SECONDS)


def next_frame(frame: dict[str, Any], agent_summary: str | None = None) -> dict[str, Any]:
    """Fresh frame for continue_as_new() at attempt + 1 (zero context).

    Copies the frame, bumps `attempt`, and — when provided — attaches the
    previous attempt's `agent_summary` as text diagnostics under
    `prior_diagnostics` (never as conversational memory; the wrapper ignores
    it, the next attempt reads it as file text only).
    """
    fresh = dict(frame)
    fresh["attempt"] = coerce_attempt(frame) + 1
    if agent_summary:
        prior = str(agent_summary)[-4000:]
        fresh["prior_diagnostics"] = prior
    return fresh


def check_file_syntax(path: str, text: str) -> str | None:
    """PoC gate (c) syntax check for one file. Returns error string or None.

    - `.py` via `ast.parse` (stdlib stand-in for the tree-sitter grammar).
    - `.json` via `json.loads`.
    - All other extensions pass (None) — tree-sitter set pinning is an open
      question; hold-out execution is reserved-but-inactive in the PoC.
    """
    suffix = Path(path).suffix.lower()
    if suffix not in SYNTAX_CHECKED_EXTENSIONS:
        return None
    if suffix == ".py":
        try:
            ast.parse(text)
        except SyntaxError as e:
            return f"{path}: SyntaxError: {e}"
        return None
    if suffix == ".json":
        try:
            json.loads(text)
        except json.JSONDecodeError as e:
            return f"{path}: JSON invalid: {e}"
        return None
    return None


def gate_c_failures(
    files_changed: list[str],
    read_text: Callable[[str], str | None],
) -> list[str]:
    """Run PoC gate (c) over every changed file. Returns failure messages.

    `read_text` maps a repo-relative path to its current content, or None
    when the file is missing/deleted (deleted files pass — nothing to parse).
    Unmapped extensions pass; failures list non-empty means gate (c) fails.
    """
    failures: list[str] = []
    for f in files_changed or []:
        try:
            text = read_text(f)
        except Exception as e:
            failures.append(f"{f}: read error: {e}")
            continue
        if text is None:
            continue
        err = check_file_syntax(f, text)
        if err is not None:
            failures.append(err)
    return failures


# decide_next actions (return contract below).
COMPLETE = "complete"
RETRY_RESET = "retry_reset"
RETRY_CONTINUE = "retry_continue"
HALT_BLOCKED = "halt_blocked"
HALT_EXHAUSTED = "halt_exhausted"


def decide_next(
    receipt: dict[str, Any],
    frame: dict[str, Any],
    ast_failures: list[str] | None = None,
) -> tuple[str, str]:
    """Evaluate gates (a/b/c) in order; map to the next child action.

    Returns (action, detail) where action is one of:
      complete       -> gate pass: SUCCESS / COMPLETE (checkpoint + promote)
      retry_reset    -> retryable fail, strategy reset (default)
      retry_continue -> retryable fail, strategy continue (opt-in)
      halt_blocked   -> gate (a) BLOCKED / HALT:BLOCKED (immediate, no retry)
      halt_exhausted -> budget spent (attempt >= max): HALT:EXHAUSTED

    Gate mapping (see 03):
      (a) status BLOCKED / HALT:BLOCKED -> halt_blocked, never retried
          (anti-fuzzing + frame/repo mismatch signal).
      (b) tactile exit != 0 (incl. 124 timeout) or status FAILED -> FAILED.
      (c) ast_failures non-empty -> treated as FAILED (same budget rules).
    Unknown statuses halt blocked (safe default, needs human inspection).
    """
    attempt = coerce_attempt(frame)
    max_attempts = coerce_max_attempts(frame)
    strategy = coerce_retry_strategy(frame)
    failures = list(ast_failures or [])

    status = receipt.get("status")
    promise = receipt.get("exit_promise")
    tactile = receipt.get("tactile_execution") or {}
    exit_code = tactile.get("exit_code", 0)

    # Gate (a): forbidden_paths violation halts immediately, no retry.
    if status == "BLOCKED" or promise == "HALT:BLOCKED":
        return HALT_BLOCKED, f"HALT:BLOCKED (gate a): {receipt.get('agent_summary', '')}"[:4000]

    # Gate (c) failure rides as FAILED regardless of wrapper status text.
    tactile_failed = False
    try:
        tactile_failed = int(exit_code) != 0
    except (TypeError, ValueError):
        tactile_failed = True

    failed = bool(failures) or status == "FAILED" or tactile_failed

    if status == "SUCCESS" and not failures and not tactile_failed:
        return COMPLETE, "SUCCESS / COMPLETE: gates a+b+c pass"

    if status not in ("SUCCESS", "FAILED"):
        return HALT_BLOCKED, f"HALT:BLOCKED: unknown receipt status {status!r}"

    # Retryable FAILED (gate b nonzero or gate c parse fail).
    if failures:
        reason = f"gate (c) AST parse fail: {'; '.join(failures)}"[:4000]
    elif tactile_failed:
        reason = f"gate (b) tactile exit {exit_code} != 0"
    else:
        reason = f"FAILED: {receipt.get('agent_summary', '')}"[:4000]

    if attempt >= max_attempts:
        return HALT_EXHAUSTED, f"HALT:EXHAUSTED (attempt {attempt}/{max_attempts}): {reason}"[:4000]
    if strategy == "continue":
        return RETRY_CONTINUE, f"RETRYABLE_FAILURE (attempt {attempt}/{max_attempts}, continue): {reason}"[:4000]
    return RETRY_RESET, f"RETRYABLE_FAILURE (attempt {attempt}/{max_attempts}, reset): {reason}"[:4000]


# ---------------------------------------------------------------------------
# Temporal wiring (guarded: module imports without the SDK for offline use)
# ---------------------------------------------------------------------------

try:  # pragma: no cover - exercised with SDK installed
    from temporalio import activity, workflow

    _TEMPORAL_AVAILABLE = True
except ImportError:  # pragma: no cover - offline fallback
    _TEMPORAL_AVAILABLE = False

    class _Dummy:
        def __call__(self, *a: Any, **k: Any) -> Any:
            if a and callable(a[0]) and len(a) == 1 and not k:
                return a[0]
            return lambda fn: fn

        def __getattr__(self, name: str) -> Any:
            return _Dummy()

    activity = _Dummy()  # type: ignore[no-redef]
    workflow = _Dummy()  # type: ignore[no-redef]


@dataclasses.dataclass
class ChildInputs:
    """One task frame; the child owns attempts N..max for this task."""

    frame: dict[str, Any]


@dataclasses.dataclass
class ChildResult:
    task_id: str
    state: str  # complete | halt_blocked | halt_exhausted
    attempt: int
    action: str
    detail: str
    receipt: dict[str, Any]


@activity.defn(name="run_attempt")
async def run_attempt(frame: dict[str, Any]) -> dict[str, Any]:
    """Attempt slot: upload frame, exec wrapper, download receipt (see 04).

    Runs `openshell sandbox upload`, `sandbox exec --timeout ... cell-harness`,
    `sandbox download` on the host worker. Not executed in this scaffolding
    item — the pure gate helpers above carry the testable logic.
    """
    raise NotImplementedError(
        "run_attempt not yet implemented: shells out to the openshell CLI "
        "(upload frame -> exec cell-harness -> download task_receipt.json; "
        "see specs/04-worker-cell.md exec-per-attempt contract)."
    )


@activity.defn(name="reset_cell")
async def reset_cell(baseline_sha: str) -> dict[str, str]:
    """Atomic `git reset --hard baseline_sha` in the cell (strategy reset).

    Failed commits remain in reflog/diagnostics. Strategy "continue" skips
    this activity and builds on top (explicit opt-in only, see 03).
    """
    raise NotImplementedError(
        "reset_cell not yet implemented: runs git reset --hard "
        f"{baseline_sha!r} inside the per-task cell before the next attempt "
        "(see specs/03-inner-loop.md retry_strategy)."
    )


@activity.defn(name="checkpoint_commit")
async def checkpoint_commit(task_id: str) -> dict[str, str]:
    """Local checkpoint commit inside the cell/host checkout (no push).

    Workers never push to origin — promotion squashes + pushes on the host
    (see 03 checkpoint & promotion model + 02 promotion).
    """
    raise NotImplementedError(
        "checkpoint_commit not yet implemented: local commit only, no push "
        f"(task {task_id}); promotion squashes + opens the draft PR."
    )


@activity.defn(name="ast_check")
async def ast_check(receipt: dict[str, Any]) -> dict[str, Any]:
    """PoC gate (c) activity wrapper around gate_c_failures().

    Reads changed files from the cell checkout, runs the stdlib syntax
    mapping (tree-sitter + hold-out suite are post-PoC slots), and returns
    {"failures": [...]}. Never raises on parse failure — failures are data.
    """
    files = receipt.get("files_changed") or []

    def _read(path: str) -> str | None:
        p = Path(path)
        try:
            if p.is_file():
                return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
        return None

    return {"failures": gate_c_failures(list(files), _read)}


@workflow.defn(name="ChildWorkflow")
class ChildWorkflow:
    """Ralph attempt loop: one attempt per run, retry via continue_as_new.

    Zero context carryover: retries re-enter as a fresh run with
    next_frame() (attempt + 1, diagnostics-as-text only) so history never
    grows. Linear backoff (60s x attempt, cap 5 min) precedes the retry.
    Terminal states return a ChildResult for the parent to project/escalate.
    """

    @workflow.run
    async def run(self, inputs: ChildInputs) -> ChildResult:
        frame = dict(inputs.frame)
        task_id = str(frame.get("task_id", "unknown"))
        attempt = coerce_attempt(frame)
        max_attempts = coerce_max_attempts(frame)

        # 1. Execute one worker-cell attempt (upload -> exec -> download).
        receipt: dict[str, Any] = await workflow.execute_activity(
            run_attempt,
            frame,
            schedule_to_close_timeout=_dt.timedelta(minutes=30),
        )

        # 2. Gate (c): PoC syntax-validity over changed files.
        ast_out = await workflow.execute_activity(
            ast_check,
            receipt,
            schedule_to_close_timeout=_dt.timedelta(minutes=5),
        )
        failures = list((ast_out or {}).get("failures") or [])

        # 3. Gates (a/b/c) in order -> next action.
        action, detail = decide_next(receipt, frame, failures)

        if action == COMPLETE:
            await workflow.execute_activity(
                checkpoint_commit,
                task_id,
                schedule_to_close_timeout=_dt.timedelta(minutes=5),
            )
            return ChildResult(
                task_id=task_id,
                state="complete",
                attempt=attempt,
                action=action,
                detail=detail,
                receipt=receipt,
            )
        if action in (HALT_BLOCKED, HALT_EXHAUSTED):
            state = "halt_blocked" if action == HALT_BLOCKED else "halt_exhausted"
            return ChildResult(
                task_id=task_id,
                state=state,
                attempt=attempt,
                action=action,
                detail=detail,
                receipt=receipt,
            )

        # 4. Retryable fail with budget left: backoff, optional reset, fresh run.
        delay = backoff_delay_seconds(attempt)
        await workflow.sleep(_dt.timedelta(seconds=delay))
        if action == RETRY_RESET:
            baseline = str(frame.get("baseline_sha", frame.get("target_branch", "HEAD")))
            await workflow.execute_activity(
                reset_cell,
                baseline,
                schedule_to_close_timeout=_dt.timedelta(minutes=5),
            )
        fresh = next_frame(frame, str(receipt.get("agent_summary", "")))
        _guard = (attempt, max_attempts)  # noqa: F841 (attempt accounting)
        workflow.continue_as_new(ChildInputs(frame=fresh))
        raise RuntimeError("unreachable: continue_as_new never returns")
