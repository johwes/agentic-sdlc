# 02 — Macro Control Plane (Temporal Parent Workflow)

Source: `intent.md` §§1, 3 (T1). Fleshed out via spec interview (round 6).
PoC stance: simplest operable path; enterprise webhook/panel machinery
reserved as named future slots, not built.

## Goal

Orchestrate end-to-end task lifecycles, global SLAs, and the outer-loop
diagnostic sensor array.

## Non-goals

- Executing atomic code attempts (child-workflow concern, see `03-inner-loop.md`).
- Release packaging (see `06-release.md`).

## Inputs (PoC): manual / file trigger

No webhook server in the PoC. A task enters the system when a human drops a
hand-written `current_task.json` frame into `tasks/inbox/TASK-<n>.json` (or
runs the starter CLI against it). A Temporal client starter picks the file
up and opens the parent workflow.

The frame shape is preserved deliberately so a GitHub webhook receiver
(issue / PR / label events) can slot in later as an alternate input adapter
without changing anything downstream. Webhook auth/dedup stays a post-PoC
open question.

## Locality (PoC): laptop-local orchestration

The OpenShell execution plane is reachable only from the owner's laptop, so
the PoC control plane runs there too — no cluster deployment:

- Parent + child Temporal workers are local processes on the same machine as
  the `openshell` CLI (local dev server for first runs; durable backend only
  if laptop-restart history loss bites).
- The remote OpenShell gateway (stage URL, `gateway login` prerequisite) is
  the execution plane; orchestration shells out to the local CLI. Gateway
  selection is a flag, so a future `--local` gateway changes no contract.
- `tasks/inbox/`, `tasks/ledger.md`, and all trigger/projection paths are
  laptop paths. Single-machine constraint is architectural for the PoC:
  no shared cluster filesystem, no remote Temporal server, no multi-node
  assumptions. Cluster deployment is post-PoC, same bucket as Tekton/ArgoCD.

## Decomposition (PoC): one issue, one task + human override

- **Default:** 1 inbox file = 1 ledger task = 1 child workflow. No
  decomposition step runs in the PoC.
- **Override:** when 1:1 doesn't fit, the human authors (or hand-edits) the
  frame directly — splitting, scoping `allowed_paths`, or tightening
  `acceptance_criteria` by hand.
- **Reserved:** an LLM decomposition activity (issue → frames) is a named
  future slot, not built. The ledger schema already carries what it would
  need (see below).

## Ledger

Temporal workflow state is the source of truth (per `01-principles.md`).
The PoC-readable projection is `tasks/ledger.md` — Temporal-rendered,
checked in, same projection pattern as `PROGRESS.md`. Never hand-edited.

Task states: `inbox → active → review → promoted | escalated`.

| Field | Notes |
|-------|-------|
| `task_id` | Matches the frame. |
| `state` | One of the five states above. |
| `attempt` / `max_attempts` | Copied from the frame; bumped per `continue_as_new`. |
| `child_workflow_id` | Spawned Tier-2 workflow handle. |
| `commit_shas` | Per-attempt local SHAs from receipts. |
| `final_receipt` | Last `task_receipt.json` outcome (`status`/`exit_promise`). |
| `pr_url` | Set at promotion (draft PR). |
| `updated_at` | Last transition timestamp. |

## Sensor review gate (PoC): sensor-only, degrading to deferred

A child `SUCCESS` moves the task to `review`, which re-runs the sensor suite
from `05-sensors.md` against the candidate commit:

- Sensors clean → task proceeds to promotion.
- `block`-mapped findings → curated into `sensor_context` and the task
  re-enters `active` as a remediation attempt (attempt budget applies).
- `advise`-only findings → attached as frame context; task proceeds to
  promotion. Severity mapping lives in `05-sensors.md`.
- **No sensors configured** → review is a logged no-op
  (`review: skipped, no sensors configured`), recorded on the receipt — never
  a silent skip — and the task proceeds to the promotion queue.

No LLM reviewer in the PoC. The multi-agent review panel from `intent.md`
is a post-PoC slot (different-model review pass; quorum rules TBD).

Sensor findings that cannot map to a ledger task are surfaced to human
review, never dropped silently.

## Promotion (PoC): draft PR auto, executed by Temporal

Single transfer path (locked): Tier-1 host-side push only. The cell never
pushes and holds no git credentials; the promotion activity runs on the
host with the owner's `gh` auth. In-cell push (even scoped) and the
patch-download handoff were considered and rejected — see
`04-worker-cell.md` for rationale (cf. fullsend ADR-0032 tier 1, the
recommended path for public repos).

The promotion activity runs the local-commit + squash model from
`03-inner-loop.md`:

1. Download the candidate as a git bundle (`git bundle create` in-cell is
   a local op needing no credentials; `sandbox download` to the host),
   then fetch it into the host's `target_branch` checkout of the frame's
   `repo_url`. Bundle
   transfer is lossless (binaries, modes, renames, history) — no patch
   surgery.
2. Secret-scan the candidate before it touches origin
   (gitleaks-equivalent); findings halt promotion for human triage —
   the agent's cell env holds injected secrets that must never reach
   origin.
3. Squash per-attempt commits into one clean commit
   (e.g. `fix(TASK-402): sanitize search input`).
4. Push `target_branch` to the frame's `repo_url` origin.
5. Open a **draft** PR via the `gh` API against the frame's `repo_url`,
   seeding the body from the receipt's
   `agent_summary` plus gate evidence (tactile command, sensor results).
6. Record `pr_url`; mark the task `promoted`.

Ordering constraint: promotion consumes cell content (bundle download)
before the terminal-state cell delete in the `finally` block — ledger
SHAs are useless once the cell is gone.

The human promotes draft → ready. Direct-to-ready and human-opens-PR are
documented alternatives, not the default. (Mechanism = Temporal pushes and
opens; draft status = the safety catch.)

## Escalation handling

`HALT:EXHAUSTED` and `HALT:BLOCKED` receipts land in the ledger as
`escalated` with the final receipt attached, awaiting human triage. Never
auto-retried, never dropped. A path-violation escalation additionally flags
which `forbidden_paths` entry tripped.

## SLAs (PoC defaults, tunable with evidence)

- Global task wall-clock: **2h** from `inbox` to terminal state
  (`promoted` / `escalated`); breach → auto-escalate with partial evidence.
- Promotion-queue staleness nudge: **24h** in `promoted` without human action
  → reminder (no auto-merge, ever).
- Attempt backoff constants live in `03-inner-loop.md`.

## Failure modes

- Ledger divergence from Temporal truth (projection is derived, never source).
- Sensor findings unmappable to a task → human review, not silent drop.
- Promotion pushing partial state (only fully-gated `SUCCESS` promotes;
  workers have no push path — see `03-inner-loop.md`).
- Webhook-shaped inputs arriving before the adapter exists (reject with a
  clear "PoC accepts file trigger only" signal).

## Open questions

- Webhook auth, dedup/idempotency, and event → frame mapping (post-PoC adapter).
- Review-panel quorum and voting rules (post-PoC LLM panel).
- LLM decomposition activity contract (post-PoC).
- SLA tuning under real run data.
