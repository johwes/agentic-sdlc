# 06 — Deterministic Release Pipeline (Tekton / ArgoCD)

Source: `intent.md` §§1, 3. Fleshed out via spec interview (round 8).

## Goal

Handle non-repairable artifact compilation, cryptographic signing, and GitOps
deployments strictly downstream at/after the PR boundary.

## Non-goals

- Remediation loops (upstream sensor/inner-loop concerns).
- Agent-driven fix cycles after promotion (release is deterministic, not agentic).

## PoC definition of release: PR merge is the end

No Tekton, no ArgoCD, no pipeline runs in the PoC. The release flow is:

1. Temporal opens the promotion **draft** PR (see `02-control-plane.md`).
2. A human reviews, marks it ready, and **merges** it.
3. That merge *is* the release.

The post-PoC deterministic pipeline below is the contract its future
implementation must satisfy — not a description of running infrastructure.

## Trigger: merge to `main`

Nothing automatic fires before the merge. Draft → ready is human judgment;
the merge event is the release trigger (and, post-PoC, the event that fires
the Tekton pipeline).

## Merge discipline + branch protection

- Promotion PRs merge via **squash-merge**: one task = one commit on `main`,
  mirroring the promotion squash in `02-control-plane.md`.
- Recommended repo setting (human-applied, since the PoC is file-trigger
  only): `main` requires PRs, no direct pushes. The loop never pushes to
  `main` itself — workers can't push at all, and promotion pushes only to
  `target_branch`.

## Signing & provenance: none in PoC (accepted debt)

No signing is enforced in the PoC. This is recorded as explicit debt, not
normalized practice. Exit criterion: the first cryptographically signed
artifact (intended mechanism: Sigstore/cosign) must land before any
non-demo deployment. An unsigned artifact reaching anything beyond a demo
environment is a hard failure of this spec.

## Failure routing: new ledger task (rule) + hotfix (emergency override)

- **Rule:** post-merge failures route back through the control plane as fresh
  `tasks/inbox/TASK-<n>.json` frames carrying the failure as
  `sensor_context`. Repair-needing code is never patched inside the release
  path — the `intent.md` inversion holds end to end.
- **Emergency override (PoC):** a human may hotfix directly on a hotfix
  branch, but owes a **file-after duty** — the ledger task gets filed
  afterwards so the loop retains history and the hotfix doesn't bypass it.

## Rollback

- PoC: `git revert` of the squash commit. Stated plainly, no ceremony.
- Post-PoC: ArgoCD rollback policy (open question below).

## Post-PoC pipeline contract

When built, the deterministic pipeline must satisfy:

1. Merge to `main` fires the Tekton pipeline.
2. Tekton compiles/packages non-repairable artifacts.
3. Artifacts are cryptographically signed (Sigstore/cosign intended).
4. ArgoCD deploys via GitOps.
5. Failures needing code repair route to the ledger as new tasks — never
   patched inside the pipeline. Agents re-enter only via ledger tasks;
   no agent fix cycles run post-promotion.

## Failure modes

- Unsigned/non-demo artifact treated as acceptable (violates the exit criterion).
- Direct pushes to `main` bypassing PR review.
- Agent patching code post-promotion outside a ledger task.
- Release failure patched inside the pipeline instead of routed to the ledger.

## Open questions

- Tekton pipeline definitions and signing key management?
- ArgoCD app-of-apps layout and promotion environments?
- ArgoCD rollback policy (post-PoC successor to `git revert`)?
