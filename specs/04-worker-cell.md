# 04 — Governed Worker Cell (OpenShift + Nvidia OpenShell)

Source: `intent.md` §§1–3 (T3). Fleshed out via spec interview (round 3).
PoC stance: take shortcuts, host in OpenShift/OpenShell where free. The
OpenShell environment (gateway + `openshell` CLI sandbox management) is
provided — not managed by this project.

## Goal

Run ephemeral agent CLI processes (Claude Code or OpenCode, pluggable) under
OpenShell policy jailing and provider-injected credentials.

## Non-goals

- Task orchestration or gating (see `02-control-plane.md`, `03-inner-loop.md`).
- Release packaging (see `06-release.md`).

## Image: custom `docker/worker-cell.Dockerfile`

Committed to this repo. Rationale: base community images cost per-task
download latency and risk non-reproducible runs.

Contents:

- Base OS: Ubuntu/Debian slim.
- Dual runtimes: Node.js (LTS) + Python 3.11+ (primary project ecosystems).
- Tooling: `git`, `jq`, `curl`, OpenCode CLI, Claude Code CLI.
- System files baked in: `/etc/prompts/worker_contract.txt` (source:
  `prompts/worker_contract.txt`) and the wrapper at
  `/usr/local/bin/cell-harness` (source: `harness/wrapper.py`).

## Wrapper: `harness/wrapper.py` (Python 3)

Repo source, baked into the image. Python for clean JSON handling, robust
subprocess isolation, and native OpenShell SDK pairing.

Role: runs inside the container as the `openshell sandbox exec` entrypoint.
It dispatches the target CLI, captures stdout/stderr, runs `git diff` and the
`tactile_command` checks (timeout, truncation, exit integrity per
`07-contracts.md`), enforces the `forbidden_paths` post-execution diff
assertion, collects token telemetry (nullable, best-effort), and serializes
the schema-valid `task_receipt.json`. It owns the envelope; the agent only
supplies an informal summary/trailer.

## Lifecycle: fresh sandbox per attempt (true ephemerality)

- No state carries over between attempts. Persistence is strictly via Git
  commits + Temporal state.
- Naming: `cell-<task_id>-att<attempt_index>-<short_uuid>` (4 hex chars,
  spawner-generated), e.g. `cell-task402-att1-a9f2`.
- Owner: the Temporal workflow worker. Creation before execution; cleanup via
  `openshell sandbox delete` in a `finally` block (or on activity timeout) —
  no orphaned sandboxes.

## Providers, policy, network

- **Inference credentials:** OpenShell named providers
  (`openshell provider create`). Keys are injected via the OpenShell secrets
  engine into the sandbox runtime env — never into code, files, or shell
  history. (Auto-discovered env creds are a local-dev fallback only.)
- **Network (PoC policy):** default-deny all outbound; allowlist:
  - LLM endpoint domains (`api.anthropic.com`, `api.openai.com`, …).
  - Package registries (`registry.npmjs.org`, `pypi.org`) only when the task
    explicitly allows installation.
  - GitHub API / host git remote only when fetching submodules/external context.
- **Filesystem mounts:**
  - `/workspace/.task/` read-write — frame in, receipt out (frame file itself
    read-only by convention; wrapper writes only the receipt).
  - `forbidden_paths` enforced via OpenShell/Landlock profiles where
    available, otherwise via the wrapper's post-execution diff assertion →
    `BLOCKED` / `HALT:BLOCKED` (see `07-contracts.md`). `forbidden_paths`
    violations never retry: path failure signals frame/repo mismatch needing
    orchestrator/human inspection, and retry would let workers fuzz
    restricted boundaries.

## Repo + task ingestion sequence

1. Host spawner prepares a fresh workspace dir, checks out `target_branch`.
2. Bind-mount into the container at `/workspace`.
3. Temporal worker writes `/workspace/.task/current_task.json` **before**
   invoking `openshell sandbox exec`.
4. Container reads contract state from that file at start; wrapper dispatches
   the agent CLI.

## Worker prompt contract (canonical)

Functionally identical across tools, adapted to each CLI's native interface.
Source of truth: `prompts/worker_contract.txt` (synced to
`/etc/prompts/worker_contract.txt` in the image).

> "You are an autonomous execution worker running in a constrained ephemeral
> cell. Your sole task is defined in /workspace/.task/current_task.json.
> * Inspect the codebase and the sensor_context provided in the task file.
> * Make minimal, precise changes to files specified in allowed_paths. Do not
>   touch files outside this list.
> * Run the command specified in tactile_command to verify your changes.
> * Once tests pass, create a git commit with a descriptive message
>   referencing the task_id.
> * Output a final summary of changes and the word COMPLETE."

Tool equivalents:

- OpenCode (non-interactive batch mode):
  `opencode run --prompt "$(cat /etc/prompts/worker_contract.txt)"`
- Claude Code (headless print mode):
  `claude -p "$(cat /etc/prompts/worker_contract.txt)" --dangerously-skip-permissions --no-auto-updater`
  (`--dangerously-skip-permissions` is expected for non-interactive
  CI/container runs; OpenShell's external Landlock/seccomp policy is the
  actual security perimeter.)

## Failure modes

- Credential exposure via env inspection → prevented by provider injection +
  credential masking.
- Lateral movement (network scan, metadata-service exploitation, escape) →
  prevented by process isolation, path scoping, egress default-deny.
- State leakage across attempts → prevented by fresh-sandbox-per-attempt.
- Agent overriding tactile failure with justification → structurally
  impossible: wrapper maps nonzero tactile exit to `FAILED` regardless of
  agent text (see `07-contracts.md`).

## Open questions

- OpenShell policy bundle location/versioning (in-repo `policy/` dir?).
- Exact provider names per model backend.
- Resource limits (CPU/mem/GPU, wall-clock) per attempt.
- Sandbox image registry + build/push flow for the custom Dockerfile.
