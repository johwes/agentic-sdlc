# 06 — Deterministic Release Pipeline (Tekton / ArgoCD)

Source: `intent.md` §§1, 3.

## Goal

Handle non-repairable artifact compilation, cryptographic signing, and GitOps
deployments strictly downstream at/after the PR boundary.

## Non-goals

- Remediation loops (upstream sensor/inner-loop concerns).
- Agent-driven fix cycles after promotion (release is deterministic, not agentic).

## Inputs

- Promoted PR from the control plane (`02-control-plane.md`).

## Outputs

- Signed, packaged artifact + GitOps deployment.

## Flow

1. PR promotion triggers the release pipeline.
2. Tekton compiles/packages non-repairable artifacts.
3. Artifacts are cryptographically signed.
4. ArgoCD deploys via GitOps.

## Failure modes

- Release failure requiring code repair → must route back through the control
  plane as a new ledger task, not patched inside the pipeline.
- Unsigned or unprovenanced artifact reaching deploy.

## Open questions

- Tekton pipeline definitions and signing key management?
- ArgoCD app-of-apps layout and promotion environments?
- Rollback policy?
