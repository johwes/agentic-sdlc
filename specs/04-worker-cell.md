# 04 — Governed Worker Cell (OpenShift + Nvidia OpenShell)

Source: `intent.md` §§1–3 (T3).

## Goal

Run ephemeral agent CLI processes (Claude Code or OpenCode) under strict
kernel-level filesystem jailing and token-injecting egress control.

## Non-goals

- Task orchestration or gating (see `02-control-plane.md`, `03-inner-loop.md`).
- Release packaging (see `06-release.md`).

## Inputs

- Non-interactive CLI command dispatched from the Tier-2 child workflow.
- Projected task frame + ephemeral scratch filesystem.

## Outputs

- `task_receipt.json` emitted back to the child workflow.
- Ephemeral diff on scratch disk (consumed by gates, then destroyed or
  checkpoint-committed by the child — never persisted by the worker itself).

## Flow

1. OpenShell policy boundary admits the dispatched command.
2. Filesystem jailing enforced: read-only root and read-only evals/hold-outs.
3. Egress proxy with in-flight token injection (raw inference keys never in pod env).
4. Ephemeral CLI executes, writes receipt + diff, terminates; cell is discarded.

## Failure modes

- Credential exposure via env inspection → prevented by in-flight injection +
  credential masking.
- Lateral movement (local network scan, metadata-service exploitation,
  container escape) → prevented by process isolation, path scoping, egress policy.
- State leakage across attempts → prevented by ephemeral cell lifecycle.

## Open questions

- OpenShell policy bundle location and versioning?
- Egress allowlist and proxy implementation?
- Resource limits (CPU/mem/GPU, wall-clock) per attempt?
- Exact non-interactive CLI contract (args, exit codes, receipt path)?
