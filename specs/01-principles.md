# 01 — Principles

Source: `intent.md` §2 (plus §1 problem statement).

## Goal

Fix four systemic failures of naive coding agents: (1) context-window rot and
hallucination spirals, (2) specification gaming / RLVR reward hacking in TDD
loops, (3) execution vulnerabilities and secret exposure, (4) CI/CD inversion
mismatch (high-latency downstream gates requiring human fix loops).

## Architectural invariants (non-negotiable)

1. **Destroy state to maintain precision (context hygiene).** The worker starts
   fresh every attempt. Context comes strictly from an ephemeral projected task
   frame plus local disk diffs — never from accumulated conversation history.
2. **Temporal as the single source of truth.** The worker filesystem is an
   ephemeral scratchpad. `PROGRESS.md` and task manifests are compiled and
   projected by Temporal — never mutated directly across workers. **PoC
   exception:** a checked-in multi-task `PROGRESS.md` the agent edits
   directly is permitted only under the 07 constraints (toggle the first
   unchecked item only; commit it with the code). See
   `07-contracts.md`.
3. **Inversion of CI (sensors vs. release assembly).** Static analysis, vuln
   scanners, and DAST move upstream/inward as sensory organs emitting structured
   SARIF/JSON that drives targeted remediation (sensor side: see
   `05-sensors.md`). Traditional CI is reserved for
   deterministic packaging (release side: see `06-release.md`).
4. **Zero-trust ephemeral sandboxing.** AI shell interactions are untrusted.
   OpenShell enforces process isolation, path scoping, and credential masking —
   raw inference keys never exist in the pod environment.

## Non-goals

- Preserving developer "flow state" ergonomics (explicitly rejected for agents;
  precision over continuity).
- Solving packaging/signing/deploy inside the loop (downstream release concern).

## Failure modes these principles prevent

- Attention drift from accumulated tool calls / compiler logs → solved by (1).
- Cheating gates by editing assertions, mocking returns, commenting out tests →
  solved by (1) + deterministic gates in `03-inner-loop.md`.
- Container escape, network scanning, metadata-service exploitation, credential
  exfiltration → solved by (4).
- Cold-runner latency and PR clutter from downstream analyzer failures → solved
  by (3).

## Open questions

- Exact context budget / projection size limits for the ephemeral task frame?
- Decided mappings live in `07-contracts.md` (`forbidden_paths` → `BLOCKED`,
  tactile-nonzero → `FAILED`); open only whether future principle classes
  need a severity beyond block/fail.
