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

Repo working directory (locked 2026-09-18): every repo-scoped wrapper op
(git identity, rev-parse/diff SHAs, `tactile_command`, agent dispatch)
resolves to the cell checkout — `/sandbox/repo` when present
(`--repo-dir` / `CELL_REPO_DIR` override, else process cwd for
offline/host use). The `sandbox exec --workdir` (`/sandbox`) is NOT the
repo: running there yields "not in a git directory" identity failures,
file-not-found tactile verdicts, and `unknown` SHAs (all observed live
on the first in-cell run). `tactile_command` frames stay repo-relative.

Fail-closed checkout (locked 2026-09-18): where a checkout is promised —
in-cell, or under an explicit `--repo-dir` / `CELL_REPO_DIR` override —
a resolved repo without `.git` halts `BLOCKED` (`cell repo checkout
missing or invalid`) instead of evaluating the wrong directory into a
confusing `FAILED`. Seeding failures cannot self-heal on retry (same
per-task cell), so `HALT` semantics fit. Offline cwd-fallback use
without an override stays lenient.

Transfer path (locked, Tier-1 host-side push only): the wrapper and agent
perform local git ops only (branch use, commit, `rev-parse`, `diff`) —
never `clone`/`push`/`fetch`, and no git credentials ever enter the cell.
The wrapper writes the non-secret commit identity
(`user.name`/`user.email`, e.g. `Ralph Worker`) into the cell repo config
before dispatching, since nothing else sets it in-cell. Candidate code
leaves the cell exclusively as a `git bundle` downloaded by the host
promotion activity (see `02-control-plane.md`); a gitconfig credential
helper was considered and rejected (agent-overridable via `git -c`,
`GIT_CONFIG_*`, `HOME`, `--no-verify`), as was in-cell push even scoped —
cf. fullsend ADR-0032 (tier 1 default for public repos) and ADR-0017
(credentials never enter the sandbox).

Scope note on the `github` skill: the skill's "do not use git except
cloning" rule binds the *agent*. The wrapper is harness infrastructure, not
the agent — its `git rev-parse` / `git diff` / `git commit` plumbing calls
are exempt by design.

## Lifecycle: one cell per task, exec per attempt (true ephemerality)

- Freshness comes from process exit, not sandbox churn: each attempt is a new
  headless `opencode run` via `sandbox exec`. Files + git persist in the cell
  across attempts (the Ralph pattern); conversational context never does.
  Persistence of record is Git commits + Temporal state.
- Naming: `cell-<task_id>-<short_uuid>` — task-scoped (attempt index moved to
  labels), e.g. `cell-TASK-402-a9f2`.
- Owner: the laptop-local Temporal workflow worker (see `02-control-plane.md`
  locality). It shells out to the local `openshell` CLI. Create on task open
  (keepalive is runtime-provided — pass no initial command); delete at
  terminal state in a `finally` block
  (or on activity timeout) — no orphaned sandboxes. **Explicit delete (locked):**
  `--no-keep` was considered and rejected — it deletes the sandbox when the
  initial command exits, which risks losing the receipt on wrapper crash
  before `sandbox download` runs. Receipt-first, then delete, always.
- Cell loss mid-task: recreate, re-upload repo at the ledger's last commit
  SHA, resume at the current attempt (see `03-inner-loop.md`).

## Spawn contract (real CLI, verified against `openshell --help`)

