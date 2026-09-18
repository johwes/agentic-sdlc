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
2. Ensure cell-local git commit identity (user.name/user.email, no secrets).
3. Dispatch the agent CLI (opencode / claude) with the contract prompt.
4. Capture stdout/stderr; collect the agent's summary trailer.
5. Run forbidden_paths diff assertion -> BLOCKED / HALT:BLOCKED (no retry).
6. Run tactile_command (timeout, 50-line tail) -> nonzero means FAILED.
7. Collect git rev-parse HEAD + git diff --name-only + token telemetry
   (nullable, best-effort).
8. Serialize schema-valid task_receipt.json to --receipt.

Exit code mirrors the receipt outcome for `sandbox exec` propagation.

Auth note: OpenCode reads OPENCODE_API_KEY from env (provider-injected,
placeholder-masked) natively — no auth.json seeding required.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
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


def _get_commit_sha(repo_dir: str | None = None) -> str:
    """Return `git rev-parse HEAD`, or "unknown" when unavailable.

    "unknown" is a sentinel for non-git / fresh-repo contexts (spec requires
    a string; telemetry gaps and missing SHAs never crash the wrapper).
    Runs in repo_dir (the exec workdir is NOT the repo — see
    _resolve_repo_dir); None inherits the process cwd (offline default).
    """
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=repo_dir or None,
        )
        if r.returncode == 0:
            sha = r.stdout.strip()
            if sha:
                return sha
    except Exception:
        pass
    return "unknown"


def _get_files_changed(repo_dir: str | None = None) -> list[str]:
    """Collect changed files vs HEAD: staged, unstaged, and untracked.

    Repo-relative paths (git emits them so); runs in repo_dir — see
    _resolve_repo_dir. None inherits the process cwd (offline default).
    """
    files: set[str] = set()
    cwd = repo_dir or None
    # Tracked changes (staged + unstaged) vs HEAD
    for cmd in (
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "diff", "--name-only"],
        ["git", "diff", "--cached", "--name-only"],
    ):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5, cwd=cwd)
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
            cwd=cwd,
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
                cwd=cwd,
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


def _get_commit_range_files(pre_sha: str | None, repo_dir: str | None = None) -> list[str]:
    """Files committed between pre_sha (exclusive) and HEAD (inclusive).

    A committed tree is clean vs HEAD, so working-tree diffs go blind the
    moment the agent commits — including to forbidden_paths violations the
    gate below must see. The caller records pre_sha before dispatch; this
    diffs it against post-dispatch HEAD. Skipped when pre_sha is missing
    or "unknown" (non-repo contexts keep today's behavior exactly).
    Never raises; failures yield [].
    """
    if not pre_sha or pre_sha == "unknown":
        return []
    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", pre_sha, "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=repo_dir or None,
        )
        if r.returncode != 0:
            return []
        return sorted({line.strip() for line in r.stdout.splitlines() if line.strip()})
    except Exception:
        return []


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


TACTILE_TAIL_LINES = 50
TACTILE_TAIL_CHARS = 4096
TACTILE_TIMEOUT_EXIT = 124
TACTILE_TIMEOUT_DEFAULT = 180


def _get_tactile_timeout(frame: dict) -> int:
    """Kill timeout for tactile_command. Default 180 per 07-contracts.md."""
    try:
        timeout = int(frame.get("tactile_timeout_seconds", TACTILE_TIMEOUT_DEFAULT))
    except (TypeError, ValueError):
        return TACTILE_TIMEOUT_DEFAULT
    if timeout <= 0:
        return TACTILE_TIMEOUT_DEFAULT
    return timeout


def _truncate_output(text: str, max_lines: int = TACTILE_TAIL_LINES, max_chars: int = TACTILE_TAIL_CHARS) -> str:
    """Cap output tail at 50 lines / ~4KB per 07-contracts.md."""
    tail = "\n".join(text.splitlines()[-max_lines:])
    if len(tail) > max_chars:
        tail = tail[-max_chars:]
    return tail


