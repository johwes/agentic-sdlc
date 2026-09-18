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
     -> pass -> SUCCESS / COMPLETE (local checkpoint commit, no push;
        cell RETAINED — the parent downloads the bundle before deleting,
        see 02 ordering constraint)
      -> retryable fail + attempt < max -> reset cell to baseline (default),
         linear backoff, continue_as_new() at attempt N+1 (zero context,
         cell name rides the frame — no recreate)
      -> retryable fail + attempt == max -> FAILED / HALT:EXHAUSTED (escalate)
      -> halt states (halt_*): delete cell, then return (nothing to promote)
      -> complete: retain cell, then return (parent promotes, then deletes)

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


def prompt_overrides_dir() -> str:
    """Resolve prompts/overrides/ (env PROMPT_OVERRIDES_DIR wins, repo fallback).

    Host-side file convention for per-task prompt overrides (see 04 worker
    prompt contract): prompts/overrides/<TASK_ID>.txt, e.g.
    prompts/overrides/TASK-403.txt. Same pattern as spawn_script_path().
    """
    env = os.environ.get("PROMPT_OVERRIDES_DIR")
    if env and env.strip():
        return env.strip()
    try:
        here = Path(__file__).resolve()
        candidate = here.parent.parent / "prompts" / "overrides"
        return str(candidate)
    except Exception:
        return os.path.join("prompts", "overrides")


def prompt_override_path(task_id: str) -> str | None:
    """Resolve the host-authored prompt override for a task, if any.

    Explicit PROMPT_FILE env wins; else the prompts/overrides/<TASK_ID>.txt
    convention (task_id sanitized to alphanumerics/dashes/underscores so it
    can never escape the overrides dir). Returns None when no override
    exists — the wrapper then uses the image default prompt (see 04
    delivery tiers). Never raises on a missing file (default behavior).
    """
    explicit = os.environ.get("PROMPT_FILE")
    if explicit and explicit.strip():
        return explicit.strip()
    safe = "".join(c for c in str(task_id) if c.isalnum() or c in ("-", "_"))
    if not safe:
        return None
    candidate = Path(prompt_overrides_dir()) / f"{safe}.txt"
    try:
        if candidate.is_file():
            return str(candidate)
    except Exception:
        return None
    return None


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
    cell: str,
    frame_path: str,
    attempt: int,
    out_dir: str,
    exec_timeout: int,
    prompt_file: str | None = None,
) -> dict[str, str]:
    """Env for `spawn-cell.sh exec-attempt` (CELL/FRAME_JSON/ATTEMPT contract).

    prompt_file (when given) rides PROMPT_FILE: the spawner uploads it as
    the per-attempt /sandbox/.task/worker_prompt.txt override, re-uploaded
    every attempt so in-cell edits can never persist it (see 04 tiers).
    """
    env = dict(os.environ)
    env["CELL"] = str(cell)
    env["FRAME_JSON"] = str(frame_path)
    env["ATTEMPT"] = str(attempt)
    env["OUT_DIR"] = str(out_dir)
    env["EXEC_TIMEOUT"] = str(exec_timeout)
    if prompt_file:
        env["PROMPT_FILE"] = str(prompt_file)
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


# In-cell repo path: the spawn contract uploads the workspace seed to
# /sandbox/repo (see 04). Env override covers driver layout drift.
CELL_REPO_DEFAULT = "/sandbox/repo"

# Wall-clock per in-cell git op (reset/rev-parse/status/add/commit are fast
# local ops; Temporal activity timeouts bound the outermost layer, see 03).
CELL_EXEC_TIMEOUT_SECONDS = 120

# Non-secret commit identity, mirroring harness/wrapper.py (which sets the
# same values in-cell before dispatch). Kept as literals so this module
# stays importable without the harness on sys.path.
GIT_IDENTITY_NAME = "Ralph Worker"
GIT_IDENTITY_EMAIL = "ralph-worker@localhost"

# Git subcommands this module may run inside the cell. Allowlist, not
# convention: argv is fixed (no shell), so push/fetch/clone can never be
# constructed here — "local-only, no push" is structural (see 03: workers
# have no push path; only the promotion step pushes, see 02).
ALLOWED_CELL_GIT_OPS = ("reset", "rev-parse", "status", "add", "commit", "config")


def openshell_bin() -> str:
    """Local openshell CLI (env override wins, for tests/dev gateways)."""
    env = os.environ.get("OPENSHELL_BIN")
    if env and env.strip():
        return env.strip()
    return "openshell"


def cell_repo_path() -> str:
    """In-cell checkout path (env override wins)."""
    env = os.environ.get("CELL_REPO_PATH")
    if env and env.strip():
        return env.strip()
    return CELL_REPO_DEFAULT


def cell_exec_argv(
    cell: str, repo: str, git_args: list[str], timeout: int = CELL_EXEC_TIMEOUT_SECONDS
) -> list[str]:
    """Build `openshell sandbox exec` argv for one in-cell git op.

    Fixed argv, no shell: the ref/message ride as single arguments after
    `--`, so they cannot escape into options or commands.
    """
    return [
        openshell_bin(),
        "sandbox",
        "exec",
        "-n",
        str(cell),
        "--workdir",
        str(repo),
        "--timeout",
        str(timeout),
        "--",
        "git",
        *[str(a) for a in git_args],
    ]


