# AGENTS.md — agentic-sdlc

Stack-agnostic greenfield repo. No build/test/lint toolchain configured — do not invent commands.

## Start here

1. Read `specs/README.md` (index), then load only the linked per-topic spec(s) you need.
2. Fall back to `specs/intent.md` for provenance. If code conflicts with specs, flag it — don't silently diverge.

## Key invariants (from specs)

- Workers are ephemeral: file-system state only (`current_task.json` in, `task_receipt.json` + diff out). Never assume conversational memory.
- Never mutate shared progress/ledger state (`PROGRESS.md`, task manifests — Temporal-projected).
- Never weaken tests to pass: no editing assertions/mocks to green, no commenting out failures. Failing gate = reset + retry.
- No secrets in env/files; egress token injection only (see `specs/04-worker-cell.md`).

## Git

Repo not yet initialized. On first code: `git init`, short-lived `feat/<scope>` branches from `main`, small PRs linking the relevant spec + gate evidence. Commit only intended files; never commit secrets.