def _run_tactile(
    command: str, timeout_seconds: int, repo_dir: str | None = None
) -> tuple[int, str, bool]:
    """Run tactile_command. Returns (exit_code, summary_output, timed_out).

    Timeout kills the command, records exit 124, and prints
    "Command timed out after N seconds" to stderr per 07-contracts.md.
    Runs in repo_dir: tactile commands are repo-relative (e.g. pytest
    tests/..., node --test file.js) and file-not-found elsewhere — see
    _resolve_repo_dir. None inherits the process cwd (offline default).
    """
    if not command.strip():
        return 0, "", False
    try:
        r = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=repo_dir or None,
        )
    except subprocess.TimeoutExpired as e:
        partial = ""
        if e.stdout:
            partial += e.stdout.decode() if isinstance(e.stdout, bytes) else e.stdout
        if e.stderr:
            err = e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr
            partial += ("\n[stderr]\n" if partial else "") + err
        print(f"Command timed out after {timeout_seconds} seconds", file=sys.stderr)
        return TACTILE_TIMEOUT_EXIT, _truncate_output(partial), True
    combined = r.stdout or ""
    if r.stderr:
        combined += ("\n[stderr]\n" if combined else "") + r.stderr
    return r.returncode, _truncate_output(combined), False


def _coerce_attempt(frame: dict) -> tuple[int, int]:
    """Parse attempt/max_attempts; default max 5 per 03-inner-loop.md."""
    try:
        attempt = int(frame.get("attempt", 1))
    except (TypeError, ValueError):
        attempt = 1
    try:
        max_attempts = int(frame.get("max_attempts", 5))
    except (TypeError, ValueError):
        max_attempts = 5
    return attempt, max_attempts


def _coerce_token(value: object) -> int | None:
    """Best-effort token count coercion: non-negative int or None."""
    try:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, float):
            if not value.is_integer() or value < 0:
                return None
            return int(value)
        num = int(str(value).strip()) if isinstance(value, str) else int(value)  # type: ignore[arg-type]
        return num if num >= 0 else None
    except (TypeError, ValueError):
        return None


def _coerce_cost(value: object) -> float | None:
    """Best-effort cost coercion: non-negative float or None."""
    try:
        if value is None or isinstance(value, bool):
            return None
        num = float(str(value).strip()) if isinstance(value, str) else float(value)  # type: ignore[arg-type]
        if num < 0:
            return None
        return num
    except (TypeError, ValueError):
        return None


def _extract_metrics_from_obj(obj: object) -> dict | None:
    """Pull {input_tokens, output_tokens, cost} from one decoded JSON value.

    Supports Claude Code --verbose JSONL shapes
    (usage:{input_tokens,output_tokens}, total_cost_usd) and OpenCode-style
    summaries (tokens:{input,output}, cost/cost_usd), plus flat
    {input_tokens, output_tokens, cost}. Returns None when nothing found.
    """
    if not isinstance(obj, dict):
        return None
    found: dict = {}
    # Nested usage/tokens objects first
    for nested_key in ("usage", "tokens", "tokenUsage"):
        nested = obj.get(nested_key)
        if isinstance(nested, dict):
            for alias, canon in (
                ("input_tokens", "input_tokens"),
                ("inputTokens", "input_tokens"),
                ("prompt_tokens", "input_tokens"),
                ("promptTokens", "input_tokens"),
                ("input", "input_tokens"),
                ("prompt", "input_tokens"),
                ("output_tokens", "output_tokens"),
                ("outputTokens", "output_tokens"),
                ("completion_tokens", "output_tokens"),
                ("completionTokens", "output_tokens"),
                ("output", "output_tokens"),
                ("completion", "output_tokens"),
            ):
                if canon not in found and nested.get(alias) is not None:
                    found[canon] = nested[alias]
    # Flat keys (do not override nested hits)
    for alias, canon in (
        ("input_tokens", "input_tokens"),
        ("inputTokens", "input_tokens"),
        ("prompt_tokens", "input_tokens"),
        ("output_tokens", "output_tokens"),
        ("outputTokens", "output_tokens"),
        ("completion_tokens", "output_tokens"),
        ("cost", "cost"),
        ("cost_usd", "cost"),
        ("costUsd", "cost"),
        ("total_cost_usd", "cost"),
        ("totalCostUsd", "cost"),
        ("total_cost", "cost"),
    ):
        if canon not in found and obj.get(alias) is not None:
            found[canon] = obj[alias]
    if not found:
        return None
    return {
        "input_tokens": _coerce_token(found.get("input_tokens")),
        "output_tokens": _coerce_token(found.get("output_tokens")),
        "cost": _coerce_cost(found.get("cost")),
    }


