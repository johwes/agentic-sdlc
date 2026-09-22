# tasks/inbox — PoC file trigger

Drop a hand-written `current_task.json` frame here as `TASK-<n>.json` to seed
work. A Temporal client starter picks the file up and opens the parent
workflow (see `specs/02-control-plane.md`).

*Alternate ingest for demos:* run the single-fetch triage adapter

```bash
python3 scripts/analyze-issue.py --repo https://github.com/<owner>/<repo>.git --issue-id 123
# fetches issue #123, runs in-cell triage (opencode-go/glm-5.3-flash, see
# prompts/triage_contract.txt), writes tasks/inbox/TASK-123.json
python3 temporal/starter.py tasks/inbox/TASK-123.json
```

Production would replace the manual fetch with a webhook/polling adapter that
produces the same frame shape — same downstream path.

- One file = one task (1:1 default; human edits the frame for overrides).
- Schema: `specs/07-contracts.md` (`current_task.json` table).
- The frame's `repo_url` points at the target repo (e.g. the standalone
  demo repo); the host clones it, the cell never sees credentials.
- `issue.number → task_id TASK-<n>` for the GitHub path; existing
  `tasks/ledger.md` row in `promoted|active` skips re-triage.
- Do not hand-edit `tasks/ledger.md` — it is Temporal-rendered.
