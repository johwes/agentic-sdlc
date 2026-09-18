"""Sensors: upstream static & security review-gate suite stub (PoC).

See specs/05-sensors.md. PoC stance: no sensors run. The review gate lives
here — a host Temporal activity running against the candidate checkout at
the local commit SHA from the receipt — and degrades to a logged no-op
annotated on the receipt ("review: skipped, no sensors configured", never
a silent skip); the task proceeds to the promotion queue. This module
defines the integration contracts the first real sensor will plug into,
not live integrations.

Contract pieces encoded below (all per 05):

  - Normalization: every sensor normalizes to SARIF/JSON with, at minimum,
    `tool_name`, `rule_id`, `file_path`, `line_number`, `severity`
    (tool-native), `message`/evidence payload. Raw megabyte-sized SARIF
    dumps never enter task frames — Temporal curates normalized findings
    to the immediate file/line target before projecting into
    `sensor_context` (see 07-contracts.md).
  - Severity mapping (stub — each integration fills its row): native
    severity -> `block` | `advise` per SEVERITY_MAP.
  - Severity -> action: `block` forces remediation re-entry (curated into
    `sensor_context`, task returns to `active` under attempt budget, see
    02-control-plane.md); `advise` rides along as frame context but never
    blocks promotion.
  - Diff-scope rule (architectural): only findings touching files in the
    task's `files_changed` can block or force re-entry; everything else is
    ignored (baselines unnecessary — PoC repos start clean). Findings that
    cannot map to the diff (or to any ledger task) are surfaced to human
    review via the annotation counts, never dropped silently.
  - Curation budget: max ~10 findings per frame projection,
    file/line-targeted, highest severity (block) first. Bounds Temporal
    payloads and worker token spend.
  - DAST scoping requirement (future): when DAST arrives it runs against a
    pinned ephemeral target per run, torn down after; unpinned/drifting
    targets are a hard misconfiguration. Recorded here, enforced at first
    integration — the stub runs no DAST.
  - First-integration milestone: one repo-native linter activity
    (zero-infra) wired through normalize -> severity map -> diff-scope ->
    curate -> re-enter. Its entry point is review_commit() with a
    configured findings list; a hosted scanner (SonarQube/Snyk) is the
    documented follow-up, not the first.

Pure helpers below (REVIEW_SKIPPED_ANNOTATION, SEVERITY_MAP,
normalize_finding, classify_severity, findings_in_diff, curate_findings,
review_commit) are stdlib-only so they import and run without the Temporal
SDK or a live server. The @activity definition at the bottom wires the
stub into Temporal when `temporalio` is installed; without it the module
still imports (guarded) for offline inspection — same pattern as
temporal/parent.py and temporal/child.py.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# PoC constants (per 05; tunable/fillable with evidence at first integration)
# ---------------------------------------------------------------------------

# Logged no-op annotation when no sensors are configured (02 + 05).
# Recorded on the receipt — never a silent skip (the receipt annotation is
# the tripwire: no annotation, no trust — see 05 failure modes).
REVIEW_SKIPPED_ANNOTATION = "review: skipped, no sensors configured"

# Sensors understood by the normalization contract (05 goal).
SUPPORTED_TOOLS = ("SonarQube", "CodeQL", "Snyk", "Trivy", "DAST")

# Severity mapping stub — each integration fills its row (05 table).
# Native severity (lowercased) -> "block" | "advise". Unknown tool or
# unknown native severity maps to "advise": never block on what we do not
# understand (unactionable findings must not spawn empty loops; persistent
# flake escalates via the attempt budget, see 02).
SEVERITY_MAP: dict[str, dict[str, str]] = {
    "SonarQube": {
        "blocker": "block",
        "critical": "block",
        "major": "advise",
        "minor": "advise",
        "info": "advise",
    },
    "CodeQL": {
        "error": "block",
        "warning": "advise",
        "note": "advise",
    },
    "Snyk": {
        "critical": "block",
        "high": "block",
        "medium": "advise",
        "low": "advise",
    },
    "Trivy": {
        "critical": "block",
        "high": "block",
        "medium": "advise",
        "low": "advise",
        "unknown": "advise",
    },
    "DAST": {
        "high": "block",
        "medium": "advise",
        "low": "advise",
        "informational": "advise",
    },
}

# Max findings per frame projection (05 curation budget).
CURATION_BUDGET = 10

# Minimum fields a raw finding must carry to be actionable (05
# normalization contract). Findings missing file/line/rule mapping are
# unactionable: counted, surfaced in the annotation, never blocking.
REQUIRED_FINDING_FIELDS = (
    "tool_name",
    "rule_id",
    "file_path",
    "line_number",
    "severity",
    "message",
)


# ---------------------------------------------------------------------------
# Pure helpers (stdlib-only; no Temporal dependency)
# ---------------------------------------------------------------------------


def normalize_finding(raw: Any) -> dict[str, Any] | None:
    """Normalize one raw sensor finding to the SARIF/JSON contract.

    Returns the normalized dict (`tool_name`, `rule_id`, `file_path`,
    `line_number`, `severity` tool-native, `message`) or None when the
    finding is unactionable (not an object, unknown tool, or no
    file/line/rule mapping). None findings never block — they are counted
    and surfaced, never silently dropped (see 05 diff-scope rule).
    """
    if not isinstance(raw, dict):
        return None
    tool = raw.get("tool_name")
    if tool not in SUPPORTED_TOOLS:
        return None
    rule = raw.get("rule_id")
    path = raw.get("file_path")
    if not rule or not isinstance(rule, str):
        return None
    if not path or not isinstance(path, str):
        return None
    try:
        line = int(raw.get("line_number", 0))
    except (TypeError, ValueError):
        return None
    if line < 1:
        return None
    severity = raw.get("severity", "unknown")
    message = raw.get("message", raw.get("evidence", ""))
    return {
        "tool_name": tool,
        "rule_id": rule,
        "file_path": path,
        "line_number": line,
        "severity": str(severity),
        "message": str(message),
    }


def classify_severity(tool_name: str, native_severity: Any) -> str:
    """Map a tool-native severity to "block" | "advise" (05 table).

    Unknown tools or severities fall back to "advise" — never block on
    what we do not understand.
    """
    row = SEVERITY_MAP.get(tool_name, {})
    return row.get(str(native_severity).lower(), "advise")


def findings_in_diff(
    findings: list[dict[str, Any]],
    files_changed: list[str] | None,
) -> list[dict[str, Any]]:
    """Diff-scope rule: keep only findings touching the task's diff.

    Only findings whose `file_path` is in the receipt's `files_changed`
    can block or force re-entry; everything else is ignored (PoC matches
    on file path; line-hunk refinement is a post-PoC slot alongside the
    first real sensor).
    """
    changed = set(files_changed or [])
    return [f for f in findings if f.get("file_path") in changed]


def curate_findings(
    raw_findings: list[dict[str, Any]] | None,
    files_changed: list[str] | None,
    budget: int = CURATION_BUDGET,
) -> dict[str, Any]:
    """Normalize -> diff-scope -> classify -> curate to budget.

    Returns {"block": [...], "advise": [...], "ignored_out_of_diff": n,
    "unactionable": m} where block/advise hold `sensor_context`-shaped
    dicts (see 07-contracts.md), highest severity (block) first, capped
    at `budget` total. Out-of-diff and unactionable findings never block;
    their counts ride the annotation so nothing is dropped silently.
    """
    raw = list(raw_findings or [])
    normalized: list[dict[str, Any]] = []
    unactionable = 0
    for r in raw:
        n = normalize_finding(r)
        if n is None:
            unactionable += 1
        else:
            normalized.append(n)
    in_diff = findings_in_diff(normalized, files_changed)
    ignored_out_of_diff = len(normalized) - len(in_diff)

    block: list[dict[str, Any]] = []
    advise: list[dict[str, Any]] = []
    for f in in_diff:
        action = classify_severity(f["tool_name"], f.get("severity"))
        context = {
            "tool_name": f["tool_name"],
            "rule_id": f["rule_id"],
            "file_path": f["file_path"],
            "line_number": f["line_number"],
            "message": f["message"],
        }
        if action == "block":
            block.append(context)
        else:
            advise.append(context)

    # Highest severity first, block before advise; cap the combined set so
    # Temporal payloads and worker token spend stay bounded (05 budget).
    try:
        lim = int(budget)
    except (TypeError, ValueError):
        lim = CURATION_BUDGET
    if lim < 0:
        lim = 0
    block = block[:lim]
    advise = advise[: max(lim - len(block), 0)]
    return {
        "block": block,
        "advise": advise,
        "ignored_out_of_diff": ignored_out_of_diff,
        "unactionable": unactionable,
    }


def review_commit(
    receipt: dict[str, Any],
    configured_findings: list[dict[str, Any]] | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """PoC sensor review gate over one child receipt (05 + 02 review gate).

    Returns (next_state, annotation, curated) where curated is the
    curate_findings() payload (`block`/`advise` lists ready to project
    into `sensor_context`, plus ignored/unactionable counts).

      - No sensors configured (`configured_findings is None`) -> the
        logged no-op: ("promoted", REVIEW_SKIPPED_ANNOTATION, empty
        curated). Recorded on the receipt, never a silent skip; the task
        proceeds to the promotion queue.
      - Sensors configured: normalize -> severity map -> diff-scope ->
        curate -> re-enter. `block` non-empty -> ("active", remediation
        re-entry annotation) under the attempt budget (caller enforces);
        advise-only or clean -> ("promoted", ...) with context attached
        by the caller; advise findings never block.
      - Non-SUCCESS receipts never reach this gate (see
        parent.decide_terminal): ValueError, same contract as
        parent.review_gate.

    The first-integration milestone (repo-native linter) plugs in by
    passing its normalized findings as `configured_findings` — no
    signature change needed.
    """
    if receipt.get("status") != "SUCCESS":
        raise ValueError(
            f"review_commit takes SUCCESS receipts only, got {receipt.get('status')!r}"
        )
    if configured_findings is None:
        return (
            "promoted",
            REVIEW_SKIPPED_ANNOTATION,
            {"block": [], "advise": [], "ignored_out_of_diff": 0, "unactionable": 0},
        )
    curated = curate_findings(configured_findings, receipt.get("files_changed"))
    n_block = len(curated["block"])
    n_advise = len(curated["advise"])
    if n_block > 0:
        return (
            "active",
            f"review: {n_block} block finding(s), remediation re-entry",
            curated,
        )
    if n_advise > 0:
        return (
            "promoted",
            f"review: advise-only ({n_advise}), proceeding to promotion",
            curated,
        )
    return ("promoted", "review: sensors clean, proceeding to promotion", curated)


# ---------------------------------------------------------------------------
# Temporal wiring (guarded: module imports without the SDK for offline use)
# ---------------------------------------------------------------------------

try:  # pragma: no cover - exercised with SDK installed
    from temporalio import activity

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


@activity.defn(name="sensor_review")
async def sensor_review(
    receipt: dict[str, Any],
    configured_findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Host Temporal activity: sensor review gate stub (05 runtime home).

    Runs on the host against the candidate checkout at the local commit
    SHA from the receipt (workers stay minimal and untrusted — sensors
    are trusted verifier infrastructure, never in-cell). PoC: no sensors
    are configured, so this is a logged no-op returning the skipped
    annotation — never a silent skip — and the parent proceeds to the
    promotion queue. The block/advise split is ready: pass configured
    findings (first-integration linter) and block-mapped, diff-scoped
    findings re-enter `active` while advise-only findings ride along.
    """
    next_state, annotation, curated = review_commit(receipt, configured_findings)
    return {
        "next_state": next_state,
        "annotation": annotation,
        "block": curated["block"],
        "advise": curated["advise"],
    }
