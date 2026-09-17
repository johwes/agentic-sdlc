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
4. Evaluate deterministic gates **in order**: (a) `forbidden_paths` diff
   assertion — violation → `BLOCKED` / `HALT:BLOCKED`, halt, no retry;
   (b) `tactile_execution.exit_code` — nonzero → `FAILED` (ground truth, no
   agent override); (c) Tree-sitter AST validation + read-only hold-out evals
   (hold-out tests are never writable by the worker — anti-gaming).
5. Resolve the receipt via the status / `exit_promise` matrix in
   `07-contracts.md`:
   - `SUCCESS` / `COMPLETE` → commit checkpoint.
   - `FAILED` / `RETRYABLE_FAILURE` → atomic `git reset` +
     `continue_as_new()` with `attempt + 1`.
   - `FAILED` / `HALT:EXHAUSTED` or `BLOCKED` / `HALT:BLOCKED` → escalate to
     the parent (or human); no further retry.

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
