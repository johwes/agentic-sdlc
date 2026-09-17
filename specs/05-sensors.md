# 05 — Sensors (Upstream Static & Security Analysis)

Source: `intent.md` §§1–2 (sensor inversion), §3 (T1 sensor step). Fleshed
out via spec interview (round 7).

## Goal

Move SonarQube, CodeQL, Snyk, Trivy, and DAST upstream/inward so they act as
sensory organs emitting structured findings that directly drive remediation
loops — instead of downstream pass/fail gates needing human intervention.

## Non-goals

- Release-time signing/scanning-as-gatekeeping (see `06-release.md`).
- Inner-loop AST/hold-out gates (see `03-inner-loop.md`).

## PoC status: none wired

No sensors run in the PoC. The review gate in `02-control-plane.md`
operates as a logged no-op annotated on the receipt
(`review: skipped, no sensors configured`) — never a silent skip — and the
task proceeds to the promotion queue. This spec defines integration
contracts, not live integrations; the first real sensor is a post-PoC
milestone (see below).

## Runtime home: host Temporal activity

The review-gate suite lives in a Temporal activity on the host, running
against the candidate checkout at the local commit SHA from the receipt.
This address holds even while the suite is a no-op.

- Not in-cell: keeps the worker cell minimal and untrusted; sensors are
  trusted verifier infrastructure.
- Not external polling: no hosted service exists in the PoC.

## Normalization contract

Every sensor normalizes to SARIF/JSON with, at minimum: `tool_name`,
`rule_id`, `file_path`, `line_number`, `severity` (tool-native),
`message`/evidence payload. Temporal curates normalized findings to the
immediate file/line target before projecting into `sensor_context` — raw
megabyte-sized SARIF dumps never enter task frames (see
`07-contracts.md`).

### Severity mapping (stub — each integration fills its row)

| Tool | Native severities | → `block` | → `advise` |
|------|-------------------|-----------|------------|
| SonarQube | blocker, critical, major, minor, info | blocker, critical | major, minor, info |
| CodeQL | error, warning, note | error | warning, note |
| Snyk | critical, high, medium, low | critical, high | medium, low |
| Trivy | critical, high, medium, low, unknown | critical, high | medium, low, unknown |
| DAST | high, medium, low, informational | high | medium, low, informational |

## Severity → action policy: high blocks, rest advise

- `block`-mapped findings force remediation re-entry: curated into
  `sensor_context` and the task returns to `active` under attempt budget
  (see `02-control-plane.md`).
- `advise`-mapped findings ride along as frame context but never block
  promotion.

## Diff-scope rule (architectural)

Only findings touching files/lines in the task's `files_changed` can block
or force re-entry; everything else is ignored. This rule is what makes
baselines unnecessary: PoC repos start clean so no checked-in baseline file
is needed, and a baseline file remains an opt-in hardening step rather than
a requirement. Findings that cannot map to the diff (or to any ledger task)
are surfaced to human review, never dropped silently.

## Curation budget

Max ~10 findings per frame projection, file/line-targeted, highest severity
first. Bounds Temporal payloads and worker token spend.

## DAST scoping requirement

When DAST arrives, it runs against a pinned ephemeral target per run
(provisioned for the review activity, torn down after). Unpinned or drifting
targets are a hard misconfiguration, not a soft warning.

## First-integration milestone

Exit criterion for "sensors live": one repo-native linter activity
(zero-infra, e.g. the repo's own lint/typecheck) wired through this entire
contract — normalize → severity map → diff-scope → curate → re-enter. A
hosted scanner (SonarQube/Snyk) is the documented follow-up, not the first.

## Failure modes

- Unactionable findings (no file/line/rule mapping) — must not spawn empty loops.
- Sensor flakiness causing infinite remediation (severity thresholds above
  plus attempt budget bound it; persistent flake → escalate, see `02`).
- DAST environment drift (target must be pinned per run).
- A sensor suite that silently stops running and degrades to an unlogged
  no-op (the receipt annotation is the tripwire — no annotation, no trust).

## Open questions

- Sensor versions and rule packs per tool?
- Suppression policy for accepted-risk findings (opt-in baseline file)?
- Advisory-findings retention (do they persist across attempts or refresh?).