def run_cell_git(
    cell: str,
    git_args: list[str],
    repo: str | None = None,
    runner: Callable[..., Any] | None = None,
    timeout: int = CELL_EXEC_TIMEOUT_SECONDS,
) -> Any:
    """Run one allowlisted git op in the cell. Returns the result.

    Raises RuntimeError on non-git op names or nonzero exit (stderr tail
    attached); Temporal retries the activity.
    """
    op = git_args[0] if git_args else ""
    if op not in ALLOWED_CELL_GIT_OPS:
        raise ValueError(f"refusing non-local git op in cell: {op!r}")
    run = runner or subprocess.run
    argv = cell_exec_argv(cell, repo or cell_repo_path(), list(git_args), timeout)
    try:
        r = run(argv, capture_output=True, text=True, timeout=timeout + 60)
    except FileNotFoundError as e:
        raise RuntimeError(f"openshell CLI not found: {e}")
    if r.returncode != 0:
        raise RuntimeError(
            f"cell git {' '.join(list(git_args)[:3])} failed: "
            f"{(r.stderr or '').strip()}"[:2000]
        )
    return r


def validate_baseline(ref: Any) -> str | None:
    """Check the reset baseline ref. Returns an error string, or None if ok.

    Single git revision only: rejects empty values and leading dashes
    (which git would parse as flags, not refs).
    """
    if not isinstance(ref, str) or not ref.strip():
        return "baseline_sha must be a non-empty string"
    if ref.strip().startswith("-"):
        return f"baseline_sha must be a revision, not a flag: {ref!r}"
    if any(c.isspace() for c in ref.strip()):
        return f"baseline_sha must be a single revision: {ref!r}"
    return None


def checkpoint_message(task_id: str, attempt: Any) -> str:
    """Local checkpoint commit message (squashed at promotion, see 02)."""
    try:
        n = int(attempt)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        n = "?"
    return f"checkpoint({task_id}): SUCCESS attempt {n}"


def reset_cell_impl(
    cell: str,
    baseline_sha: str,
    repo: str | None = None,
    runner: Callable[..., Any] | None = None,
) -> dict[str, str]:
    """Atomic `git reset --hard baseline_sha` in the cell (strategy reset).

    One git command = atomic; failed commits stay in reflog/diagnostics
    (see 03). Returns the post-reset HEAD for the ledger.
    """
    name = str(cell or "").strip()
    if not name:
        raise ValueError("reset_cell: empty cell name")
    err = validate_baseline(baseline_sha)
    if err is not None:
        raise ValueError(f"reset_cell: {err}")
    target = str(repo or cell_repo_path())
    run_cell_git(name, ["reset", "--hard", baseline_sha.strip()], target, runner)
    r = run_cell_git(name, ["rev-parse", "HEAD"], target, runner)
    return {
        "cell": name,
        "baseline_sha": baseline_sha.strip(),
        "commit_sha": (r.stdout or "").strip(),
        "reset": "true",
    }