Base image for PoC spawns: `quay.io/jwesterl/worker-cell:2026-09-18-f33cc67`
(the cell layer below, pulled — no local build step at spawn time),
built atop `quay.io/jwesterl/openshell-base:latest` (the checked-in
CentOS build). The cell layer (`docker/worker-cell.Dockerfile`, `ARG
BASE_IMAGE`) adds the Ralph-loop contract (prompt, harness, OpenCode
config) that the base deliberately lacks. Tag convention (locked
2026-09-18): immutable `date-shortsha` tags naming the baked-content
commit — never retag changed content under an existing tag (the
gateway may resolve by tag with pull-through cache semantics, silently
running stale layers); the spawner default (`CELL_IMAGE_PINNED` in
`scripts/spawn-cell.sh`) moves forward only to pushed, digest-verified
tags. Entrypoint stays the base default (`/bin/bash`); cell keepalive is provided
by the sandbox runtime (no `CMD` in the checked-in Dockerfiles — the pushed
base / gateway driver holds it), so `create` takes no initial command, and
the wrapper is invoked explicitly per exec — never as PID 1.
**No trailing command + async create (locked 2026-09-18):** cell keepalive
is runtime-provided, so `create` takes no initial command. The `create` CLI
stays attached to the running keepalive and does not return on its own —
observed >300s with `-- sleep infinity` and >240s without, cell `Ready`
server-side in both cases. So the spawner (`scripts/spawn-cell.sh`
`create`) backgrounds the call and polls `sandbox get -o json` until
`phase == Ready` (bounded `CREATE_WAIT_TRIES` × `CREATE_WAIT_INTERVAL`),
with best-effort delete on failure/timeout. Sandbox names must be lowercase
alphanumerics/hyphens.

```bash
openshell sandbox create \
  --name "cell-${TASK_ID_LOWER}-${UUID4}" \
  --from quay.io/jwesterl/worker-cell:2026-09-18-828dd5b \
  --policy /abs/path/to/policy/upstream-base-policy.yaml \
  --provider "${CRED_PROVIDER:-opencode-go}" \
  --env "OPENCODE_CONFIG=/etc/opencode/opencode.json" \
  --approval-mode manual \
  --no-auto-providers \
  --cpu "${CELL_CPU:-1}" --memory "${CELL_MEM:-4Gi}" \
  --label "task=${TASK_ID}"
# (no --upload here: the repo seed follows post-Ready as a tarball, and
# per-attempt files ride upload-to-dir + mv — see below and ingestion.)
```

## Exec-per-attempt contract

Each attempt (Temporal activity):

```bash
# 1. Deliver the attempt frame (frame changes per attempt: N, sensor_context)
#    via upload-to-dir + mv (see dir-semantics note below)
openshell sandbox upload "${CELL}" "${FRAME_JSON}" /sandbox/.task/
openshell sandbox exec -n "${CELL}" --workdir /sandbox/.task --timeout 60 -- \
  mv -- "<FRAME_JSON basename>" current_task.json
# 2. Run the wrapper (exit code propagates; --timeout bounds the attempt)
openshell sandbox exec -n "${CELL}" --workdir /sandbox \
  --timeout "${EXEC_TIMEOUT}" -- /usr/local/bin/cell-harness \
  --attempt "${ATTEMPT}" --frame /sandbox/.task/current_task.json \
  --receipt /sandbox/.task/task_receipt.json
# 3. Collect the receipt (Temporal gates on it)
openshell sandbox download "${CELL}" /sandbox/.task/task_receipt.json "${OUT_DIR}/"
```

