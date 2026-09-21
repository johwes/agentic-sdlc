"""Macro Control Plane: Temporal Parent Workflow stub (PoC).

See specs/02-control-plane.md. PoC stance: simplest operable path on the
owner's laptop — no webhook server, no cluster deployment, no LLM
decomposition, no review panel.

PoC flow this stub encodes:
  file trigger (tasks/inbox/TASK-<n>.json)
    -> 1 file = 1 ledger task = 1 child workflow (no decomposition)
    -> ledger states: inbox -> active -> review -> promoted | escalated
    -> sensor review degrades to a logged no-op when no sensors are
       configured ("review: skipped, no sensors configured" — never silent;
       canonical suite in temporal/sensors.py, see 05)
     -> promotion = draft PR via gh on the host (bundle -> fetch ->
        scan -> squash -> push -> draft PR chain, see 02)
    -> HALT:EXHAUSTED / HALT:BLOCKED receipts -> escalated, never retried
    -> SLAs: 2h inbox-to-terminal wall-clock (auto-escalate on breach);
       24h promotion-staleness nudge (reminder only, never auto-merge).

Future slots (named, not built): webhook ingest adapter, LLM decomposition
activity, multi-agent review panel, Tekton/ArgoCD release (see 06).

Pure helpers below (load_frame, initial_ledger_entry, review_gate,
decide_terminal, render_ledger_row) are stdlib-only so they import and run
without the Temporal SDK or a live server. The @workflow/@activity
definitions at the bottom wire them into Temporal when `temporalio` is
installed; without it the module still imports (guarded) for offline
inspection.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Task queue + SLA constants (PoC defaults per 02; tunable with evidence)
# ---------------------------------------------------------------------------

TASK_QUEUE = "agentic-sdlc-dev"
TEMPORAL_ADDRESS = "localhost:7233"

# Global task wall-clock: 2h from inbox to terminal (promoted / escalated).
TASK_WALL_CLOCK_SECONDS = 2 * 3600
# Promotion-queue staleness nudge: 24h in promoted without human action.
PROMOTION_STALENESS_NUDGE_SECONDS = 24 * 3600

LEDGER_STATES = ("inbox", "active", "review", "promoted", "escalated")

# Frame fields required at the parent boundary (mirrors 07-contracts.md
# current_task.json table and harness/wrapper.py REQUIRED_FIELDS).
REQUIRED_FRAME_FIELDS = [
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

try:  # Canonical sensor suite (see specs/05-sensors.md); guarded for offline import.
    from sensors import REVIEW_SKIPPED_ANNOTATION, review_commit, sensor_review
except ImportError:
    try:
        from temporal.sensors import REVIEW_SKIPPED_ANNOTATION, review_commit, sensor_review
    except ImportError:
        # Offline fallback when the sensors module is unavailable: the
        # logged no-op annotation stays defined so the gate below still
        # degrades loudly instead of skipping silently.
        REVIEW_SKIPPED_ANNOTATION = "review: skipped, no sensors configured"
        review_commit = None  # type: ignore[assignment]
        sensor_review = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Pure helpers (stdlib-only; no Temporal dependency)
# ---------------------------------------------------------------------------


def load_frame(path: str | Path) -> tuple[dict[str, Any] | None, str | None]:
    """Load + validate an inbox frame file. Returns (frame, error)."""
    p = Path(path)
    try:
        raw = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, f"frame not found: {p}"
    except OSError as e:
        return None, f"frame read error: {e}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"frame JSON invalid: {e}"
    if not isinstance(data, dict):
        return None, "frame JSON must be an object"
    missing = [f for f in REQUIRED_FRAME_FIELDS if f not in data]
    if missing:
        return None, f"frame missing required fields: {", ".join(missing)}"
    return data, None


def _utcnow_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def initial_ledger_entry(
    frame: dict[str, Any],
    child_workflow_id: str,
    state: str = "active",
    updated_at: str | None = None,
) -> dict[str, Any]:
    """Build the Temporal-owned ledger row for a newly opened task.

    The checked-in tasks/ledger.md projection is rendered from rows like
    this one — never hand-edited (see 02 ledger + 07 PROGRESS.md rules).

    `updated_at` defaults to now for direct callers; pass "" when the
    entry is built inside workflow code — wall-clock reads break Temporal
    replay determinism, so the projection activity stamps the real time
    at write (see the ledger write-path block below).
    """
    if state not in LEDGER_STATES:
        raise ValueError(f"unknown ledger state: {state}")
    return {
        "task_id": frame["task_id"],
        "state": state,
        "attempt": frame.get("attempt", 1),
        "max_attempts": frame.get("max_attempts", 5),
        "child_workflow_id": child_workflow_id,
        "commit_shas": [],
        "final_receipt": None,
        "pr_url": None,
        "updated_at": updated_at if updated_at is not None else _utcnow_iso(),
    }


def review_gate(
    receipt_status: str,
    sensors_configured: bool = False,
    block_findings: int = 0,
) -> tuple[str, str]:
    """PoC sensor review gate (02 sensor-only, degrading to deferred).

    Returns (next_state, annotation). Thin wrapper over
    sensors.review_commit() (see specs/05-sensors.md): no sensors run, so
    a SUCCESS receipt degrades to the logged no-op and proceeds to the
    promotion queue. Block-mapped findings re-enter active as a
    remediation attempt; advise-only findings proceed with context
    attached (caller attaches). Non-SUCCESS receipts never reach this
    gate (see decide_terminal).
    """
    if receipt_status != "SUCCESS":
        raise ValueError(f"review_gate takes SUCCESS receipts only, got {receipt_status}")
    if _review_commit_available():
        findings = _synthetic_findings(block_findings) if sensors_configured else None
        receipt: dict[str, Any] = {
            "status": receipt_status,
            # Synthetic findings live on a placeholder diff path so the
            # canonical diff-scope rule keeps them (legacy count bridge).
            "files_changed": ["__diff__"] if findings else [],
        }
        next_state, annotation, _ = review_commit(receipt, findings)
        return next_state, annotation
    if not sensors_configured:
        return "promoted", REVIEW_SKIPPED_ANNOTATION
    if block_findings > 0:
        return "active", f"review: {block_findings} block finding(s), remediation re-entry"
    return "promoted", "review: advise-only, proceeding to promotion"


def _review_commit_available() -> bool:
    """Whether the canonical sensors module imported (offline fallback?)."""
    return callable(review_commit)


def _synthetic_findings(block_findings: int) -> list[dict[str, Any]]:
    """Bridge int counts to the sensors contract for the legacy signature.

    review_gate() predates the finding-list contract; when callers pass a
    bare block count, synthesize minimal diff-scoped block findings so the
    canonical review_commit() drives the verdict (block/advise split
    ready). Real findings flow via the sensor_review activity instead.
    """
    try:
        n = int(block_findings)
    except (TypeError, ValueError):
        n = 0
    return [
        {
            "tool_name": "SonarQube",
            "rule_id": "synthetic",
            "file_path": "__diff__",
            "line_number": 1,
            "severity": "blocker",
            "message": "synthetic block finding (legacy count bridge)",
        }
        for _ in range(max(n, 0))
    ]


def decide_terminal(receipt: dict[str, Any]) -> str | None:
    """Map a child receipt to a terminal escalation state, if any.

    HALT:EXHAUSTED and HALT:BLOCKED land as `escalated` with the final
    receipt attached, awaiting human triage — never auto-retried, never
    dropped (see 02 escalation handling). Returns None when the receipt
    is not terminal (SUCCESS / RETRYABLE_FAILURE continue the loop).
    """
    promise = receipt.get("exit_promise")
    if promise in ("HALT:EXHAUSTED", "HALT:BLOCKED"):
        return "escalated"
    return None


def render_ledger_row(entry: dict[str, Any]) -> str:
    """Render one markdown table row for the tasks/ledger.md projection."""
    shas = entry.get("commit_shas") or []
    receipt = entry.get("final_receipt")
    if isinstance(receipt, dict):
        receipt_str = f"{receipt.get('status', '?')}/{receipt.get('exit_promise', '?')}"
    elif receipt is None:
        receipt_str = "-"
    else:
        receipt_str = str(receipt)
    return (
        f"| {entry.get('task_id', '?')} "
        f"| {entry.get('state', '?')} "
        f"| {entry.get('attempt', '?')}/{entry.get('max_attempts', '?')} "
        f"| {entry.get('child_workflow_id', '-')} "
        f"| {", ".join(shas) if shas else "-"} "
        f"| {receipt_str} "
        f"| {entry.get('pr_url') or "-"} "
        f"| {entry.get('updated_at', '-')} |"
    )


# ---------------------------------------------------------------------------
# Ledger projection write path: Temporal-rendered tasks/ledger.md (see 02)
# ---------------------------------------------------------------------------
#
# Temporal workflow state is the source of truth (see 01-principles.md); the
# checked-in tasks/ledger.md is a PoC-readable projection — never hand-edited
# (see 02 ledger + tasks/inbox/README.md). This block is the write path the
# projection stub was waiting for:
#
#   pure helpers (stdlib-only, deterministic — safe to call from workflows):
#     update_ledger_entry / receipt_summary / render_ledger_file /
#     upsert_ledger_row_text
#   IO edge (activities only, never from workflow code):
#     project_ledger_impl stamps updated_at + atomic-writes one row;
#     the project_ledger activity wraps it off the event loop.
#
# updated_at is stamped in the activity, not in workflow code: wall-clock
# reads inside a workflow break Temporal replay determinism, while an
# activity may be non-deterministic. Workflow-built entries carry "" and the
# projected file row always gets a fresh stamp.
#
# Merge is line-level (replace the `| task_id |...` row, else append): each
# single-task parent run upserts only its own row, so sibling task rows
# survive byte-for-byte and no markdown-table reparse is needed. Writes are
# atomic (tmp file in the same dir + os.replace) so a crashed projection
# never leaves a half-written ledger.

LEDGER_DIRNAME = "tasks"
LEDGER_FILENAME = "ledger.md"

# Verbatim copy of the checked-in ledger.md header: projections into a
# missing/empty ledger reproduce it byte-for-byte (existing files keep
# their own header — upsert only touches the task row).
LEDGER_FILE_PREAMBLE = (
    "# Task Ledger — Temporal projection (PoC stub)\n"
    "\n"
    "> Temporal workflow state is the source of truth (see `specs/01-principles.md`).\n"
    "> This file is a Temporal-rendered projection — never hand-edit\n"
    "> (see `specs/02-control-plane.md` ledger). Seed stub until the parent\n"
    "> workflow projects live rows. Task states:\n"
    "> `inbox → active → review → promoted | escalated`."
)
LEDGER_TABLE_HEADER = (
    "| task_id | state | attempt/max_attempts | child_workflow_id "
    "| commit_shas | final_receipt | pr_url | updated_at |"
)
LEDGER_TABLE_SEPARATOR = (
    "|---------|-------|----------------------|-------------------|"
    "-------------|---------------|--------|------------|"
)

# First table cell of a `| ... |` line (header, separator, and task rows
# all match; callers skip the header/separator explicitly).
_ROW_FIRST_CELL_RE = re.compile(r"^\|\s*([^|]+?)\s*\|")


def ledger_path_default() -> str:
    """Resolve tasks/ledger.md (env LEDGER_PATH wins, repo-root fallback).

    Laptop-local per 02 locality: the worker runs on the owner's machine,
    so the projection lands in the repo checkout. Env override covers
    tests and isolated runs (same pattern as spawn_script_path in
    temporal/child.py).
    """
    env = os.environ.get("LEDGER_PATH")
    if env and env.strip():
        return env.strip()
    try:
        here = Path(__file__).resolve()
        candidate = here.parent.parent / LEDGER_DIRNAME / LEDGER_FILENAME
        return str(candidate)
    except Exception:
        return os.path.join(LEDGER_DIRNAME, LEDGER_FILENAME)


def update_ledger_entry(
    entry: dict[str, Any],
    *,
    state: str | None = None,
    attempt: int | None = None,
    commit_sha: str | None = None,
    receipt: dict[str, Any] | None = None,
    pr_url: str | None = None,
) -> dict[str, Any]:
    """Return an updated copy of a ledger entry (pure; no IO, no clock).

    - state must be one of LEDGER_STATES (unknown -> ValueError).
    - commit_sha appends to commit_shas (order-kept, blank/duplicates
      skipped) — per-attempt local SHAs from receipts (see 02 ledger).
    - receipt is the final_receipt summary ({status, exit_promise} — the
      row renderer prints dicts as `status/exit_promise`; the full
      receipt stays in Temporal history).
    - pr_url sets the promotion link (None leaves it untouched).
    - updated_at is NOT bumped here — the projection activity stamps it
      at write time so workflow code stays replay-deterministic.
    """
    fresh = dict(entry)
    if state is not None:
        if state not in LEDGER_STATES:
            raise ValueError(f"unknown ledger state: {state}")
        fresh["state"] = state
    if attempt is not None:
        try:
            n = int(attempt)
        except (TypeError, ValueError):
            raise ValueError(f"attempt must be an integer, got {attempt!r}")
        if n < 1:
            raise ValueError(f"attempt must be >= 1, got {attempt!r}")
        fresh["attempt"] = n
    if commit_sha:
        sha = str(commit_sha).strip()
        if sha:
            shas = list(fresh.get("commit_shas") or [])
            if sha not in shas:
                shas.append(sha)
            fresh["commit_shas"] = shas
    if receipt is not None:
        if not isinstance(receipt, dict):
            raise ValueError("receipt must be an object")
        fresh["final_receipt"] = dict(receipt)
    if pr_url is not None:
        if not isinstance(pr_url, str) or not pr_url.strip():
            raise ValueError("pr_url must be a non-empty string")
        fresh["pr_url"] = pr_url.strip()
    return fresh


def receipt_summary(receipt: dict[str, Any]) -> dict[str, str]:
    """Ledger-sized receipt digest ({status, exit_promise}) for final_receipt."""
    return {
        "status": str(receipt.get("status", "?")),
        "exit_promise": str(receipt.get("exit_promise", "?")),
    }


def render_ledger_file(entries: list[dict[str, Any]]) -> str:
    """Render the full ledger.md projection (preamble + table, by task_id)."""
    rows = sorted(entries, key=lambda e: str(e.get("task_id", "?")))
    lines = [
        LEDGER_FILE_PREAMBLE.rstrip("\n"),
        "",
        LEDGER_TABLE_HEADER,
        LEDGER_TABLE_SEPARATOR,
    ]
    lines += [render_ledger_row(e) for e in rows]
    return "\n".join(lines) + "\n"


def _is_separator_row(line: str) -> bool:
    cells = line.strip().replace("|", "").replace(" ", "")
    return bool(cells) and set(cells) <= {"-", ":"}


def upsert_ledger_row_text(existing_text: str, entry: dict[str, Any]) -> str:
    """Merge one rendered row into existing ledger markdown (pure).

    Replaces the `| task_id |...` line when present, else inserts it after
    the table separator (or appends a fresh preamble + table block when the
    file has none — e.g. first projection into a missing ledger). All other
    lines pass through untouched, so sibling task rows survive.
    """
    task_id = str(entry.get("task_id", "")).strip()
    if not task_id:
        raise ValueError("upsert_ledger_row_text: entry needs a non-empty task_id")
    row = render_ledger_row(entry)
    lines = (existing_text or "").splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        m = _ROW_FIRST_CELL_RE.match(line)
        if not m:
            continue
        first = m.group(1).strip()
        if first == "task_id" or _is_separator_row(line):
            continue
        if first == task_id:
            lines[i] = row
            return "\n".join(lines) + "\n"
    for i, line in enumerate(lines):
        if line.startswith("|") and _is_separator_row(line):
            lines.insert(i + 1, row)
            return "\n".join(lines) + "\n"
    block = ["", LEDGER_TABLE_HEADER, LEDGER_TABLE_SEPARATOR, row] if lines else [
        LEDGER_FILE_PREAMBLE,
        "",
        LEDGER_TABLE_HEADER,
        LEDGER_TABLE_SEPARATOR,
        row,
    ]
    return "\n".join(lines + block) + "\n"


def project_ledger_impl(
    entry: dict[str, Any],
    ledger_path: str | Path | None = None,
) -> dict[str, str]:
    """Project one ledger entry into tasks/ledger.md (IO edge: activity only).

    Reads the current file (missing -> fresh), upserts the entry's row,
    stamps updated_at on the projected copy, and atomic-writes (tmp file
    in the same dir + os.replace). Returns {"ledger_path", "task_id",
    "state"}. Raises ValueError on bad entries, RuntimeError on IO
    failure (Temporal retries the activity).
    """
    if not isinstance(entry, dict):
        raise ValueError("project_ledger: entry must be an object")
    task_id = str(entry.get("task_id", "")).strip()
    if not task_id:
        raise ValueError("project_ledger: entry needs a non-empty task_id")
    state = entry.get("state")
    if state not in LEDGER_STATES:
        raise ValueError(f"project_ledger: unknown ledger state: {state!r}")
    raw_path = str(ledger_path).strip() if ledger_path else ""
    path = Path(raw_path or ledger_path_default())
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise RuntimeError(f"project_ledger: cannot create {path.parent}: {e}")
    try:
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError as e:
        raise RuntimeError(f"project_ledger: read failed for {path}: {e}")
    projected = dict(entry)
    projected["task_id"] = task_id
    projected["updated_at"] = _utcnow_iso()
    new_text = upsert_ledger_row_text(existing, projected)
    try:
        fd, tmp = tempfile.mkstemp(
            dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(new_text)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError as e:
        raise RuntimeError(f"project_ledger: write failed for {path}: {e}")
    return {"ledger_path": str(path), "task_id": task_id, "state": str(state)}


# ---------------------------------------------------------------------------
# Promotion: Tier-1 host-side push only (see specs/02-control-plane.md)
# ---------------------------------------------------------------------------
#
# Single transfer path (locked): the cell never pushes and holds no git
# credentials; this chain runs on the host with the owner's `gh` auth.
# Steps: bundle-download (local `git bundle create` in-cell + `sandbox
# download`, no credentials) -> fetch into the host's `target_branch`
# checkout of the frame's `repo_url` -> secret-scan before anything touches
# origin (halt for human triage) -> squash per-attempt commits into one
# clean commit -> push `target_branch` -> open a draft PR seeded from the
# receipt's `agent_summary` plus gate evidence.
#
# Ordering constraint (see 02): the bundle download consumes cell content,
# so the caller must run promotion BEFORE the terminal-state cell delete —
# ledger SHAs are useless once the cell is gone. Never `--force` on push:
# a non-fast-forward push escalates for human triage instead of rewriting
# origin history.

# PR base default. The frame carries no base field in the PoC; `main` is the
# documented assumption (override per call via payload `base_branch`).
PROMOTION_BASE_BRANCH_DEFAULT = "main"

# Local ref the downloaded bundle is fetched to before the squash merge.
BUNDLE_CANDIDATE_REF = "refs/bundle/candidate"

# In-cell checkout (see 04 spawn contract: workspace seed uploads to
# /sandbox/repo). Env override covers driver layout drift.
CELL_REPO_DEFAULT = "/sandbox/repo"

# Wall-clock per in-cell/local git op (bundle create/verify/fetch are fast
# local ops; Temporal activity timeouts bound the outermost layer).
CELL_EXEC_TIMEOUT_SECONDS = 120
VERIFY_TIMEOUT_SECONDS = 120
FETCH_TIMEOUT_SECONDS = 120
SCAN_TIMEOUT_SECONDS = 120
COMMIT_TIMEOUT_SECONDS = 120

# Network ops: push of a small PoC branch + one `gh` API call.
PUSH_TIMEOUT_SECONDS = 300
PR_TIMEOUT_SECONDS = 120
CLONE_TIMEOUT_SECONDS = 300

# Non-secret commit identity, mirroring harness/wrapper.py and
# temporal/child.py (nothing else sets it on a fresh host checkout).
GIT_IDENTITY_NAME = "Ralph Worker"
GIT_IDENTITY_EMAIL = "ralph-worker@localhost"

# Builtin secret patterns ("gitleaks-equivalent", see 02). Findings halt
# promotion for human triage — the cell env holds injected secrets that
# must never reach origin. Only the pattern NAME + line number are
# reported; matched values are never echoed into logs or annotations.
# Tunable with evidence (a real gitleaks binary is the documented swap,
# not a second scanner running alongside this set).
SECRET_PATTERNS: tuple[tuple[str, str], ...] = (
    ("OPENCODE_API_KEY", r"OPENCODE_API_KEY\s*[:=]"),
    ("ANTHROPIC_API_KEY", r"ANTHROPIC_API_KEY\s*[:=]"),
    ("GITHUB_PAT", r"ghp_[A-Za-z0-9]{10,}"),
    ("GITHUB_OAUTH", r"gho_[A-Za-z0-9]{10,}"),
    ("GITHUB_FINE_GRAINED_PAT", r"github_pat_[A-Za-z0-9_]{10,}"),
    ("AWS_ACCESS_KEY", r"AKIA[0-9A-Z]{16}"),
    ("PRIVATE_KEY", r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    ("GENERIC_API_KEY_ASSIGN", r"(?i)\bapi[_-]?key\b\s*[:=]\s*['\"]?\S{8,}"),
    ("GENERIC_SECRET_ASSIGN", r"(?i)\b(secret|token|password)\b\s*[:=]\s*['\"]?\S{8,}"),
)


class PromotionBlocked(Exception):
    """Candidate secret-scan findings halt promotion for human triage.

    Carries `findings` (pattern names + line numbers only — never secret
    values). The workflow maps this to `escalated`, never a retry loop.
    """

    def __init__(self, findings: list[str]):
        super().__init__(
            f"promotion blocked: {len(findings)} secret finding(s): "
            + "; ".join(findings[:10])
        )
        self.findings = list(findings)


def openshell_bin() -> str:
    """Local openshell CLI (env override wins, for tests/dev gateways)."""
    env = os.environ.get("OPENSHELL_BIN")
    if env and env.strip():
        return env.strip()
    return "openshell"


def gh_bin() -> str:
    """Host `gh` CLI (env override wins, for tests/shims)."""
    env = os.environ.get("GH_BIN")
    if env and env.strip():
        return env.strip()
    return "gh"


def cell_repo_path() -> str:
    """In-cell checkout path (env override wins)."""
    env = os.environ.get("CELL_REPO_PATH")
    if env and env.strip():
        return env.strip()
    return CELL_REPO_DEFAULT


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


def _validate_branch(value: Any, field: str) -> str | None:
    """Single git ref only: rejects empty values, leading dashes (parsed
    as flags, not refs) and whitespace (multi-token ref)."""
    if not isinstance(value, str) or not value.strip():
        return f"{field} must be a non-empty string"
    v = value.strip()
    if v.startswith("-"):
        return f"{field} must be a ref, not a flag: {v!r}"
    if any(c.isspace() for c in v):
        return f"{field} must be a single ref: {v!r}"
    return None


def validate_promotion_payload(payload: Any) -> str | None:
    """Check the open_draft_pr payload. Returns an error string, or None.

    Payload contract (locked by this item)::
        {"frame": {...}, "receipt": {...},
         "host_checkout": "/path" (optional),
         "bundle_path": "/path/to.bundle" (optional),
         "cell": "cell-TASK-..." (optional),
         "base_branch": "main" (optional),
         "review_annotation": str (optional)}

    Exactly one candidate source resolution must be possible: an explicit
    `bundle_path`, else a live `cell` to download the bundle from (see
    the ordering constraint above). Only fully-gated `SUCCESS` receipts
    promote (see 02 failure modes); anything else is a caller bug.
    """
    if not isinstance(payload, dict):
        return "promotion payload must be an object"
    frame = payload.get("frame")
    receipt = payload.get("receipt")
    if not isinstance(frame, dict):
        return "promotion payload needs frame object"
    if not isinstance(receipt, dict):
        return "promotion payload needs receipt object"
    task_id = frame.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        return "frame task_id must be a non-empty string"
    err = validate_repo_url(frame.get("repo_url"))
    if err is not None:
        return f"frame {err}"
    err = _validate_branch(frame.get("target_branch"), "frame target_branch")
    if err is not None:
        return err
    if receipt.get("status") != "SUCCESS":
        return (
            "promotion takes SUCCESS receipts only "
            f"(got {receipt.get('status')!r}); only fully-gated SUCCESS promotes"
        )
    rtid = receipt.get("task_id")
    if rtid is not None and rtid != task_id:
        return f"receipt task_id {rtid!r} does not match frame {task_id!r}"
    base = payload.get("base_branch", frame.get("base_branch", PROMOTION_BASE_BRANCH_DEFAULT))
    if base is None:
        base = PROMOTION_BASE_BRANCH_DEFAULT
    err = _validate_branch(base, "base_branch")
    if err is not None:
        return err
    checkout = payload.get("host_checkout")
    if checkout is not None and (not isinstance(checkout, str) or not checkout.strip()):
        return "host_checkout must be a directory path string"
    cell = payload.get("cell")
    bundle = payload.get("bundle_path")
    if bundle is not None and (not isinstance(bundle, str) or not bundle.strip()):
        return "bundle_path must be a file path string"
    if cell is not None and (not isinstance(cell, str) or not cell.strip()):
        return "cell must be a sandbox name string"
    if (bundle is None or not str(bundle).strip()) and (
        cell is None or not str(cell).strip()
    ):
        return (
            "no candidate source: provide bundle_path (pre-downloaded) or "
            "cell (bundle download runs inside promotion, before cell delete)"
        )
    return None


def repo_slug_from_url(url: str) -> str | None:
    """Derive `owner/repo` from a public https repo URL for `gh --repo`.

    Returns None when the URL has no `owner/repo` path (validation of
    scheme/credentials stays in validate_repo_url).
    """
    try:
        path = str(url).strip().split("://", 1)[1].split("/", 1)[1]
    except IndexError:
        return None
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        return None
    repo = parts[1]
    if repo.endswith(".git"):
        repo = repo[: -len(".git")]
    if not parts[0] or not repo:
        return None
    return f"{parts[0]}/{repo}"


def squash_message(task_id: str, title: Any) -> str:
    """One clean commit message for the promotion squash (see 02 model).

    Format mirrors the spec example: `fix(TASK-402): sanitize search
    input` — first title line only, capped so `gh`/git stay happy.
    """
    first = str(title or "").strip().splitlines()
    subject = first[0].strip() if first and first[0].strip() else "promotion candidate"
    return f"fix({str(task_id).strip()}): {subject}"[:200]


def build_pr_body(
    receipt: dict[str, Any],
    review_annotation: Any = "",
    max_chars: int = 8000,
) -> str:
    """Seed the draft PR body from `agent_summary` + gate evidence (02).

    Tactile command/exit, sensor review annotation, files changed and the
    candidate SHA ride along so the human reviewer sees what the loop
    verified without digging through Temporal history.
    """
    tactile = receipt.get("tactile_execution") or {}
    lines = [
        "## Summary",
        "",
        str(receipt.get("agent_summary", "(no summary)") or "(no summary)"),
        "",
        "## Gate evidence",
        "",
        f"- tactile: `{tactile.get('command_run', '?')}` "
        f"exit {tactile.get('exit_code', '?')}",
        f"- review: {str(review_annotation or '-').strip()}",
        f"- commit: {receipt.get('commit_sha', '?')}",
        f"- files: {', '.join(receipt.get('files_changed') or ['-'])}",
        f"- task: {receipt.get('task_id', '?')}",
    ]
    tail = str(tactile.get("summary_output", "") or "").strip()
    if tail:
        lines += ["", "### Tactile output (tail)", "", "```", tail[-2000:], "```"]
    body = "\n".join(lines).strip() + "\n"
    if len(body) > max_chars:
        body = body[:max_chars] + "\n…(truncated)\n"
    return body


def scan_text_for_secrets(text: str) -> list[str]:
    """Scan text for secret patterns. Returns finding descriptions.

    Each finding is `"<line N>: <PATTERN_NAME> suspected"` — pattern
    names and line numbers only, never matched values.
    """
    findings: list[str] = []
    compiled = [(name, re.compile(rx)) for name, rx in SECRET_PATTERNS]
    for i, line in enumerate(str(text or "").splitlines(), start=1):
        for name, rx in compiled:
            try:
                if rx.search(line):
                    findings.append(f"line {i}: {name} suspected")
                    break
            except re.error:
                continue
    return findings


def _run_checked(
    argv: list[str],
    cwd: str | None = None,
    timeout: int = 120,
    runner: Any | None = None,
    label: str = "command",
) -> Any:
    """Run fixed argv (no shell) and raise on failure. Returns the result.

    `runner` injects subprocess.run for offline tests. Raises
    RuntimeError with a stderr tail on nonzero exit (Temporal retries
    the activity); missing binaries surface as RuntimeError, never a
    silent skip.
    """
    run = runner or subprocess.run
    try:
        r = run(list(argv), capture_output=True, text=True, timeout=timeout, cwd=cwd)
    except FileNotFoundError as e:
        raise RuntimeError(f"{label}: binary not found: {e}")
    if r.returncode != 0:
        detail = (r.stderr or r.stdout or "").strip()
        raise RuntimeError(f"{label} failed: {detail}"[:2000])
    return r


def bundle_remote_name(task_id: str) -> str:
    """In-cell bundle path for a task (under /sandbox, outside the repo)."""
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "-" for c in str(task_id))
    return f"/sandbox/bundle-{(safe or 'task')}.bundle"


def download_bundle_impl(
    cell: str,
    task_id: str,
    out_dir: str | Path,
    repo: str | None = None,
    runner: Any | None = None,
) -> str:
    """Create the candidate bundle in-cell and download it to the host.

    `git bundle create` is a local op needing no credentials (see 02);
    the bundle transfer is lossless (binaries, modes, renames, history).
    Returns the host bundle path. Must run BEFORE the terminal-state
    cell delete (see ordering constraint above).
    """
    name = str(cell or "").strip()
    if not name:
        raise ValueError("download_bundle: empty cell name")
    remote = bundle_remote_name(task_id)
    target = str(repo or cell_repo_path())
    _run_checked(
        [
            openshell_bin(),
            "sandbox",
            "exec",
            "-n",
            name,
            "--workdir",
            target,
            "--timeout",
            str(CELL_EXEC_TIMEOUT_SECONDS),
            "--",
            "git",
            "bundle",
            "create",
            remote,
            "HEAD",
        ],
        timeout=CELL_EXEC_TIMEOUT_SECONDS + 60,
        runner=runner,
        label="cell git bundle create",
    )
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    _run_checked(
        [openshell_bin(), "sandbox", "download", name, remote, str(out) + "/"],
        timeout=CELL_EXEC_TIMEOUT_SECONDS + 60,
        runner=runner,
        label="sandbox download bundle",
    )
    host_path = out / Path(remote).name
    if host_path.is_file():
        return str(host_path)
    cands = sorted(out.glob("*.bundle"))
    if not cands:
        raise RuntimeError(f"bundle download produced no file in {out}")
    return str(cands[0])


def ensure_host_checkout(
    frame: dict[str, Any],
    host_checkout: Any | None = None,
    runner: Any | None = None,
) -> str:
    """Resolve the host `target_branch` checkout of the frame's repo_url.

    Uses the provided checkout when given (must exist); otherwise clones
    the public https `repo_url` into a fresh temp dir — no credentials
    are ever passed (auth lives only in the provider-injected cell env
    and the owner's host `gh`, see 04 ingestion). New demo branches that
    do not exist on the remote yet start from the clone HEAD
    (`checkout -B`), mirroring temporal/child.py prepare_workspace.
    """
    branch = str(frame.get("target_branch") or "").strip()
    if host_checkout is not None and str(host_checkout).strip():
        checkout = str(host_checkout).strip()
        if not Path(checkout).is_dir():
            raise RuntimeError(f"host_checkout not a directory: {checkout}")
        try:
            _run_checked(
                ["git", "checkout", branch],
                cwd=checkout,
                timeout=60,
                runner=runner,
                label=f"git checkout {branch}",
            )
        except RuntimeError:
            _run_checked(
                ["git", "checkout", "-B", branch],
                cwd=checkout,
                timeout=60,
                runner=runner,
                label=f"git checkout -B {branch}",
            )
        return checkout
    url = str(frame.get("repo_url") or "").strip()
    dest = tempfile.mkdtemp(prefix="ralph-promote-")
    _run_checked(
        ["git", "clone", url, dest],
        timeout=CLONE_TIMEOUT_SECONDS,
        runner=runner,
        label="git clone",
    )
    try:
        _run_checked(
            ["git", "-C", dest, "checkout", branch],
            timeout=60,
            runner=runner,
            label=f"git checkout {branch}",
        )
    except RuntimeError:
        _run_checked(
            ["git", "-C", dest, "checkout", "-B", branch],
            timeout=60,
            runner=runner,
            label=f"git checkout -B {branch}",
        )
    return dest


def fetch_and_stage_impl(
    host_checkout: str,
    bundle_path: str,
    target_branch: str,
    runner: Any | None = None,
) -> str:
    """Verify the bundle, fetch it, and squash-merge it onto target_branch.

    `git merge --squash` stages the full candidate diff without
    committing, so the secret scan below inspects exactly what the
    squash commit would record. Returns the candidate ref.
    """
    checkout = str(host_checkout)
    bundle = str(bundle_path)
    if not Path(bundle).is_file():
        raise RuntimeError(f"bundle not found: {bundle}")
    _run_checked(
        ["git", "bundle", "verify", bundle],
        cwd=checkout,
        timeout=VERIFY_TIMEOUT_SECONDS,
        runner=runner,
        label="git bundle verify",
    )
    _run_checked(
        ["git", "fetch", bundle, f"HEAD:{BUNDLE_CANDIDATE_REF}"],
        cwd=checkout,
        timeout=FETCH_TIMEOUT_SECONDS,
        runner=runner,
        label="git fetch bundle",
    )
    try:
        _run_checked(
            ["git", "checkout", str(target_branch)],
            cwd=checkout,
            timeout=60,
            runner=runner,
            label=f"git checkout {target_branch}",
        )
    except RuntimeError:
        _run_checked(
            ["git", "checkout", "-B", str(target_branch)],
            cwd=checkout,
            timeout=60,
            runner=runner,
            label=f"git checkout -B {target_branch}",
        )
    _run_checked(
        ["git", "merge", "--squash", BUNDLE_CANDIDATE_REF],
        cwd=checkout,
        timeout=FETCH_TIMEOUT_SECONDS,
        runner=runner,
        label="git merge --squash",
    )
    return BUNDLE_CANDIDATE_REF


def scan_staged_impl(
    host_checkout: str,
    runner: Any | None = None,
) -> list[str]:
    """Secret-scan the staged candidate diff + untracked content.

    Runs BEFORE the squash commit or any push touches origin (see 02):
    findings raise PromotionBlocked for human triage (never auto-push,
    never silently dropped). Untracked files are scanned too — a fresh
    clone has none, so any hit there names operator dirt, not the agent.
    Finding entries carry pattern names + line numbers only.
    """
    checkout = str(host_checkout)
    cached = _run_checked(
        ["git", "diff", "--cached"],
        cwd=checkout,
        timeout=SCAN_TIMEOUT_SECONDS,
        runner=runner,
        label="git diff --cached",
    )
    unstaged = _run_checked(
        ["git", "diff"],
        cwd=checkout,
        timeout=SCAN_TIMEOUT_SECONDS,
        runner=runner,
        label="git diff",
    )
    findings = scan_text_for_secrets((cached.stdout or "") + "\n" + (unstaged.stdout or ""))
    status = _run_checked(
        ["git", "status", "--porcelain"],
        cwd=checkout,
        timeout=60,
        runner=runner,
        label="git status",
    )
    for line in (status.stdout or "").splitlines():
        if line.startswith("??"):
            rel = line[2:].strip().strip('"')
            p = Path(checkout) / rel
            try:
                if p.is_file() and p.stat().st_size < 1_000_000:
                    findings += [
                        f"{rel} {f}" for f in scan_text_for_secrets(
                            p.read_text(encoding="utf-8", errors="replace")
                        )
                    ]
            except OSError:
                continue
    if findings:
        raise PromotionBlocked(findings)
    return findings


def squash_commit_impl(
    host_checkout: str,
    message: str,
    runner: Any | None = None,
) -> str:
    """Commit the staged candidate as one clean commit (no push here).

    Refuses an empty stage (nothing fetched — a caller bug, not an
    empty task). Returns the squash commit SHA.
    """
    checkout = str(host_checkout)
    if not str(message).strip():
        raise ValueError("squash_commit: empty message")
    names = _run_checked(
        ["git", "diff", "--cached", "--name-only"],
        cwd=checkout,
        timeout=60,
        runner=runner,
        label="git diff --cached --name-only",
    )
    if not (names.stdout or "").strip():
        raise RuntimeError("nothing staged to squash — candidate fetch staged no changes")
    _run_checked(
        ["git", "config", "user.name", GIT_IDENTITY_NAME],
        cwd=checkout,
        timeout=60,
        runner=runner,
        label="git config user.name",
    )
    _run_checked(
        ["git", "config", "user.email", GIT_IDENTITY_EMAIL],
        cwd=checkout,
        timeout=60,
        runner=runner,
        label="git config user.email",
    )
    _run_checked(
        ["git", "commit", "-m", str(message).strip()],
        cwd=checkout,
        timeout=COMMIT_TIMEOUT_SECONDS,
        runner=runner,
        label="git commit squash",
    )
    head = _run_checked(
        ["git", "rev-parse", "HEAD"],
        cwd=checkout,
        timeout=60,
        runner=runner,
        label="git rev-parse HEAD",
    )
    sha = (head.stdout or "").strip()
    if not sha:
        raise RuntimeError("squash commit left empty HEAD")
    return sha


def push_branch_impl(
    host_checkout: str,
    target_branch: str,
    runner: Any | None = None,
) -> None:
    """Push `target_branch` to the frame origin. Never `--force`.

    A non-fast-forward push (stale branch from an earlier run) fails
    here and escalates for human triage instead of rewriting origin
    history (see 03: no force-push races).
    """
    _run_checked(
        ["git", "push", "origin", str(target_branch)],
        cwd=str(host_checkout),
        timeout=PUSH_TIMEOUT_SECONDS,
        runner=runner,
        label="git push origin",
    )


def _parse_pr_url(output: str) -> str:
    """Extract the PR URL from `gh pr create` stdout."""
    m = re.search(r"https://\S+/pull/\d+", str(output or ""))
    if not m:
        raise RuntimeError(
            f"gh pr create printed no PR URL: {str(output or '').strip()}"[:500]
        )
    return m.group(0)


def open_pr_impl(
    repo_slug: str,
    head_branch: str,
    base_branch: str,
    title: str,
    body: str,
    cwd: str | None = None,
    runner: Any | None = None,
) -> str:
    """Open a DRAFT PR via `gh` (host auth — never in-cell, see 04).

    The human promotes draft → ready (mechanism = Temporal pushes and
    opens; draft status = the safety catch, see 02). Returns the PR URL.
    """
    body_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(body)
            body_file = fh.name
        r = _run_checked(
            [
                gh_bin(),
                "pr",
                "create",
                "--repo",
                str(repo_slug),
                "--head",
                str(head_branch),
                "--base",
                str(base_branch),
                "--draft",
                "--title",
                str(title),
                "--body-file",
                body_file,
            ],
            cwd=cwd,
            timeout=PR_TIMEOUT_SECONDS,
            runner=runner,
            label="gh pr create",
        )
    finally:
        if body_file:
            try:
                os.unlink(body_file)
            except OSError:
                pass
    return _parse_pr_url(r.stdout or "")


def promotion_impl(payload: dict[str, Any], runner: Any | None = None) -> dict[str, str]:
    """Run the full promotion chain; return the promotion record.

    Bundle-download (when `cell` is the source) runs first so cell
    content is consumed before any terminal-state delete (see ordering
    constraint). Secret findings raise PromotionBlocked BEFORE the
    squash commit or push — origin is never touched with secrets.
    Raises ValueError on bad payloads, RuntimeError on infra failures.
    """
    err = validate_promotion_payload(payload)
    if err is not None:
        raise ValueError(f"promotion: {err}")
    frame = payload["frame"]
    receipt = payload["receipt"]
    task_id = str(frame["task_id"]).strip()
    branch = str(frame["target_branch"]).strip()
    base = str(
        payload.get("base_branch")
        or frame.get("base_branch")
        or PROMOTION_BASE_BRANCH_DEFAULT
    ).strip()
    checkout = ensure_host_checkout(frame, payload.get("host_checkout"), runner)
    bundle = payload.get("bundle_path")
    if bundle is None or not str(bundle).strip():
        tmp = tempfile.mkdtemp(prefix="ralph-bundle-")
        bundle = download_bundle_impl(
            str(payload.get("cell")), task_id, tmp, None, runner
        )
    fetch_and_stage_impl(checkout, str(bundle), branch, runner)
    scan_staged_impl(checkout, runner)
    sha = squash_commit_impl(checkout, squash_message(task_id, frame.get("title", "")), runner)
    push_branch_impl(checkout, branch, runner)
    slug = repo_slug_from_url(str(frame.get("repo_url")))
    if slug is None:
        raise RuntimeError(f"promotion: cannot derive owner/repo from repo_url")
    pr_url = open_pr_impl(
        slug,
        branch,
        base,
        squash_message(task_id, frame.get("title", "")),
        build_pr_body(receipt, payload.get("review_annotation", "")),
        checkout,
        runner,
    )
    return {
        "task_id": task_id,
        "target_branch": branch,
        "base_branch": base,
        "commit_sha": sha,
        "pr_url": pr_url,
        "squashed": "true",
    }


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


try:  # Child workflow (see specs/03-inner-loop.md); guarded for offline import.
    from child import ChildInputs, ChildWorkflow, destroy_cell
except ImportError:
    try:
        from temporal.child import ChildInputs, ChildWorkflow, destroy_cell
    except ImportError:
        ChildInputs = None  # type: ignore[assignment]
        ChildWorkflow = None  # type: ignore[assignment]
        destroy_cell = None  # type: ignore[assignment]


@dataclasses.dataclass
class ParentInputs:
    """One inbox file = one parent run (1:1 default, no decomposition)."""

    frame: dict[str, Any]
    inbox_path: str


@dataclasses.dataclass
class ParentResult:
    task_id: str
    state: str
    annotation: str


@activity.defn(name="dispatch_child")
async def dispatch_child(frame: dict[str, Any]) -> dict[str, Any]:
    """Legacy dispatch slot, superseded by ChildWorkflow (see 03-inner-loop.md).

    Kept registered for backwards compatibility; ParentWorkflow now spawns
    the child workflow directly (1 file = 1 ledger task = 1 child).
    """
    raise NotImplementedError(
        "dispatch_child superseded by temporal/child.py ChildWorkflow; "
        "ParentWorkflow spawns the child via execute_child_workflow."
    )


# Note: the `sensor_review` Temporal activity lives canonically in
# temporal/sensors.py (host-side review-gate suite, see 05 runtime home)
# and is re-exported here for backwards compatibility — ParentWorkflow
# below dispatches it by function reference, and worker.py registers the
# canonical definition. No duplicate @activity.defn here (one activity
# name, one definition).


async def _run_in_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a blocking stdlib call off the event loop (worker stays responsive)."""
    import asyncio as _asyncio

    return await _asyncio.to_thread(func, *args, **kwargs)


@activity.defn(name="open_draft_pr")
async def open_draft_pr(payload: dict[str, Any]) -> dict[str, str]:
    """Promotion activity: bundle-download -> fetch -> scan -> squash -> push -> draft PR.

    Runs on the host with the owner's `gh` auth (workers never push —
    network-enforced, see 04). Payload contract in
    validate_promotion_payload(). Secret findings raise PromotionBlocked
    for human triage (origin untouched); other failures raise so
    Temporal retries instead of promoting partial state (only
    fully-gated `SUCCESS` promotes, see 02 failure modes).
    """
    return await _run_in_thread(promotion_impl, dict(payload))


@activity.defn(name="project_ledger")
async def project_ledger(
    entry: dict[str, Any], ledger_path: str | None = None
) -> dict[str, str]:
    """Projection activity: upsert one ledger row into tasks/ledger.md.

    Runs on the laptop-local worker (see 02 locality) with the default
    repo-checkout path; `ledger_path` overrides it for tests and isolated
    runs. updated_at is stamped here at write time — never in workflow
    code (replay determinism). IO failure raises so Temporal retries
    instead of diverging silently from the checked-in projection.
    """
    return await _run_in_thread(project_ledger_impl, dict(entry), ledger_path)


@workflow.defn(name="ParentWorkflow")
class ParentWorkflow:
    """Parent lifecycle stub: inbox -> active -> review -> promoted|escalated."""

    async def _project(self, entry: dict[str, Any]) -> str:
        """Project one ledger row; returns "" or a failure suffix for the annotation.

        The projection is derived state (Temporal history stays source of
        truth), so a failed write never fails the task — the gap rides the
        annotation instead of diverging silently (see 02 failure modes:
        ledger divergence; same pattern as the cell-delete annotation
        below). The entry keeps "" updated_at in workflow memory; the
        activity stamps the real time at write.
        """
        try:
            await workflow.execute_activity(
                project_ledger,
                entry,
                schedule_to_close_timeout=_dt.timedelta(minutes=2),
            )
        except Exception as e:
            return f" | ledger projection failed ({entry.get('task_id', '?')}): {e}"[:500]
        return ""

    @workflow.run
    async def run(self, inputs: ParentInputs) -> ParentResult:
        task_id = inputs.frame.get("task_id", "unknown")
        # SLA: 2h inbox-to-terminal wall-clock; breach auto-escalates with
        # partial evidence (timer + escalation wiring lands with the live
        # child loop; constant locked here per 02).
        _deadline = TASK_WALL_CLOCK_SECONDS  # noqa: F841 (consumed when live)
        # active: dispatch 1 file -> 1 child (no decomposition in PoC).
        child_id = f"child-{task_id}"
        child_cell = ""
        if ChildWorkflow is not None and ChildInputs is not None:
            child_result = await workflow.execute_child_workflow(
                ChildWorkflow.run,
                ChildInputs(frame=inputs.frame),
                id=child_id,
                task_queue=TASK_QUEUE,
            )
            receipt: dict[str, Any] = child_result.receipt
            # Cell handoff: on `complete` the child retains the cell and
            # returns its name so promotion downloads the bundle BEFORE
            # the terminal-state delete (see 02 ordering constraint).
            # Halt states delete in-child and return "" (nothing to promote).
            raw_cell = getattr(child_result, "cell", "") or ""
            child_cell = raw_cell.strip() if isinstance(raw_cell, str) else ""
        else:  # offline fallback (no child module): legacy activity slot.
            receipt = await workflow.execute_activity(
                dispatch_child,
                inputs.frame,
                schedule_to_close_timeout=_dt.timedelta(seconds=TASK_WALL_CLOCK_SECONDS),
            )
        # Ledger baseline: the task is active with the child dispatched
        # (1 file = 1 ledger task = 1 child, no decomposition in PoC).
        # updated_at="" here — the projection activity stamps the real
        # time at write so workflow code stays replay-deterministic.
        entry = initial_ledger_entry(inputs.frame, child_id, state="active", updated_at="")
        entry = update_ledger_entry(
            entry,
            commit_sha=receipt.get("commit_sha") if isinstance(receipt, dict) else None,
            receipt=receipt_summary(receipt) if isinstance(receipt, dict) else None,
        )
        # Terminal receipts escalate immediately (never retried, never dropped).
        terminal = decide_terminal(receipt)
        if terminal is not None:
            entry = update_ledger_entry(entry, state=terminal)
            annotation = f"{receipt.get('exit_promise')}: awaiting human triage"
            annotation += await self._project(entry)
            return ParentResult(
                task_id=task_id,
                state=terminal,
                annotation=annotation[:2000],
            )
        # review: sensor-only gate, degrading to deferred no-op in PoC.
        review = await workflow.execute_activity(
            sensor_review,
            receipt,
            schedule_to_close_timeout=_dt.timedelta(minutes=10),
        )
        if review["next_state"] != "promoted":
            entry = update_ledger_entry(entry, state=review["next_state"])
            annotation = str(review["annotation"]) + await self._project(entry)
            return ParentResult(
                task_id=task_id, state=review["next_state"], annotation=annotation[:2000]
            )
        # Promotion queue: host-side push + draft PR, but only when the
        # candidate source rides along (the child's retained `cell` for
        # bundle download, a frame `cell`, or a pre-downloaded
        # `bundle_path`). Frames without any source predate the
        # cell/bundle handoff — passthrough preserves PoC behavior until
        # the handoff lands.
        frame_cell = inputs.frame.get("cell")
        frame_cell = frame_cell.strip() if isinstance(frame_cell, str) else ""
        bundle_path = inputs.frame.get("bundle_path")
        bundle_path = bundle_path.strip() if isinstance(bundle_path, str) else ""
        cell = child_cell or frame_cell
        if not cell and not bundle_path:
            entry = update_ledger_entry(entry, state="promoted")
            annotation = str(review["annotation"]) + await self._project(entry)
            return ParentResult(
                task_id=task_id, state="promoted", annotation=annotation[:2000]
            )
        # The bundle download consumes cell content, so the cell is
        # deleted here — after promotion — never before (see the ordering
        # constraint above). Runs on a pre-downloaded bundle delete
        # nothing (no live cell was consumed).
        delete_after = bool(cell) and not bundle_path
        state, annotation = "promoted", str(review["annotation"])
        try:
            promo = await workflow.execute_activity(
                open_draft_pr,
                {
                    "frame": inputs.frame,
                    "receipt": receipt,
                    "review_annotation": review["annotation"],
                    "cell": cell or None,
                    "bundle_path": bundle_path or None,
                },
                schedule_to_close_timeout=_dt.timedelta(minutes=15),
            )
            annotation = f"{annotation} | {promo['pr_url']}"
            entry = update_ledger_entry(
                entry,
                state="promoted",
                pr_url=promo["pr_url"],
            )
        except Exception as e:
            # Promotion failure (secret halt or infra) awaits human triage
            # — never auto-retried into origin, never dropped (see 02
            # escalation handling).
            state = "escalated"
            annotation = f"promotion halted: {e}"
            entry = update_ledger_entry(entry, state="escalated")
        finally:
            if delete_after:
                if destroy_cell is not None:
                    try:
                        await workflow.execute_activity(
                            destroy_cell,
                            {"cell": cell},
                            schedule_to_close_timeout=_dt.timedelta(minutes=5),
                        )
                    except Exception as e:
                        annotation = f"{annotation} | cell delete failed ({cell}): {e}"
                else:  # offline fallback: orphan stays visible, never silent.
                    annotation = (
                        f"{annotation} | cell {cell} needs manual delete "
                        "(no destroy activity)"
                    )
        annotation += await self._project(entry)
        return ParentResult(
            task_id=task_id, state=state, annotation=annotation[:2000]
        )
