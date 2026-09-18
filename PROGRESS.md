# Progress — agentic-sdlc (Ralph backlog)

<!-- Ralph loop: each `opencode run` implements ONLY the topmost unchecked
item below, commits it (code + this file + spec delta if behavior locked),
then exits. See AGENTS.md git workflow. -->

- [x] Wire `harness/wrapper.py` stage 1: frame load + forbidden_paths diff assertion → `BLOCKED` (no LLM dispatch yet)
- [x] Wire wrapper stage 2: `tactile_command` timeout/truncation + nonzero→`FAILED` ground truth (see `specs/07-contracts.md`)
- [x] Wire wrapper stage 3: git SHAs + `task_receipt.json` serialization, nullable `token_metrics` (see `specs/07-contracts.md`)
- [ ] Import `policy/opencode-profile.yaml` on gateway + re-prove headless `opencode --model` (see `specs/04-worker-cell.md`)
- [ ] Add Temporal dev scaffolding: laptop-local server + parent workflow stub (see `specs/02-control-plane.md`)
- [ ] Add child workflow: attempt loop, gates a/b/c, `continue_as_new`, `retry_strategy` `reset` default (see `specs/03-inner-loop.md`)
- [ ] Seed `tasks/inbox/TASK-402.json` example frame + `tasks/ledger.md` projection stub (see `specs/02-control-plane.md`)
- [ ] Add sensor stub activity: logged no-op (`review: skipped, no sensors configured`), block/advise split ready (see `specs/05-sensors.md`)
