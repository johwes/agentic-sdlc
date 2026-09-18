"""Inner-Loop State Engine: Temporal Child Workflow (PoC).

See specs/03-inner-loop.md. PoC stance: laptop-local orchestration, one
sandbox cell per task with exec-per-attempt freshness (see
specs/04-worker-cell.md lifecycle) — files + git persist in the cell across
attempts, conversational context never does.

Attempt lifecycle this module encodes (per-task cell, exec-per-attempt):

  create cell on first attempt (clone frame repo_url, no credentials)
    -> upload frame (attempt N)
    -> exec wrapper (fresh headless run, see harness/wrapper.py)
    -> download receipt (task_receipt.json, see specs/07-contracts.md)
    -> gate (a) forbidden_paths? violation -> BLOCKED / HALT:BLOCKED (no retry)
    -> gate (b) tactile exit 0? nonzero (incl. 124 timeout) -> FAILED
    -> gate (c) AST parses? PoC syntax-validity only (stdlib parsers;
       tree-sitter grammars + hold-out suite are post-PoC slots)
    -> pass -> SUCCESS / COMPLETE (local checkpoint commit, no push)
     -> retryable fail + attempt < max -> reset cell to baseline (default),
        linear backoff, continue_as_new() at attempt N+1 (zero context,
        cell name rides the frame — no recreate)
     -> retryable fail + attempt == max -> FAILED / HALT:EXHAUSTED (escalate)
     -> terminal states (complete / halt_*): delete cell, then return

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
import os
import subprocess
import tempfile
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
# Cell lifecycle helpers (host-side; called from activities only, never from
# the workflow — workflow code stays deterministic. All subprocess use is
# stdlib-only and runner-injectable for offline tests.)
# ---------------------------------------------------------------------------

# script subcommands (see scripts/spawn-cell.sh usage).
SPAWN_CREATE = "create"
SPAWN_EXEC_ATTEMPT = "exec-attempt"
SPAWN_DESTROY = "destroy"

# EXEC_TIMEOUT bounds the whole attempt server-side (agent dispatch + tactile
# + receipt work). Default 600 matches the spawner; per-attempt value derives
# from the frame tactile budget + margin (tunable, not spec-locked).
EXEC_TIMEOUT_DEFAULT = 600
EXEC_TIMEOUT_MARGIN_SECONDS = 420

# `git clone` wall-clock for the repo seed (public https, small PoC repos).
CLONE_TIMEOUT_SECONDS = 300


def spawn_script_path() -> str:
    """Resolve scripts/spawn-cell.sh (env override wins, repo-root fallback)."""
    env = os.environ.get("SPAWN_CELL_SCRIPT")
    if env and env.strip():
        return env.strip()
    try:
        here = Path(__file__).resolve()
        candidate = here.parent.parent / "scripts" / "spawn-cell.sh"
        if candidate.is_file():
            return str(candidate)
    except Exception:
        pass
    return "scripts/spawn-cell.sh"


def validate_repo_url(url: Any) -> str | None:
    """Check the frame repo_url per 04 ingestion (public https, no creds).

    Returns an error string, or None when the URL is acceptable.
    """
    if not isinstance(url, str) or not url.strip():
        return "repo_url must be a non-empty string"
    u = url.strip()
    if not u.startswith("https://"):
        return f"repo_url must be public https (got {u!r})"
    host_part = u[len("https://"):].split("/", 1)[0]
    if "@" in host_part:
        return "repo_url must not carry credentials (public https only)"
    return None


def prepare_workspace(
    frame: dict[str, Any],
    dest_dir: str | Path,
    runner: Callable[..., Any] | None = None,
) -> dict[str, str]:
    """Clone the frame repo_url into dest_dir; check out target_branch.

    No credentials are ever passed: public https clone only (auth lives in
    the provider-injected cell env and the owner's host `gh`, see 04).
    When target_branch is absent on the remote, a local branch is created
    from the clone HEAD (`checkout -B`) so fresh demo branches work.
    `runner` injects subprocess.run for offline tests. Raises on failure.
    """
    run = runner or subprocess.run
    url = frame.get("repo_url", "")
    err = validate_repo_url(url)
    if err is not None:
        raise ValueError(f"prepare_workspace: {err}")
    branch = str(frame.get("target_branch") or "main")
    dest = str(dest_dir)
    r = run(
        ["git", "clone", str(url).strip(), dest],
        capture_output=True,
        text=True,
        timeout=CLONE_TIMEOUT_SECONDS,
    )
    if r.returncode != 0:
        raise RuntimeError(f"git clone failed: {(r.stderr or '').strip()}"[:2000])
    r = run(
        ["git", "-C", dest, "checkout", branch],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        r2 = run(
            ["git", "-C", dest, "checkout", "-B", branch],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if r2.returncode != 0:
            raise RuntimeError(
                f"git checkout {branch!r} failed: {(r2.stderr or '').strip()}"[:2000]
            )
    return {"workspace_dir": dest, "branch": branch}


def new_workspace_dir(task_id: str) -> str:
    """Fresh host workspace dir for the repo seed (clone target)."""
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "-" for c in str(task_id))
    return tempfile.mkdtemp(prefix=f"ralph-{safe or 'task'}-")


def exec_timeout_for(frame: dict[str, Any]) -> int:
    """Attempt wall-clock for `sandbox exec --timeout` (tactile + margin)."""
    try:
        tactile = int(frame.get("tactile_timeout_seconds", 180))
    except (TypeError, ValueError):
        tactile = 180
    if tactile <= 0:
        tactile = 180
    explicit = os.environ.get("EXEC_TIMEOUT")
    if explicit and explicit.strip().isdigit() and int(explicit.strip()) > 0:
        return int(explicit.strip())
    return max(EXEC_TIMEOUT_DEFAULT, tactile + EXEC_TIMEOUT_MARGIN_SECONDS)


def build_create_env(task_id: str, workspace_dir: str) -> dict[str, str]:
    """Env for `spawn-cell.sh create` (TASK_ID + WORKSPACE_DIR contract)."""
    env = dict(os.environ)
    env["TASK_ID"] = str(task_id)
    env["WORKSPACE_DIR"] = str(workspace_dir)
    return env


def build_exec_attempt_env(
    cell: str, frame_path: str, attempt: int, out_dir: str, exec_timeout: int
) -> dict[str, str]:
    """Env for `spawn-cell.sh exec-attempt` (CELL/FRAME_JSON/ATTEMPT contract)."""
    env = dict(os.environ)
    env["CELL"] = str(cell)
    env["FRAME_JSON"] = str(frame_path)
    env["ATTEMPT"] = str(attempt)
    env["OUT_DIR"] = str(out_dir)
    env["EXEC_TIMEOUT"] = str(exec_timeout)
    return env


def run_spawn(
    subcommand: str,
    env: dict[str, str],
    runner: Callable[..., Any] | None = None,
) -> Any:
    """Invoke scripts/spawn-cell.sh <subcommand> with env. Returns the result."""
    run = runner or subprocess.run
    return run(
        [spawn_script_path(), subcommand],
        env=env,
        capture_output=True,
        text=True,
        timeout=None,
    )


def read_receipt_file(out_dir: str | Path) -> dict[str, Any]:
    """Load the downloaded task_receipt.json from the exec OUT_DIR."""
    p = Path(out_dir) / "task_receipt.json"
    try:
        raw = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RuntimeError(f"receipt not downloaded: {p} missing")
    except OSError as e:
        raise RuntimeError(f"receipt read error: {e}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"receipt JSON invalid: {e}")
    if not isinstance(data, dict):
        raise RuntimeError("receipt JSON must be an object")
    return data


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


async def _run_in_thread(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run a blocking stdlib call off the event loop (worker stays responsive)."""
    import asyncio as _asyncio

    return await _asyncio.to_thread(func, *args, **kwargs)


@activity.defn(name="create_cell")
async def create_cell(frame: dict[str, Any]) -> dict[str, str]:
    """Host activity: clone the frame repo_url, create the per-task cell.

    Prepares a fresh workspace dir (clone + checkout target_branch, no
    credentials — see 04 ingestion), then runs `spawn-cell.sh create`
    (TASK_ID + WORKSPACE_DIR contract). The script prints the cell name
    (`cell-<task_id>-<short_uuid>`) on stdout; the workflow carries it in
    `frame["cell"]` across continue_as_new retries (per-task cell, see 03
    lifecycle). Raises on clone/create failure (Temporal retries).
    """
    task_id = str(frame.get("task_id", "unknown"))
    workspace_dir = new_workspace_dir(task_id)
    prepare_workspace(frame, workspace_dir)
    env = build_create_env(task_id, workspace_dir)
    try:
        r = await _run_in_thread(run_spawn, SPAWN_CREATE, env)
    except FileNotFoundError as e:
        raise RuntimeError(f"spawn-cell.sh not found: {e}")
    if r.returncode != 0:
        raise RuntimeError(
            f"spawn-cell.sh create failed: {(r.stderr or '').strip()}"[:2000]
        )
    cell = (r.stdout or "").strip().splitlines()
    cell_name = cell[-1].strip() if cell else ""
    if not cell_name:
        raise RuntimeError("spawn-cell.sh create printed no cell name")
    return {"cell": cell_name, "workspace_dir": workspace_dir}


@activity.defn(name="destroy_cell")
async def destroy_cell(cell: str | dict[str, Any]) -> dict[str, str]:
    """Host activity: delete the per-task cell at terminal state (see 03).

    Runs `spawn-cell.sh destroy` (CELL contract). Accepts the bare cell
    name or a {"cell": ...} dict. Raises on failure so Temporal retries
    instead of orphaning the sandbox; the workflow records the outcome.
    """
    name = cell.get("cell") if isinstance(cell, dict) else cell
    name = str(name or "").strip()
    if not name:
        raise ValueError("destroy_cell: empty cell name")
    env = dict(os.environ)
    env["CELL"] = name
    try:
        r = await _run_in_thread(run_spawn, SPAWN_DESTROY, env)
    except FileNotFoundError as e:
        raise RuntimeError(f"spawn-cell.sh not found: {e}")
    if r.returncode != 0:
        raise RuntimeError(
            f"spawn-cell.sh destroy failed: {(r.stderr or '').strip()}"[:2000]
        )
    return {"cell": name, "deleted": "true"}


@activity.defn(name="run_attempt")
async def run_attempt(frame: dict[str, Any]) -> dict[str, Any]:
    """Host activity: one exec-per-attempt via `spawn-cell.sh exec-attempt`.

    Resolves the per-task cell from `frame["cell"]` (set by create_cell;
    `$CELL` env fallback for direct script use), writes the attempt frame
    to a temp file, runs upload -> exec cell-harness -> download receipt
    (see 04 exec-per-attempt contract), and returns the receipt dict the
    child gates (a/b/c) consume. Raises when the cell is unknown, the
    script fails, or no valid receipt comes back.
    """
    import tempfile as _tempfile

    cell = str(frame.get("cell") or os.environ.get("CELL") or "").strip()
    if not cell:
        raise ValueError(
            "run_attempt: no cell (frame['cell'] unset — create_cell first?)"
        )
    attempt = coerce_attempt(frame)
    tmp = _tempfile.mkdtemp(prefix="ralph-attempt-")
    frame_path = str(Path(tmp) / "current_task.json")
    Path(frame_path).write_text(json.dumps(frame, indent=2) + "\n", encoding="utf-8")
    out_dir = str(Path(tmp) / "out")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    env = build_exec_attempt_env(
        cell, frame_path, attempt, out_dir, exec_timeout_for(frame)
    )
    try:
        r = await _run_in_thread(run_spawn, SPAWN_EXEC_ATTEMPT, env)
    except FileNotFoundError as e:
        raise RuntimeError(f"spawn-cell.sh not found: {e}")
    if r.returncode != 0:
        raise RuntimeError(
            f"spawn-cell.sh exec-attempt failed: {(r.stderr or '').strip()}"[:2000]
        )
    return read_receipt_file(out_dir)


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

    Cell ownership (see 03 lifecycle + 04 spawn contract): one cell per
    task, created on the first attempt (frame carries no "cell" yet) and
    deleted at terminal state. The cell name rides the frame across
    continue_as_new retries — attempts never create or delete it, only a
    lost cell triggers recreation (caller re-runs without "cell").
    """

    async def _delete_cell(self, cell: str, detail: str) -> str:
        """Best-effort terminal-state cell delete (see 03 cleanup ownership).

        The Temporal worker owns deletion — no orphaned sandboxes. Failure
        is annotated onto the result detail for human triage instead of
        blocking the terminal result (orphan risk stays visible, never
        silent). Bundle download precedes this delete at promotion (see 02
        ordering constraint).
        """
        try:
            await workflow.execute_activity(
                destroy_cell,
                cell,
                schedule_to_close_timeout=_dt.timedelta(minutes=5),
            )
        except Exception as e:
            detail = f"{detail} | cell delete failed ({cell}): {e}"[:4000]
        return detail

    @workflow.run
    async def run(self, inputs: ChildInputs) -> ChildResult:
        frame = dict(inputs.frame)
        task_id = str(frame.get("task_id", "unknown"))
        attempt = coerce_attempt(frame)
        max_attempts = coerce_max_attempts(frame)

        # 0. Per-task cell: create on first attempt, reuse across retries.
        cell = str(frame.get("cell") or "").strip()
        if not cell:
            created = await workflow.execute_activity(
                create_cell,
                frame,
                schedule_to_close_timeout=_dt.timedelta(minutes=15),
            )
            cell = str(created["cell"])
            frame["cell"] = cell

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
            detail = await self._delete_cell(cell, detail)
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
            detail = await self._delete_cell(cell, detail)
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
        # next_frame() copies the frame, so frame["cell"] rides along: the
        # retried run reuses the per-task cell (no create/delete on retry).
        _guard = (attempt, max_attempts)  # noqa: F841 (attempt accounting)
        workflow.continue_as_new(ChildInputs(frame=fresh))
        raise RuntimeError("unreachable: continue_as_new never returns")
