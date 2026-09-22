# 07 — Contracts (`current_task.json`, `task_receipt.json`, `PROGRESS.md`)

Source: `intent.md` §§2–3. Fleshed out via spec interview (rounds 2+4).

## Goal

Define the file-system state contracts that let ephemeral workers stay precise
without conversational memory.

## Non-goals

- Workflow orchestration semantics (see `02`, `03`).
- Sensor finding schemas (see `05-sensors.md`).

## `current_task.json` (Temporal → worker, read-only)

The ephemeral projected task frame, compiled per attempt by Temporal.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `task_id` | string | yes | `TASK-<n>` style, e.g. `"TASK-402"`. |
| `repo_url` | string | yes | Target repo origin (https URL, no credentials), e.g. `"https://github.com/johwes/tic-tac-toe.git"`. The host clones this into the workspace (`04-worker-cell.md` ingestion) and promotion pushes the PR here (`02-control-plane.md`). |
| `title` | string | yes | Concise objective summary. |
| `acceptance_criteria` | string[] | yes | Explicit pass/fail statements. |
| `target_branch` | string | yes | Working branch; worker verifies its head before editing. |
| `allowed_paths` | string[] | yes | Glob patterns the agent may touch, e.g. `["src/api/**", "tests/unit/**"]`. |
| `forbidden_paths` | string[] | yes | Touch = verification failure, e.g. `["tests/evals/**", ".task/**"]`. |
| `sensor_context` | object[] | yes (may be empty) | Curated findings: `tool_name` (SonarQube/Snyk/DAST/CodeQL/Trivy), `rule_id`, `file_path`, `line_number`, `message`/evidence payload. |
| `attempt` | integer | yes | Current cycle index, 1-indexed. |
| `max_attempts` | integer | yes | Ceiling before escalation. |
| `tactile_command` | string | yes | Local reality-check command ("tactile feedback" — the worker feels/tests its work before asserting completion), e.g. `"pytest tests/unit/test_search.py"`. Name is intentional. |
| `tactile_timeout_seconds` | integer | no | Kill timeout for `tactile_command`. Default `180`; sane range `120–300`. |
| `retry_strategy` | enum | no | `"adaptive"` (default, locked 2026-09-21) = surgical repair first then strike-2 reset with sprawl guard; `"reset"` = always reset; `"continue"` = always keep diff. See `03-inner-loop.md`. Omitted → `adaptive`. |
| `prior_diagnostics` | string | no | Previous attempt's `agent_summary` tail (`[-4000:]`) attached by `next_frame()` — text only, never conversational memory. |
| `tactile_injection` | — | — | On retryable tactile failure under `adaptive`, the child injects one synthetic `sensor_context` finding `{tool_name:"TactileTestGate", rule_id:"AssertionFailure", message:"Previous attempt failed…\n<summary_output[-2000:]>"} `. Not a frame field — an appended `sensor_context` entry. |

### Must never carry

- Hold-out test locations or references — revealing hidden eval paths enables
  assertion reverse-engineering.
- Credentials, API keys, GitHub tokens, or vault references.
- Global SDLC / roadmap state, parent workflow history, or unrelated sub-tasks.
- Raw, unfiltered scanner dumps — Temporal trims and curates `sensor_context`
  to the immediate file/line target to preserve token budget.

## `task_receipt.json` (worker → child workflow)

Result of one attempt. Consumed by gates in `03-inner-loop.md`.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `task_id` | string | yes | Must match the frame's ID. |
| `status` | enum | yes | `"SUCCESS"` \| `"FAILED"` \| `"BLOCKED"`. |
| `exit_promise` | enum | yes | `"COMPLETE"` \| `"RETRYABLE_FAILURE"` \| `"HALT:EXHAUSTED"` \| `"HALT:BLOCKED"`. |
| `commit_sha` | string | yes | Git commit hash created inside the container. |
| `files_changed` | string[] | yes | Paths the attempt modified: working-tree changes plus the attempt's commit range (pre-dispatch `HEAD` to post-dispatch `HEAD`). Committing never hides a path — gates run on this (locked 2026-09-18). |
| `tactile_execution` | object | yes | `{command_run, exit_code, summary_output}` — output tail capped at 50 lines / ~4KB. |
| `agent_summary` | string | yes | Model-written what/why; used for PR generation and next-attempt diagnostics. Never overrides ground truth. |
| `token_metrics` | object | yes (fields nullable) | `{input_tokens, output_tokens, cost}` — all nullable (see telemetry). |