def _parse_metrics_text(text: str) -> dict | None:
    """Scan JSON / JSONL text; last fully-parsed hit wins. Never raises."""
    try:
        best: dict | None = None
        # Whole-blob JSON first (covers single-object summaries)
        try:
            whole = json.loads(text)
            hit = _extract_metrics_from_obj(whole)
            if hit is not None:
                best = hit
            if isinstance(whole, list):
                for item in whole:
                    hit = _extract_metrics_from_obj(item)
                    if hit is not None:
                        best = hit
        except (json.JSONDecodeError, ValueError):
            pass
        # Line-delimited JSON (Claude --verbose JSONL); later lines override
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                hit = _extract_metrics_from_obj(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                continue
            if hit is not None:
                if best is None:
                    best = hit
                else:
                    # Merge: non-None fields from later lines win
                    for k, v in hit.items():
                        if v is not None:
                            best[k] = v
        return best
    except Exception:
        return None


def _null_metrics() -> dict:
    return {"input_tokens": None, "output_tokens": None, "cost": None}


def _collect_token_metrics(agent_log_text: str | None = None) -> dict:
    """Best-effort token telemetry per specs/07-contracts.md telemetry.

    Priority: explicit text arg → TASK_TOKEN_METRICS_JSON env →
    AGENT_LOG_PATH file → well-known default log paths. Parse failure or
    missing logs → all-null fields. Never raises, never blocks the workflow.
    """
    try:
        if agent_log_text:
            hit = _parse_metrics_text(agent_log_text)
            if hit is not None:
                return hit
        env_blob = os.environ.get("TASK_TOKEN_METRICS_JSON")
        if env_blob:
            hit = _parse_metrics_text(env_blob)
            if hit is not None:
                return hit
        candidates: list[str] = []
        env_path = os.environ.get("AGENT_LOG_PATH")
        if env_path:
            candidates.append(env_path)
        candidates.extend(
            [
                ".task/agent.log",
                "/sandbox/.task/agent.log",
                "agent.log",
            ]
        )
        for cand in candidates:
            try:
                p = Path(cand)
                if p.is_file():
                    text = p.read_text(encoding="utf-8", errors="replace")
                    # Cap scan to tail (~64KB) — metrics ride at the end
                    hit = _parse_metrics_text(text[-65536:])
                    if hit is not None:
                        return hit
            except Exception:
                continue
    except Exception:
        pass
    return _null_metrics()


VALID_STATUSES = {"SUCCESS", "FAILED", "BLOCKED"}
VALID_EXIT_PROMISES = {"COMPLETE", "RETRYABLE_FAILURE", "HALT:EXHAUSTED", "HALT:BLOCKED"}

# Stage 4: LLM dispatch + cell gitconfig identity (see specs/04-worker-cell.md).
#
# Tier-1 transfer path (locked): the wrapper performs LOCAL git ops only
# (config user.name/user.email, rev-parse, diff, ls-files, status) — never
# clone/push/fetch, and no credentials ever enter the cell. Candidate code
# leaves the cell exclusively as a host-downloaded `git bundle` (see
# specs/02-control-plane.md promotion); there is deliberately no push logic
# here.
#
# Dispatch posture mirrors specs/04-worker-cell.md tool equivalents:
#   opencode: opencode run --auto --model <id> "<contract prompt>"
#   claude:   claude -p "<contract prompt>" --dangerously-skip-permissions --no-auto-updater
# Model default matches config/opencode-sandbox.json (locked in spec 04);
# override via --model / CELL_MODEL. A future `model` frame field is recorded
# in spec 04, not built here.

DEFAULT_MODEL = "opencode-go/muse-spark-1.3-contributor"

GIT_IDENTITY_NAME = "Ralph Worker"
GIT_IDENTITY_EMAIL = "ralph-worker@localhost"

AGENT_TIMEOUT_DEFAULT = 480
AGENT_SUMMARY_MAX_LINES = 50
AGENT_SUMMARY_MAX_CHARS = 4096


def _ensure_git_identity(repo_dir: str | None = None) -> dict:
    """Write the non-secret commit identity into the cell repo config.

    Runs `git config user.name` / `git config user.email` (local repo scope
    by default — never --global, never credentials) in repo_dir: running
    from the exec workdir yields "not in a git directory" (observed live).
    Best-effort: returns {"name", "email", "configured"} and never raises;
    a missing git repo or git binary yields configured=False with a stderr
    warning. Must run before agent dispatch since nothing else sets
    identity in-cell.
    """
    result = {"name": GIT_IDENTITY_NAME, "email": GIT_IDENTITY_EMAIL, "configured": False}
    for key, value in (("user.name", GIT_IDENTITY_NAME), ("user.email", GIT_IDENTITY_EMAIL)):
        try:
            r = subprocess.run(
                ["git", "config", key, value],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=repo_dir or None,
            )
            if r.returncode != 0:
                print(
                    f"warning: git config {key} failed: {(r.stderr or '').strip()}",
                    file=sys.stderr,
                )
                return result
        except FileNotFoundError:
            print("warning: git binary not found; commit identity not set", file=sys.stderr)
            return result
        except Exception as e:
            print(f"warning: git config {key} error: {e}", file=sys.stderr)
            return result
    result["configured"] = True
    return result


ATTEMPT_PROMPT_DEFAULT = "/sandbox/.task/worker_prompt.txt"


def _resolve_contract_prompt_text(
    explicit_path: str | None = None,
    attempt_path: str | None = ATTEMPT_PROMPT_DEFAULT,
) -> tuple[str, str | None]:
    """Load the worker contract prompt. Returns (text, source_path or None).

    Search order: explicit --contract-prompt / CELL_CONTRACT_PROMPT, then
    the per-attempt host upload (/sandbox/.task/worker_prompt.txt —
    re-uploaded by the host on every attempt, never agent-persistent),
    then the in-cell path /etc/prompts/worker_contract.txt (baked by
    docker/worker-cell.Dockerfile), then repo-relative fallbacks for
    offline use. Missing prompt yields ("", None) with a stderr warning —
    dispatch still runs so gates stay testable offline.
    """
    candidates: list[str] = []
    if explicit_path:
        candidates.append(explicit_path)
    env_path = os.environ.get("CELL_CONTRACT_PROMPT")
    if env_path and env_path not in candidates:
        candidates.append(env_path)
    if attempt_path and attempt_path not in candidates:
        candidates.append(attempt_path)
    candidates.append("/etc/prompts/worker_contract.txt")
    try:
        here = Path(__file__).resolve()
        candidates.append(str(here.parent.parent / "prompts" / "worker_contract.txt"))
    except Exception:
        pass
    candidates.append("prompts/worker_contract.txt")
    for cand in candidates:
        try:
            p = Path(cand)
            if p.is_file():
                return p.read_text(encoding="utf-8", errors="replace"), str(p)
        except Exception:
            continue
    print("warning: worker contract prompt not found; dispatching with empty prompt", file=sys.stderr)
    return "", None


def _resolve_model(cli_model: str | None = None) -> str:
    """Model ID: --model flag wins, then CELL_MODEL env, then spec default."""
    if cli_model:
        return cli_model
    env_model = os.environ.get("CELL_MODEL")
    if env_model and env_model.strip():
        return env_model.strip()
    return DEFAULT_MODEL


# In-cell checkout (see 04 spawn contract: the workspace seed uploads to
# /sandbox/repo; the exec workdir /sandbox is its parent, NOT the repo).
CELL_REPO_DEFAULT = "/sandbox/repo"


def _resolve_repo_dir(explicit: str | None = None) -> str:
    """Resolve the repo checkout all repo-scoped subprocesses run in.

    Order: explicit --repo-dir / CELL_REPO_DIR (a missing path warns and
    falls through — never crash on a stale override), then
    /sandbox/repo when present (in-cell convention), else the process cwd
    (offline/host use, where the wrapper runs from the repo root).
    Running git/tactile from the exec workdir instead yields "not in a git
    directory" + file-not-found tactile failures (observed live
    2026-09-18). Always exists by construction (fallbacks are checked).
    """
    for cand in (explicit, os.environ.get("CELL_REPO_DIR")):
        if cand and cand.strip():
            p = Path(cand.strip())
            try:
                if p.is_dir():
                    return str(p)
            except Exception:
                pass
            print(
                f"warning: repo dir override not a directory: {cand.strip()}; falling back",
                file=sys.stderr,
            )
    try:
        if Path(CELL_REPO_DEFAULT).is_dir():
            return CELL_REPO_DEFAULT
    except Exception:
        pass
    return os.getcwd()


def _repo_checkout_valid(repo_dir: str) -> bool:
    """Whether repo_dir looks like a git checkout (.git file or dir both count).

    Pure path check, no subprocess — worktree .git files pass too.
    """
    try:
        return (Path(repo_dir) / ".git").exists()
    except Exception:
        return False


def _in_cell() -> bool:
    """Best-effort in-cell detection: the exec workdir exists on this host."""
    try:
        return Path("/sandbox").is_dir()
    except Exception:
        return False


def _resolve_agent_choice(cli_agent: str | None = None) -> str:
    """Agent selector: --agent flag wins, then CELL_AGENT_CLI env, else auto."""
    raw = cli_agent or os.environ.get("CELL_AGENT_CLI", "auto")
    choice = str(raw).strip().lower()
    if choice in ("auto", "opencode", "claude", "none", "skip", "off"):
        if choice in ("skip", "off"):
            return "none"
        return choice
    print(f"warning: unknown agent choice {raw!r}; falling back to auto", file=sys.stderr)
    return "auto"


def _resolve_agent_timeout(cli_timeout: int | None = None) -> int:
    """Agent dispatch kill timeout. --agent-timeout wins, then env, else 480s.

    480s leaves margin for the tactile budget (default 180s) + receipt work
    inside the spawn-cell EXEC_TIMEOUT default (600s). Tunable, not spec-locked.
    """
    if cli_timeout is not None:
        try:
            if int(cli_timeout) > 0:
                return int(cli_timeout)
        except (TypeError, ValueError):
            pass
    try:
        env_timeout = int(str(os.environ.get("CELL_AGENT_TIMEOUT_SECONDS", "")).strip())
        if env_timeout > 0:
            return env_timeout
    except (TypeError, ValueError):
        pass
    return AGENT_TIMEOUT_DEFAULT


def _resolve_agent_argv(agent: str, model: str, prompt_text: str) -> list[str] | None:
    """Build the headless CLI argv per specs/04-worker-cell.md, or None to skip.

    auto prefers opencode (PoC default provider opencode-go) when its binary
    is on PATH, else claude, else None (offline/demo hosts without CLIs).
    Returns None instead of raising; callers log the skip and continue so
    offline gates stay runnable without infrastructure.
    """
    choice = agent
    if choice == "none":
        return None
    if choice == "auto":
        if shutil.which("opencode") is not None:
            choice = "opencode"
        elif shutil.which("claude") is not None:
            choice = "claude"
        else:
            return None
    if choice == "opencode":
        if shutil.which("opencode") is None:
            return None
        # Spec 04: opencode run --auto --model <id> "<prompt>"
        return ["opencode", "run", "--auto", "--model", model, prompt_text]
    if choice == "claude":
        if shutil.which("claude") is None:
            return None
        # Spec 04: claude -p "<prompt>" --dangerously-skip-permissions --no-auto-updater
        return ["claude", "-p", prompt_text, "--dangerously-skip-permissions", "--no-auto-updater"]
    return None


def _run_agent(
    argv: list[str], timeout_seconds: int, repo_dir: str | None = None
) -> dict:
    """Run the agent CLI headless. Never raises; timeouts/failures are data.

    Returns {"stdout", "stderr", "exit_code" (int|None; None on timeout),
    "timed_out" (bool), "argv"}. Agent exit never gates the receipt on its
    own — tactile ground truth + forbidden_paths do (see 07-contracts.md);
    the result feeds agent_summary diagnostics + token-metrics parsing only.
    Runs in repo_dir so relative codebase paths resolve (see
    _resolve_repo_dir); None inherits the process cwd (offline default).
    """
    try:
        r = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=repo_dir or None,
        )
        return {
            "stdout": r.stdout or "",
            "stderr": r.stderr or "",
            "exit_code": r.returncode,
            "timed_out": False,
            "argv": argv,
        }
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout.decode() if isinstance(getattr(e, "stdout", None), bytes) else (e.stdout or "")
        stderr = e.stderr.decode() if isinstance(getattr(e, "stderr", None), bytes) else (e.stderr or "")
        print(f"agent dispatch timed out after {timeout_seconds} seconds", file=sys.stderr)
        return {"stdout": stdout, "stderr": stderr, "exit_code": None, "timed_out": True, "argv": argv}
    except FileNotFoundError:
        return {"stdout": "", "stderr": f"agent binary not found: {argv[0]}", "exit_code": None, "timed_out": False, "argv": argv}
    except Exception as e:
        return {"stdout": "", "stderr": f"agent dispatch error: {e}", "exit_code": None, "timed_out": False, "argv": argv}