(`upload`/`download` take positional `NAME PATH [DEST]` — no `-n`, no
`local:dest` colon form; verified against CLI help 2026-09-18. `upload`
treats `DEST` as a directory (observed live 2026-09-18: uploading to a
file path yields a directory containing the file under its basename —
there is no file-vs-dir flag), so the spawner uploads to
`/sandbox/.task/` and `mv`s into place (`current_task.json`,
`worker_prompt.txt`), repairing stale dirs so retries heal the same
cell. `download` to a directory lands the file under its basename.)
The child stages fixed filenames (`current_task.json`,
`worker_prompt.txt`), so source and target routinely coincide — those
already land in place and the `mv` is skipped (it would fail "same
file"; observed live on the first Temporal run).

Flag notes (all verified in CLI help unless marked):
- `--policy` needs an **absolute, readable path** — relative paths fail
  depending on cwd (observed in the probe). The spawner asserts readability
  before invoking `create`.
- `--provider` is repeatable and the only path for secrets; `--env` help
  text explicitly forbids credentials there. (`ANTHROPIC_BASE_URL` remains a
  valid non-secret `--env` hint only on the Claude-Code-via-proxy path.)
- `--upload` of single files to a directory is the deterministic transfer
  primitive (driver-portable; host bind-mounts may not exist under the
  Kubernetes driver). Directory sources are never uploaded directly —
  `DEST` treats them as place-inside (observed live: the whole source dir
  nested one level down, see ingestion). `.gitignore` filtering applies
  by default — the tarball seed carries the complete tree regardless.
- `--approval-mode manual` (the default): agent-authored policy proposals wait
  in a draft inbox for human review. `auto` (empty-delta auto-approve) is a
  documented opt-in only — default-deny posture preserved for the PoC.
- `--no-auto-providers` in the spawner: fail loudly on a missing provider
  instead of prompting / erroring opaquely.
- Per-task creation means `--upload` of the repo seed happens once; only the
  small frame file is re-uploaded per attempt.

## Inference model: OpenCode-hosted catalog via attached provider (locked)

OpenCode speaks its first-party hosted catalogs directly: the in-cell
`OPENCODE_API_KEY` (injected, placeholder-masked, by the attached
`opencode-go` provider — never `--env`, never disk) authenticates against
`opencode.ai` + `models.opencode.ai`, both in the adopted policy's `opencode`
block. No `baseURL` override, no `auth.json` seeding, no proxy placeholder
on this path. Proven live 2026-09-17: `opencode --model
opencode-go/muse-spark-1.3-contributor run` succeeds headless in-cell via
`sandbox exec` (first attempt `policy_denied` on `models.opencode.ai`,
approved live under `--approval-mode manual`, second attempt self-identified
correctly). The `models.opencode.ai` endpoint and both binary paths
(`.opencode` + `opencode.exe`) are now persisted in the baseline so future
cells need no approval for this model.

- Template default: `config/opencode-sandbox.json` pins
  `model: opencode-go/muse-spark-1.3-contributor` and
  `small_model: opencode-go/glm-5` (changeable later); per-run override via
  `opencode run --model <id>` (future: a `model` frame field flowing into the
  wrapper invocation — recorded, not built).
- Provider profile scope (locked 2026-09-18): `policy/opencode-profile.yaml`
  scopes `OPENCODE_API_KEY` injection to `opencode.ai` +
  `models.opencode.ai` only (L7 `rest`/`enforce`, opencode + node binaries —
  no `curl`). npm registry + nvidia network access stays in the sandbox
  network-policy baseline (`policy/upstream-base-policy.yaml` `opencode`
  block), not in the credential profile: the gateway linter rejects L4-only
  endpoints on credentialed profiles, and L7-promoting them would wrongly
  inject the bearer there. Imported workspace-scoped on the gateway
  (`openshell provider profile import` → `list-profiles` shows
  `opencode … user … 2 inference`); headless re-proven live
  (`opencode run --model opencode-go/muse-spark-1.3-contributor`, exit 0).
  In-cell injection re-proven live 2026-09-18 on `jwesterl-test`
  (`cell-probe-5a27`, `--provider opencode-go`, updated profile
  `resource_version: 2`): headless run exited 0 with `PROBE_OK`,
  approval-free (no `policy_denied` on `models.opencode.ai`),
  `OPENCODE_API_KEY` present in-cell via provider injection; cell deleted
  after the probe, no orphans. Naming note: sandbox names must be lowercase
  alphanumerics/hyphens (uppercase rejected at create).
- Pricing/terms note: hosted-catalog models carry their own pricing and data
  terms (some discounted tiers permit training use of prompts/completions) —
  check the active model's terms before routing proprietary code; revisit at
  promotion time.
- Retained alternative: Claude Code via L7 `inference.local` placeholder +
  attached provider (`ANTHROPIC_BASE_URL`, proxy rewrites URL and injects the
  real token). That path is documented, not deleted — but it is not the PoC
  default.

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

1. Host spawner prepares a fresh workspace dir: clones the frame's
   `repo_url` (public https, no credentials — auth lives only in the
   provider-injected cell env and the owner's host `gh`), checks out
   `target_branch`. A missing workspace dir fails `create` before any
   `openshell` call (fail fast, no orphan cells).
2. `sandbox create` takes no initial command and no `--upload` (keepalive
   is runtime-provided; the spawner polls to `Ready`). Once `Ready`, the
   spawner seeds the checkout as a tarball: `tar -czf` the workspace
   (dotfiles and `.git` included), upload the single file to
   `/sandbox/repo/`, `exec` extract + remove tarball, then assert
   `repo/.git` exists. Any seeding failure deletes the cell — a repo-less
   cell never boots into an attempt.
3. Per attempt: upload the frame to `/sandbox/.task/` + `mv` into place
   (`current_task.json`, plus `worker_prompt.txt` override when present),
   `exec` the wrapper, `download` the receipt even on harness failure
   before propagating its status (see exec contract above).

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
> * Output a final summary of changes and the word COMPLETE.
> * Never ask questions or wait for input — there is no user attached. If
>   you cannot proceed, write your summary, state what blocked you, and
>   finish."

Tool equivalents:

- OpenCode (non-interactive batch mode):
  `opencode run --auto --model <id> "$(cat /etc/prompts/worker_contract.txt)"`
  (`--auto` auto-approves everything not explicitly denied; paired with
  `"permission": "allow"` in `config/opencode-sandbox.json` so nothing —
  notably `question`, `doom_loop`, `external_directory`, which default to
  `ask` — can stall a headless cell waiting on input. Same posture as the
  Claude flag below: OpenShell's external Landlock/seccomp policy is the
  actual security perimeter. Locked 2026-09-18.)
- Claude Code (headless print mode):
  `claude -p "$(cat /etc/prompts/worker_contract.txt)" --dangerously-skip-permissions --no-auto-updater`
  (`--dangerously-skip-permissions` is expected for non-interactive
  CI/container runs; OpenShell's external Landlock/seccomp policy is the
  actual security perimeter.)

## Delivery tiers: image-immutable vs. host-injected per attempt

`/usr` and `/etc` are read-only at runtime, so anything living there must
arrive via the image build — nothing can be uploaded or created in-cell.
Within that constraint, artifacts split three ways (locked 2026-09-18):

| Artifact | Delivery | Mutability |
|----------|----------|------------|
| `cell-harness` (`/usr/local/bin`) | Image-baked only | Immutable — the judged agent can never rewrite the judge (anti-gaming load-bearing, see `03-inner-loop.md`). |
| Worker prompt | Image default (`/etc/prompts/worker_contract.txt`) + per-attempt host-upload override (`/sandbox/.task/worker_prompt.txt`) | Host varies it per task/attempt; agent never persists it (re-uploaded every attempt; flows through Temporal activity inputs so history records what the worker was told). Override source: explicit `PROMPT_FILE` env wins, else `prompts/overrides/<TASK_ID>.txt`, else the image default. |
| OpenCode config (`/etc/opencode/opencode.json`, source `config/opencode-sandbox.json`) | Image-baked defaults + per-run `--model` CLI override | Defaults frozen. opencode needs blanket permission from config (unlike Claude's `--dangerously-skip-permissions` flag), so the file must exist in-cell; auth still arrives only via the attached provider. |

## Failure modes

- Credential exposure via env inspection → prevented by provider injection +
  credential masking.
- Lateral movement (network scan, metadata-service exploitation, escape) →
  prevented by process isolation, path scoping, egress default-deny.
- State leakage across attempts → prevented by fresh process per exec
  (no conversational carryover; cell filesystem reset via `retry_strategy`).
- Agent overriding tactile failure with justification → structurally
  impossible: wrapper maps nonzero tactile exit to `FAILED` regardless of
  agent text (see `07-contracts.md`).

## Open questions

- Gateway prerequisite: `gateway login` + Connected status before any spawn;
  the spawner fails fast otherwise (no silent misroute).
- Deltas from the upstream baseline (OpenRouter? general npm?) — list or close.
- Provider per model backend: PoC default `opencode-go` (type `opencode`);
  Claude-Code path needs its own provider name when activated.
- Resource values (CPU/mem/GPU, wall-clock) per attempt — flags pinned,
  numbers TBD under real attempt-latency data.
- Sandbox image registry + build/push flow for base and cell layers.
