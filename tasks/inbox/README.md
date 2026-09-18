# tasks/inbox — PoC file trigger

Drop a hand-written `current_task.json` frame here as `TASK-<n>.json` to seed
work. A Temporal client starter picks the file up and opens the parent
workflow (see `specs/02-control-plane.md`).

- One file = one task (1:1 default; human edits the frame for overrides).
- Schema: `specs/07-contracts.md` (`current_task.json` table).
- The frame's `repo_url` points at the target repo (e.g. the standalone
  demo repo); the host clones it, the cell never sees credentials.
- Do not hand-edit `tasks/ledger.md` — it is Temporal-rendered.