def _build_agent_summary(
    *,
    argv: list[str] | None,
    model: str,
    contract_source: str | None,
    agent_result: dict | None,
    skipped_reason: str | None = None,
) -> tuple[str, str]:
    """Build (agent_summary, agent_log_text) for receipt + metrics parsing.

    agent_log_text is the raw stdout+stderr tail source for
    _collect_token_metrics (best-effort, nullable). agent_summary is the
    truncated human-readable trailer: CLI/model/prompt source, exit/timeout,
    COMPLETE trailer detection, and the output tail capped at 50 lines/~4KB.
    Never raises.
    """
    try:
        if skipped_reason is not None or argv is None:
            reason = skipped_reason or "no agent CLI available"
            summary = f"agent dispatch skipped ({reason}); model {model}"
            return summary, ""
        result = agent_result or {}
        stdout = str(result.get("stdout") or "")
        stderr = str(result.get("stderr") or "")
        exit_code = result.get("exit_code")
        timed_out = bool(result.get("timed_out"))
        cli = argv[0] if argv else "unknown"
        combined = stdout
        if stderr:
            combined += ("\n[stderr]\n" if combined else "") + stderr
        tail = _truncate_output(combined, AGENT_SUMMARY_MAX_LINES, AGENT_SUMMARY_MAX_CHARS)
        complete = "COMPLETE" in combined
        if timed_out:
            status_note = "timed out (exit unknown)"
        elif exit_code is None:
            status_note = "not executed"
        else:
            status_note = f"exit {exit_code}"
        header = f"agent {cli} (model {model}, prompt {contract_source or 'empty'}) {status_note}"
        trailer = "trailer COMPLETE present" if complete else "trailer COMPLETE absent"
        summary = f"{header}; {trailer}"
        if tail:
            summary += f"\n{tail}"
        log_text = combined
        # Keep the receipt field bounded even if truncation missed multibyte tails
        if len(summary) > AGENT_SUMMARY_MAX_CHARS + 512:
            summary = summary[-(AGENT_SUMMARY_MAX_CHARS + 512):]
        return summary, log_text
    except Exception as e:
        return f"agent summary build failed: {e}", ""
