# Progress — agentic-sdlc (Ralph backlog)

<!-- Ralph loop: each `opencode run` implements ONLY the topmost unchecked
item below, commits it (code + this file + spec delta if behavior locked),
then exits. See AGENTS.md git workflow. -->

- [x] Wire `harness/wrapper.py` stage 1: frame load + forbidden_paths diff assertion → `BLOCKED` (no LLM dispatch yet)
- [x] Wire wrapper stage 2: `tactile_command` timeout/truncation + nonzero→`FAILED` ground truth (see `specs/07-contracts.md`)
- [x] Wire wrapper stage 3: git SHAs + `task_receipt.json` serialization, nullable `token_metrics` (see `specs/07-contracts.md`)
- [x] Import `policy/opencode-profile.yaml` on gateway + re-prove headless `opencode --model` (see `specs/04-worker-cell.md`)
- [x] Add Temporal dev scaffolding: laptop-local server + parent workflow stub (see `specs/02-control-plane.md`)
- [x] Add child workflow: attempt loop, gates a/b/c, `continue_as_new`, `retry_strategy` `reset` default (see `specs/03-inner-loop.md`)
- [x] Seed `tasks/inbox/TASK-402.json` example frame + `tasks/ledger.md` projection stub (see `specs/02-control-plane.md`)
- [x] Add sensor stub activity: logged no-op (`review: skipped, no sensors configured`), block/advise split ready (see `specs/05-sensors.md`)
- [x] Add root README: project overview + offline/infra getting-started demo (public audience)
- [x] Wire `harness/wrapper.py` stage 4: LLM dispatch + summary/metrics capture + cell gitconfig identity (no push logic; Tier-1 locked, see `specs/04-worker-cell.md`)
- [x] Bootstrap standalone demo repo `johwes/tic-tac-toe` (tic-tac-toe + planted bug + zero-dep node tests) + `tasks/inbox/TASK-403.json` frame with `repo_url` (see `specs/07-contracts.md`)
- [ ] Wire child `run_attempt` + cell create/destroy activities to `scripts/spawn-cell.sh` (clone frame `repo_url`, see `specs/03-inner-loop.md`, `specs/04-worker-cell.md`)
- [ ] Wire child `reset_cell` + `checkpoint_commit` activities (local-only, no push; see `specs/03-inner-loop.md`)
- [ ] Wire promotion `open_draft_pr`: bundle-download → host fetch → secret scan → squash → push → draft PR (see `specs/02-control-plane.md`)
- [ ] Wire ledger projection write path to `tasks/ledger.md` (see `specs/02-control-plane.md`)
- [ ] Private end-to-end rehearsal + refresh README demo from real output