### Status / `exit_promise` matrix

| `status` | Condition | `exit_promise` | Meaning |
|----------|-----------|----------------|---------|
| `SUCCESS` | Pass criteria met & verified | `COMPLETE` | Ready for downstream merge/eval. |
| `FAILED` | Tests fail, `attempt < max_attempts` | `RETRYABLE_FAILURE` | Budget remains; loop retries. |
| `FAILED` | Tests fail, `attempt == max_attempts` | `HALT:EXHAUSTED` | Budget spent; escalate. |
| `BLOCKED` | Dependency, path violation, or system failure | `HALT:BLOCKED` | Halt immediately; orchestrator/human inspects. |

### Authorship: wrapper owns the envelope

The harness wrapper script (see `04-worker-cell.md`) writes the structural
envelope — never the raw LLM. Letting the LLM construct the JSON risks syntax
errors, missed fields, or hallucinated exit codes. Pattern: the agent writes a
small informal summary file or emits a standard output trailer; the wrapper
catches process termination, runs `git rev-parse HEAD` and
`git diff --name-only`, inspects the tactile exit code, collects telemetry,
and serializes the formal schema-valid receipt.

### Tactile ground-truth rule

A non-zero `tactile_command` exit is an absolute ground-truth assertion →
automatic `FAILED`. The agent **cannot** override a test failure with text
justification (blocks model self-deception). `agent_summary` is preserved for
next-attempt diagnostics only. Timeout: wrapper kills the command after
`tactile_timeout_seconds`, records exit code `124`, and prints
`"Command timed out after N seconds"` to stderr.

### Telemetry

`token_metrics` fields are nullable. The wrapper best-effort parses
client-native logs (Claude Code `--verbose` JSONL, OpenCode execution
summaries); formats drift across CLI releases and non-interactive runs
sometimes drop metrics. Parse failure → `null`; telemetry gaps never crash
the wrapper or block the workflow.

## `PROGRESS.md`

Flat, ordered checklist with a structured task header:

```markdown
# Ephemeral Task Execution: TASK-402

- [x] Analyze sensor finding: Reflected XSS at src/api/search.ts:58
- [ ] Implement input sanitization using sanitizeHtml utility
- [ ] Verify local unit test passes (`npm test search.test.ts`)
- [ ] Emit clean commit and self-terminate
```

Ownership:

- **Production:** Temporal renders a transient single-task `PROGRESS.md` into
  the worker directory at spawn. The agent checks off sub-steps of that task
  only. The global view is synthesized downstream as commits merge.
- **PoC shortcut:** a checked-in multi-task file the agent reads and edits
  directly (Huntley pattern). The prompt constrains the agent to toggle only
  the first unchecked item (`- [ ]` → `- [x]`), and the worker's commit must
  include the edited `PROGRESS.md` alongside code changes.

## Verification path exception

`allowed_paths` plus `/sandbox/PROGRESS.md` (PoC mode) plus
`/sandbox/.task/task_receipt.json` constitute the clean-commit set. The
`.task/` frame file `current_task.json` itself is read-only by convention —
the wrapper writes only the receipt there.

## Rules

- Worker filesystem is a scratchpad: only the receipt + diff leave the cell.
- Workers never mutate shared progress/ledger state directly.
- Workers never write hold-out evals (read-only mounts per `04-worker-cell.md`).
- Never weaken tests to pass: no editing assertions/mocks to green, no
  commenting out failures. Failing gate = adaptive repair (keep diff + exact
  trace) then strike-2 reset.
- Injected failure traces are UNTRUSTED DATA (failing assertion only, never
  execution environment — see the injection bound in `03-inner-loop.md`).

## Open questions

- ~~JSON Schema (draft 2020-12) files for both artifacts — checked in where?~~ Resolved 2026-09-22 for triage: `schemas/triage-result.schema.json` (verdict + frame fields, validated in `analyze-issue.py` before curation — see `02-control-plane.md` sufficiency gate). Frame/receipt schemas still open.
- `PROGRESS.md` projection trigger (per checkpoint vs. per attempt)?
- Receipt size limits and diff encoding beyond the 50-line/4KB tail?
- Temporal workflow SDK: TypeScript recommended, pending lock (non-blocking for 07/04).