def checkpoint_commit_impl(
    cell: str,
    task_id: str,
    attempt: Any = "?",
    repo: str | None = None,
    runner: Callable[..., Any] | None = None,
) -> dict[str, str]:
    """Local checkpoint commit in the cell checkout (no push, see 03).

    The agent commits per the prompt contract; when it already did, the
    tree is clean and this records HEAD (`committed: false`). When the
    tree is dirty (untracked edits, agent forgot to commit), stage all
    (`add -A` captures new files too — no partial checkpoints, see 03
    failure modes) and commit locally under the worker identity. Gate (a)
    already passed, so no forbidden paths can be in the tree. Returns the
    checkpoint SHA for Temporal history (see 03: wrapper records it,
    Temporal logs it).
    """
    name = str(cell or "").strip()
    if not name:
        raise ValueError("checkpoint_commit: empty cell name")
    tid = str(task_id or "").strip()
    if not tid:
        raise ValueError("checkpoint_commit: empty task_id")
    target = str(repo or cell_repo_path())
    head = run_cell_git(name, ["rev-parse", "HEAD"], target, runner)
    sha = (head.stdout or "").strip()
    if not sha:
        raise RuntimeError("checkpoint_commit: empty HEAD (no commits in cell?)")
    dirty = run_cell_git(name, ["status", "--porcelain"], target, runner)
    if not (dirty.stdout or "").strip():
        return {"cell": name, "task_id": tid, "commit_sha": sha, "committed": "false"}
    run_cell_git(name, ["config", "user.name", GIT_IDENTITY_NAME], target, runner)
    run_cell_git(name, ["config", "user.email", GIT_IDENTITY_EMAIL], target, runner)
    run_cell_git(name, ["add", "-A"], target, runner)
    run_cell_git(
        name, ["commit", "-m", checkpoint_message(tid, attempt)], target, runner
    )
    new_head = run_cell_git(name, ["rev-parse", "HEAD"], target, runner)
    new_sha = (new_head.stdout or "").strip()
    if not new_sha:
        raise RuntimeError("checkpoint_commit: commit left empty HEAD")
    return {"cell": name, "task_id": tid, "commit_sha": new_sha, "committed": "true"}


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
    # Per-task cell name. Set on `complete` so the parent can download the
    # candidate bundle BEFORE the terminal-state delete (see 02 ordering
    # constraint); empty on halt_* (cell already deleted, nothing to
    # promote) and on runs that predate this handoff.
    cell: str = ""


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
    # Per-attempt prompt override (host-authored, see 04 delivery tiers):
    # staged into the attempt tmp dir so the frame + prompt travel as one
    # fresh bundle; absent override = image default prompt (no PROMPT_FILE).
    prompt_file: str | None = None
    override = prompt_override_path(str(frame.get("task_id", "")))
    if override:
        try:
            staged = Path(tmp) / "worker_prompt.txt"
            staged.write_bytes(Path(override).read_bytes())
            prompt_file = str(staged)
        except OSError as e:
            raise RuntimeError(f"run_attempt: cannot stage prompt override: {e}")
    env = build_exec_attempt_env(
        cell, frame_path, attempt, out_dir, exec_timeout_for(frame), prompt_file
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
async def reset_cell(payload: dict[str, Any]) -> dict[str, str]:
    """Host activity: atomic `git reset --hard baseline_sha` in the cell.

    Payload {"cell", "baseline_sha"} (strategy "reset", the default; the
    workflow skips this activity entirely on "continue", see 03). The cell
    name rides the frame across continue_as_new retries, so this runs in
    the per-task cell before the next attempt. Failed commits remain in
    reflog/diagnostics. Local op only — the argv allowlist cannot express
    push/fetch/clone. Raises on failure (Temporal retries).
    """
    if not isinstance(payload, dict):
        raise ValueError("reset_cell: payload must be {cell, baseline_sha}")
    return await _run_in_thread(
        reset_cell_impl,
        str(payload.get("cell") or ""),
        str(payload.get("baseline_sha") or ""),
    )


@activity.defn(name="checkpoint_commit")
async def checkpoint_commit(payload: dict[str, Any]) -> dict[str, str]:
    """Host activity: local checkpoint commit in the cell checkout (no push).

    Payload {"cell", "task_id", "attempt"} (attempt optional, for the
    message). Records the agent's commit when the tree is clean, else
    stages + commits locally. Returns the checkpoint SHA; Temporal logs
    it in history (see 03 checkpoint model). Promotion squashes + pushes
    on the host later (see 02) — never here.
    """
    if not isinstance(payload, dict):
        raise ValueError("checkpoint_commit: payload must be {cell, task_id}")
    return await _run_in_thread(
        checkpoint_commit_impl,
        str(payload.get("cell") or ""),
        str(payload.get("task_id") or ""),
        payload.get("attempt", "?"),
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
    task, created on the first attempt (frame carries no "cell" yet).
    Halt states delete the cell here; on `complete` the cell is retained
    and its name rides the ChildResult to the parent, which downloads the
    candidate bundle before deleting (see 02 ordering constraint). The
    cell name rides the frame across continue_as_new retries — attempts
    never create or delete it, only a lost cell triggers recreation
    (caller re-runs without "cell").
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
            checkpoint = await workflow.execute_activity(
                checkpoint_commit,
                {"cell": cell, "task_id": task_id, "attempt": attempt},
                schedule_to_close_timeout=_dt.timedelta(minutes=5),
            )
            detail = f"{detail} | checkpoint {checkpoint['commit_sha']}"[:4000]
            # Retain the cell: the parent downloads the candidate bundle
            # before the terminal-state delete (see 02 ordering constraint —
            # ledger SHAs are useless once the cell is gone). The parent
            # owns deletion after promotion (or after a promotion halt).
            detail = f"{detail} | cell {cell} retained for promotion"[:4000]
            return ChildResult(
                task_id=task_id,
                state="complete",
                attempt=attempt,
                action=action,
                detail=detail,
                receipt=receipt,
                cell=cell,
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
                cell="",
            )

        # 4. Retryable fail with budget left: backoff, optional reset, fresh run.
        delay = backoff_delay_seconds(attempt)
        await workflow.sleep(_dt.timedelta(seconds=delay))
        if action == RETRY_RESET:
            baseline = str(frame.get("baseline_sha", frame.get("target_branch", "HEAD")))
            await workflow.execute_activity(
                reset_cell,
                {"cell": cell, "baseline_sha": baseline},
                schedule_to_close_timeout=_dt.timedelta(minutes=5),
            )
        fresh = next_frame(frame, str(receipt.get("agent_summary", "")))
        # next_frame() copies the frame, so frame["cell"] rides along: the
        # retried run reuses the per-task cell (no create/delete on retry).
        _guard = (attempt, max_attempts)  # noqa: F841 (attempt accounting)
        workflow.continue_as_new(ChildInputs(frame=fresh))
        raise RuntimeError("unreachable: continue_as_new never returns")
