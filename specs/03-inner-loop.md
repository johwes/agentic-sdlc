# 03 — Inner-Loop State Engine (Temporal Child Workflow)

Source: `intent.md` §§1–3 (T2).

## Goal

Execute atomic Ralph cycles with zero context carryover between attempts.

## Non-goals

- Cross-task orchestration (parent concern, see `02-control-plane.md`).
- Worker sandboxing mechanics (worker concern, see `04-worker-cell.md`).

## Inputs

- Projected task frame: `current_task.json` (compiled by Temporal; schema in
  `07-contracts.md`).

## Outputs

- On gate pass: commit checkpoint to the task git branch.
- On gate fail: atomic `git reset` + `continue_as_new()` (fresh history, no rot).
- Worker result artifact: `task_receipt.json` (schema in `07-contracts.md`).

## Flow

1. Receive `current_task.json`.
2. Dispatch non-interactive command to worker pod.
3. Collect `task_receipt.json`.
4. Evaluate deterministic gates: Tree-sitter AST validation + read-only hold-out
   evals (hold-out tests are never writable by the worker — anti-gaming).
5. Pass → commit checkpoint. Fail → atomic reset + `continue_as_new()`.

## Failure modes

- Worker mutates hold-out evals or test assertions to force green (must be
  structurally impossible: read-only mounts, see `04-worker-cell.md`).
- Partial commits leaking failed-attempt state (reset must be atomic).
- History growth across retries (must use `continue_as_new`, not unbounded
  history append).

## Open questions

- Gate ordering and retry budget / backoff?
- Tree-sitter grammar set and AST acceptance criteria?
- Hold-out eval sourcing and rotation policy?
