# 02 — Macro Control Plane (Temporal Parent Workflow)

Source: `intent.md` §§1, 3 (T1).

## Goal

Orchestrate end-to-end task lifecycles, global SLAs, and the outer-loop
diagnostic sensor array.

## Non-goals

- Executing atomic code attempts (child-workflow concern, see `03-inner-loop.md`).
- Packaging/signing/deploying artifacts (release concern, see `06-release.md`).

## Inputs

- Webhook ingestion: issue / PR / label events.

## Outputs

- Task Decomposition Ledger entries spawning Tier-2 child workflows.
- Sensor-driven remediation directives (from `05-sensors.md` findings).
- Multi-agent review verdicts.
- PR promotion + downstream release trigger.

## Flow

1. Ingest webhook (issue / PR / label).
2. Decompose into ledger tasks.
3. Run sensor inversion (SonarQube / Snyk / DAST findings feed back as work items).
4. Convene multi-agent review panel on candidate output.
5. Promote to PR and trigger downstream release.

## Failure modes

- Ledger divergence from Temporal truth (must remain the single source of truth
  per `01-principles.md`).
- Sensor findings that cannot map to a ledger task (route to open questions /
  human review rather than dropping silently).

## Open questions

- Ledger schema and SLA/timeout values?
- Review-panel quorum and voting rules?
- Webhook auth and dedup/idempotency strategy?