# Status / exit_promise matrix per specs/07-contracts.md
VALID_TRANSITIONS = {
    ("SUCCESS", "COMPLETE"),
    ("FAILED", "RETRYABLE_FAILURE"),
    ("FAILED", "HALT:EXHAUSTED"),
    ("BLOCKED", "HALT:BLOCKED"),
}


def _validate_receipt(receipt: dict) -> list[str]:
    """Schema check for task_receipt.json per specs/07-contracts.md. Returns errors."""
    errors: list[str] = []
    if not isinstance(receipt, dict):
        return ["receipt must be an object"]
    if not isinstance(receipt.get("task_id"), str) or not receipt["task_id"]:
        errors.append("task_id must be a non-empty string")
    if receipt.get("status") not in VALID_STATUSES:
        errors.append(f"status must be one of {sorted(VALID_STATUSES)}")
    if receipt.get("exit_promise") not in VALID_EXIT_PROMISES:
        errors.append(f"exit_promise must be one of {sorted(VALID_EXIT_PROMISES)}")
    if (
        receipt.get("status") in VALID_STATUSES
        and receipt.get("exit_promise") in VALID_EXIT_PROMISES
        and (receipt["status"], receipt["exit_promise"]) not in VALID_TRANSITIONS
    ):
        errors.append(
            f"invalid status/exit_promise pair: {receipt.get('status')}/{receipt.get('exit_promise')}"
        )
    if not isinstance(receipt.get("commit_sha"), str) or not receipt["commit_sha"]:
        errors.append("commit_sha must be a non-empty string")
    files_changed = receipt.get("files_changed")
    if not isinstance(files_changed, list) or any(not isinstance(f, str) for f in files_changed):
        errors.append("files_changed must be a string[]")
    tactile = receipt.get("tactile_execution")
    if not isinstance(tactile, dict):
        errors.append("tactile_execution must be an object")
    else:
        if not isinstance(tactile.get("command_run"), str):
            errors.append("tactile_execution.command_run must be a string")
        if not isinstance(tactile.get("exit_code"), int) or isinstance(tactile.get("exit_code"), bool):
            errors.append("tactile_execution.exit_code must be an integer")
        if not isinstance(tactile.get("summary_output"), str):
            errors.append("tactile_execution.summary_output must be a string")
    if not isinstance(receipt.get("agent_summary"), str):
        errors.append("agent_summary must be a string")
    metrics = receipt.get("token_metrics")
    if not isinstance(metrics, dict):
        errors.append("token_metrics must be an object")
    else:
        for key in ("input_tokens", "output_tokens"):
            v = metrics.get(key)
            if v is not None and (
                not isinstance(v, int) or isinstance(v, bool) or v < 0
            ):
                errors.append(f"token_metrics.{key} must be a non-negative int or null")
        cost = metrics.get("cost")
        if cost is not None and (
            not isinstance(cost, (int, float)) or isinstance(cost, bool) or float(cost) < 0
        ):
            errors.append("token_metrics.cost must be a non-negative number or null")
    return errors


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
    # Wrapper owns the envelope: reject invalid receipts before they hit disk.
    pre_errors = _validate_receipt(receipt)
    if pre_errors:
        raise ValueError(f"refusing to write invalid receipt: {'; '.join(pre_errors)}")
    # Write atomically via tmp + rename
    tmp = receipt_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    tmp.replace(receipt_path)
    # Read-back: guarantee the serialized file is schema-valid JSON
    try:
        on_disk = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"receipt read-back failed: {e}") from e
    post_errors = _validate_receipt(on_disk)
    if post_errors:
        raise ValueError(f"receipt failed read-back validation: {'; '.join(post_errors)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Cell harness stage 4: frame load + cell gitconfig identity + LLM dispatch, forbidden_paths -> BLOCKED, tactile ground truth -> FAILED, git SHAs + schema-valid task_receipt.json with nullable token_metrics (local git ops only, no push)")
    parser.add_argument("--attempt", required=True, help="Attempt index (1-indexed)")
    parser.add_argument("--frame", required=True, help="Path to current_task.json (read-only)")
    parser.add_argument("--receipt", required=True, help="Path to write task_receipt.json")
    parser.add_argument("--agent-log", required=False, default=None, help="Optional agent stdout/log text for best-effort token telemetry parsing")
    parser.add_argument("--agent", required=False, default=None, help="Agent CLI: auto (default), opencode, claude, none (skip dispatch). Env CELL_AGENT_CLI fallback.")
    parser.add_argument("--model", required=False, default=None, help="Model ID for opencode dispatch. Env CELL_MODEL fallback, else spec default.")
    parser.add_argument("--agent-timeout", required=False, default=None, type=int, help="Kill timeout secs for agent dispatch. Env CELL_AGENT_TIMEOUT_SECONDS fallback, else 480.")
    parser.add_argument("--contract-prompt", required=False, default=None, help="Explicit worker contract prompt path. Env CELL_CONTRACT_PROMPT fallback, else /etc/prompts/worker_contract.txt.")
    parser.add_argument("--repo-dir", required=False, default=None, help="Repo checkout repo-scoped commands (git, tactile, dispatch) run in. Env CELL_REPO_DIR fallback, else /sandbox/repo when present, else cwd.")
    parser.add_argument("--no-agent", action="store_true", help="Skip LLM dispatch (offline/demo; same as --agent none)")
    args = parser.parse_args()

    frame_path = Path(args.frame)
    receipt_path = Path(args.receipt)
    explicit_agent_log: str | None = args.agent_log
    repo_dir = _resolve_repo_dir(args.repo_dir)

    # 1. Load frame (read-only)
    frame, err = _load_frame(frame_path)
    if err is not None or frame is None:
        # Frame load failure is BLOCKED / HALT:BLOCKED per 07 contracts (system failure)
        commit_sha = _get_commit_sha(repo_dir)
        files_changed: list[str] = _get_files_changed(repo_dir)
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
            token_metrics=_collect_token_metrics(explicit_agent_log),
        )
        print(f"BLOCKED: frame load failed: {err}", file=sys.stderr)
        return EXIT_BLOCKED

    task_id = str(frame["task_id"])
    forbidden_paths = list(frame.get("forbidden_paths") or [])
    tactile_command = str(frame.get("tactile_command") or "")

    # Fail closed on a missing checkout where one is promised: in-cell
    # (convention path) or under an explicit operator override, a repo
    # without .git means broken seeding — evaluating the wrong directory
    # into a confusing FAILED (observed live) is worse than halting.
    # Offline cwd-fallback use without an override stays lenient.
    override_given = args.repo_dir is not None or bool(
        (os.environ.get("CELL_REPO_DIR") or "").strip()
    )
    if (override_given or _in_cell()) and not _repo_checkout_valid(repo_dir):
        detail = f"cell repo checkout missing or invalid: {repo_dir}"
        print(f"BLOCKED: {detail}", file=sys.stderr)
        _write_receipt(
            receipt_path,
            task_id=task_id,
            status="BLOCKED",
            exit_promise="HALT:BLOCKED",
            commit_sha="unknown",
            files_changed=[],
            tactile_execution={"command_run": tactile_command, "exit_code": 0, "summary_output": ""},
            agent_summary=f"BLOCKED: {detail}",
            token_metrics=_collect_token_metrics(explicit_agent_log),
        )
        return EXIT_BLOCKED

    # 2. Cell-local git identity before dispatch (non-secret, local scope only).
    identity = _ensure_git_identity(repo_dir)

    # Pre-dispatch HEAD: bounds the candidate commit range. Agent commits
    # vanish from working-tree diffs once made, so files_changed below
    # unions the tree state with diff(pre_sha, HEAD) — see
    # _get_commit_range_files.
    pre_sha = _get_commit_sha(repo_dir)

    # 3. LLM dispatch (best-effort; agent exit never overrides gates).
    agent_choice = "none" if args.no_agent else _resolve_agent_choice(args.agent)
    model = _resolve_model(args.model)
    agent_timeout = _resolve_agent_timeout(args.agent_timeout)
    prompt_text, contract_source = _resolve_contract_prompt_text(args.contract_prompt)
    agent_argv = _resolve_agent_argv(agent_choice, model, prompt_text)
    agent_result: dict | None = None
    skipped_reason: str | None = None
    if agent_argv is None:
        if agent_choice == "none":
            skipped_reason = "dispatch disabled (--no-agent/--agent none)"
        else:
            skipped_reason = f"no {agent_choice} CLI on PATH (offline/demo)"
        print(f"agent dispatch skipped ({skipped_reason})", file=sys.stderr)
    else:
        print(f"dispatching agent: {agent_argv[0]} (model {model})", file=sys.stderr)
        agent_result = _run_agent(agent_argv, agent_timeout, repo_dir)
    agent_summary, agent_log_text = _build_agent_summary(
        argv=agent_argv,
        model=model,
        contract_source=contract_source,
        agent_result=agent_result,
        skipped_reason=skipped_reason,
    )
    if explicit_agent_log:
        agent_log_text = (agent_log_text + "\n" + explicit_agent_log) if agent_log_text else explicit_agent_log
    token_metrics = _collect_token_metrics(agent_log_text)
    identity_note = "git identity configured" if identity.get("configured") else "git identity NOT configured (see stderr)"

    # Collect post-dispatch git state (agent edits land here; gates run on this).
    # Union working-tree changes with the attempt's commit range so committed
    # changes (a clean tree vs HEAD) stay visible to the forbidden_paths gate
    # and sensor diff-scope — committing must never hide a touched path.
    commit_sha = _get_commit_sha(repo_dir)
    files_changed = sorted(
        set(_get_files_changed(repo_dir))
        | set(_get_commit_range_files(pre_sha, repo_dir))
    )

    # 4. Forbidden_paths diff assertion -> BLOCKED / HALT:BLOCKED (no retry)
    violations = _check_forbidden(files_changed, forbidden_paths, receipt_path)
    if violations:
        detail = ", ".join(f"{f} matched {pat}" for f, pat in violations)
        summary = f"BLOCKED: forbidden_paths violation: {detail} | {identity_note} | {agent_summary}"
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
            token_metrics=token_metrics,
        )
        return EXIT_BLOCKED

    # 5. Tactile ground truth: nonzero exit (incl. 124 on timeout) -> FAILED.
    # Agent text cannot override a test failure; agent_summary is diagnostics.
    timeout_seconds = _get_tactile_timeout(frame)
    attempt, max_attempts = _coerce_attempt(frame)
    exit_code, summary_output, _timed_out = _run_tactile(tactile_command, timeout_seconds, repo_dir)
    tactile_execution = {
        "command_run": tactile_command,
        "exit_code": exit_code,
        "summary_output": summary_output,
    }
    if exit_code != 0:
        exit_promise = "HALT:EXHAUSTED" if attempt >= max_attempts else "RETRYABLE_FAILURE"
        summary = f"FAILED: tactile_command exited {exit_code}: {tactile_command} | {identity_note} | {agent_summary}"
        print(summary, file=sys.stderr)
        _write_receipt(
            receipt_path,
            task_id=task_id,
            status="FAILED",
            exit_promise=exit_promise,
            commit_sha=commit_sha,
            files_changed=files_changed,
            tactile_execution=tactile_execution,
            agent_summary=summary,
            token_metrics=token_metrics,
        )
        return EXIT_FAILED

    # Clean diff + tactile pass emits SUCCESS; agent output rides as diagnostics.
    summary = (
        f"stage 4: task {task_id} attempt {args.attempt}, tactile passed, "
        f"{identity_note} | {agent_summary}"
    )
    print(summary)
    _write_receipt(
        receipt_path,
        task_id=task_id,
        status="SUCCESS",
        exit_promise="COMPLETE",
        commit_sha=commit_sha,
        files_changed=files_changed,
        tactile_execution=tactile_execution,
        agent_summary=summary,
        token_metrics=token_metrics,
    )
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
