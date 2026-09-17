# AGENTS.md — agentic-sdlc

Stack-agnostic greenfield repo. No build/test/lint toolchain configured — do not invent commands.

## Start here

1. Read `specs/README.md` (index), then load only the linked per-topic spec(s) you need.
2. Fall back to `specs/intent.md` for provenance. If code conflicts with specs, flag it — don't silently diverge.

## Key invariants (from specs)

- Workers are ephemeral: file-system state only (`current_task.json` in, `task_receipt.json` + diff out). Never assume conversational memory.
- Shared progress/ledger state (`PROGRESS.md`, task manifests) is Temporal-projected in production — never hand-mutated. **PoC exception:** the checked-in `PROGRESS.md` Ralph backlog is hand-edited, but an agent run may toggle **only the topmost unchecked item** (`- [ ]` → `- [x]`) and must commit it alongside code (see `specs/07-contracts.md`).
- Never weaken tests to pass: no editing assertions/mocks to green, no commenting out failures. Failing gate = reset + retry.
- No secrets in env/files; egress token injection only (see `specs/04-worker-cell.md`).

## Spec-update rule

Update the relevant `specs/NN-*.md` file **only** if you changed behavior or locked a tuning decision (e.g. pinning a model ID, fixing an allowlist, locking `retry_strategy`). Pure progress (toggling the box, fixing a typo, wiring code the spec already describes) does not touch specs.

## Git

Repo is initialized on `main` (remote `origin`). Short-lived `feat/<task-id>-<slug>` branches from `main` — one branch per Ralph backlog item. Small commits linking the relevant spec + gate evidence; push the branch when the item is done. Commit only intended files (code + `PROGRESS.md` + spec delta if any); never commit secrets.
