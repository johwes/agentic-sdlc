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

## Image: thin layer over the sandbox base

Base image: `docker/openshell-sandbox-image/Dockerfile` — a CentOS Stream 10
port of upstream [`NVIDIA/OpenShell-Community` `sandboxes/base`](https://github.com/NVIDIA/OpenShell-Community/tree/main/sandboxes/base)
(the Ubuntu original is kept as `Dockerfile.org` for provenance). The port
tracks upstream stage-for-stage with documented deltas: EL10 package mapping
+ `/usr/sbin` compat symlinks, distro Node.js 22.23.1 (takes the security
patch upstream's pinned 22.22.1 was still waiting for), RPM-based `gh`
install. All other pins (npm 11.11.0, uv 0.10.8, Python 3.14.3, tar/hono,
codex, copilot) match upstream; `opencode-ai` floats newer at the checked-in
pin with no standing opinion — re-pin deliberately, not by drift.

The base already provides both runtimes, all four agent CLIs, `gh`, `git`,
`curl`, the `github` skill, and the default policy. Rationale for a local
base (vs. pulling community images per task): no per-task download latency,
fully reproducible runs, auditable policy.

Our cell layer (`docker/worker-cell.Dockerfile`, `FROM` the locally built
base) adds only the Ralph-loop contract:

- `/etc/prompts/worker_contract.txt` (source: `prompts/worker_contract.txt`).
- `/usr/local/bin/cell-harness` (source: `harness/wrapper.py`), set as the
  cell `ENTRYPOINT` (base default is `/bin/bash`).

Canonical in-cell workdir is `/sandbox` (image `WORKDIR`, user `sandbox`
home) — adopted across all specs and the prompt contract.

## Wrapper: `harness/wrapper.py` (Python 3)

Repo source, baked into the image. Python for clean JSON handling, robust
subprocess isolation, and native OpenShell SDK pairing.

Role: runs inside the container as the `openshell sandbox exec` entrypoint.
It dispatches the target CLI, captures stdout/stderr, runs `git diff` and the
`tactile_command` checks (timeout, truncation, exit integrity per
`07-contracts.md`), enforces the `forbidden_paths` post-execution diff
assertion, collects token telemetry (nullable, best-effort), and serializes
the schema-valid `task_receipt.json`. It owns the envelope; the agent only
supplies an informal summary/trailer. Python stdlib only — the base image
ships no `jq`, and the wrapper must not add dependencies.

Scope note on the `github` skill: the skill's "do not use git except
cloning" rule binds the *agent*. The wrapper is harness infrastructure, not
the agent — its `git rev-parse` / `git diff` / `git commit` plumbing calls
are exempt by design.

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
- **Network policy: adopt upstream as baseline.** `policy/upstream-base-policy.yaml`
  vendors the full upstream `sandboxes/base` `policy.yaml` verbatim (per-binary
  `network_policies`; provenance header notes the source). It already encodes
  our interview allowlist: `claude_code` (anthropic), `codex` (openai),
  `opencode` (npm registry + opencode.ai + nvidia), `nvidia_inference`, `pypi`,
  read-only `github_rest_api`, read-only git smart-HTTP. Deltas from the
  baseline (if any — e.g. OpenRouter, general npm access) are documented
  amendments, not a rewrite. The checked-in minimal `policy.yaml` in
  `docker/openshell-sandbox-image/` is the image-build default only — the
  gateway-served policy governs at runtime; verify which one your gateway
  serves.
- **Policy-enforced invariants (not just spec prose):** upstream blocks pushes
  by default — `git-receive-pack` is commented out and `github_rest_api` is
  `access: read-only`. So "workers never push" and "promotion runs on the
  host" are network-enforced facts: in-cell `gh pr create` (POST) would be
  denied, which is why PR creation lives in the host Temporal promotion
  activity (see `02-control-plane.md`), never in the cell.
- **Package registries** remain conditional on the task explicitly allowing
  installation (policy permits; the frame decides).
- **Filesystem mounts:**
  - `/sandbox/.task/` read-write — frame in, receipt out (frame file itself
    read-only by convention; wrapper writes only the receipt).
  - `forbidden_paths` enforced via OpenShell/Landlock profiles where
    available, otherwise via the wrapper's post-execution diff assertion →
    `BLOCKED` / `HALT:BLOCKED` (see `07-contracts.md`). `forbidden_paths`
    violations never retry: path failure signals frame/repo mismatch needing
    orchestrator/human inspection, and retry would let workers fuzz
    restricted boundaries.

## Repo + task ingestion sequence

1. Host spawner prepares a fresh workspace dir, checks out `target_branch`.
2. Bind-mount into the container at `/sandbox`.
3. Temporal worker writes `/sandbox/.task/current_task.json` **before**
   invoking `openshell sandbox exec`.
4. Container reads contract state from that file at start; wrapper dispatches
   the agent CLI.

## Worker prompt contract (canonical)

Functionally identical across tools, adapted to each CLI's native interface.
Source of truth: `prompts/worker_contract.txt` (synced to
`/etc/prompts/worker_contract.txt` in the image).

> "You are an autonomous execution worker running in a constrained ephemeral
> cell. Your sole task is defined in /sandbox/.task/current_task.json.
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

- Gateway policy resolution: confirm the gateway serves the adopted baseline
  (not just the image-build minimal policy).
- Deltas from the upstream baseline (OpenRouter? general npm?) — list or close.
- Exact provider names per model backend.
- Resource limits (CPU/mem/GPU, wall-clock) per attempt.
- Sandbox image registry + build/push flow for base and cell layers.
