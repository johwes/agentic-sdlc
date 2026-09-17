# 07 — Contracts (`current_task.json`, `task_receipt.json`, `PROGRESS.md`)

Source: `intent.md` §§2–3.

## Goal

Define the file-system state contracts that let ephemeral workers stay precise
without conversational memory.

## Non-goals

- Workflow orchestration semantics (see `02`, `03`).
- Sensor finding schemas (see `05-sensors.md`).

## Contracts (initial shapes — field-level schemas TBD)

- **`current_task.json`** (Temporal → worker): the ephemeral projected task
  frame. Compiled per attempt by Temporal. Worker treats it as read-only input.
- **`task_receipt.json`** (worker → child workflow): result of one attempt
  (exit status, diff summary, test-relevant metadata). Consumed by gates in
  `03-inner-loop.md`.
- **`PROGRESS.md`** (Temporal-projected): human/agent-readable progress view,
  dynamically compiled — never hand-mutated across workers.

## Rules

- Worker filesystem is a scratchpad: only the receipt + diff leave the cell.
- Workers never mutate shared progress/ledger state directly.
- Workers never write hold-out evals (read-only mounts per `04-worker-cell.md`).
- Never weaken tests to pass: no editing assertions/mocks to green, no
  commenting out failures. Failing gate = reset + retry.

## Open questions

- JSON schemas (required fields, versions) for `current_task.json` /
  `task_receipt.json`?
- `PROGRESS.md` template and projection trigger (per checkpoint vs. per attempt)?
- Receipt size limits and diff encoding?
