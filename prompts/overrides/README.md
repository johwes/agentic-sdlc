# prompts/overrides — per-task worker prompt overrides (optional)

Drop a host-authored prompt here as `<TASK_ID>.txt` (e.g. `TASK-403.txt`)
to override the image-default worker contract for that task
(see `specs/04-worker-cell.md` delivery tiers).

- Re-uploaded into the cell on **every** attempt — in-cell edits can never
  persist it; the image default (`prompts/worker_contract.txt`) applies
  when no override exists.
- Auditability: the override flows through Temporal activity inputs, so
  history records what the worker was told.
- Env `PROMPT_FILE` (explicit file) wins over this convention; the wrapper
  flag `--contract-prompt` / `CELL_CONTRACT_PROMPT` wins over both.
