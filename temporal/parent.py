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
    -> promotion = draft PR via gh on the host (activity slot, see 02+06)
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
) -> dict[str, Any]:
    """Build the Temporal-owned ledger row for a newly opened task.

    The checked-in tasks/ledger.md projection is rendered from rows like
    this one — never hand-edited (see 02 ledger + 07 PROGRESS.md rules).
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
        "updated_at": _utcnow_iso(),
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
    from child import ChildInputs, ChildWorkflow
except ImportError:
    try:
        from temporal.child import ChildInputs, ChildWorkflow
    except ImportError:
        ChildInputs = None  # type: ignore[assignment]
        ChildWorkflow = None  # type: ignore[assignment]


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


@activity.defn(name="open_draft_pr")
async def open_draft_pr(task_id: str, commit_sha: str) -> dict[str, str]:
    """Promotion slot: squash + push target_branch + open draft PR via gh.

    Runs on the host (workers never push — network-enforced, see 04).
    Not executed in this stub item; implemented with 06-release.md.
    """
    raise NotImplementedError(
        "promotion activity not yet implemented "
        "(see specs/02-control-plane.md promotion + specs/06-release.md)."
    )


@workflow.defn(name="ParentWorkflow")
class ParentWorkflow:
    """Parent lifecycle stub: inbox -> active -> review -> promoted|escalated."""

    @workflow.run
    async def run(self, inputs: ParentInputs) -> ParentResult:
        task_id = inputs.frame.get("task_id", "unknown")
        # SLA: 2h inbox-to-terminal wall-clock; breach auto-escalates with
        # partial evidence (timer + escalation wiring lands with the live
        # child loop; constant locked here per 02).
        _deadline = TASK_WALL_CLOCK_SECONDS  # noqa: F841 (consumed when live)
        # active: dispatch 1 file -> 1 child (no decomposition in PoC).
        if ChildWorkflow is not None and ChildInputs is not None:
            child_result = await workflow.execute_child_workflow(
                ChildWorkflow.run,
                ChildInputs(frame=inputs.frame),
                id=f"child-{task_id}",
                task_queue=TASK_QUEUE,
            )
            receipt: dict[str, Any] = child_result.receipt
        else:  # offline fallback (no child module): legacy activity slot.
            receipt = await workflow.execute_activity(
                dispatch_child,
                inputs.frame,
                schedule_to_close_timeout=_dt.timedelta(seconds=TASK_WALL_CLOCK_SECONDS),
            )
        # Terminal receipts escalate immediately (never retried, never dropped).
        terminal = decide_terminal(receipt)
        if terminal is not None:
            return ParentResult(
                task_id=task_id,
                state=terminal,
                annotation=f"{receipt.get('exit_promise')}: awaiting human triage",
            )
        # review: sensor-only gate, degrading to deferred no-op in PoC.
        review = await workflow.execute_activity(
            sensor_review,
            receipt,
            schedule_to_close_timeout=_dt.timedelta(minutes=10),
        )
        return ParentResult(
            task_id=task_id, state=review["next_state"], annotation=review["annotation"]
        )
