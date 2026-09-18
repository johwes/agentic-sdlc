#!/usr/bin/env bash
# Worker cell lifecycle (see specs/04-worker-cell.md).
#
# One cell per task (keepalive is image/gateway-provided — pass no initial
# command); one `exec` per attempt.
# Temporal activity boundaries: create -> exec-attempt (xN) -> destroy.
#
# Usage:
#   ./scripts/spawn-cell.sh create       # TASK_ID, WORKSPACE_DIR, CRED_PROVIDER
#   ./scripts/spawn-cell.sh exec-attempt # CELL, FRAME_JSON, ATTEMPT [, OUT_DIR] [, PROMPT_FILE]
#   ./scripts/spawn-cell.sh destroy      # CELL
#
# Env:
#   TASK_ID        e.g. TASK-402 (create)
#   WORKSPACE_DIR  fresh target_branch checkout to upload (create)
#   CRED_PROVIDER  openshell provider name, default opencode-go (create)
#   CELL           cell name, e.g. cell-TASK-402-a9f2 (exec-attempt, destroy)
#   FRAME_JSON     local current_task.json frame to upload (exec-attempt)
#   ATTEMPT        1-indexed attempt number (exec-attempt)
#   OUT_DIR        receipt destination dir, default . (exec-attempt)
#   PROMPT_FILE    optional host-authored prompt override to upload as the
#                  per-attempt /sandbox/.task/worker_prompt.txt (exec-attempt;
#                  re-uploaded every attempt, never agent-persistent — the
#                  wrapper prefers it over the image default; unset = default)
#   EXEC_TIMEOUT   sandbox exec timeout secs, default 600 (exec-attempt)
#   UUID4          optional 4-hex suffix; generated when unset (create)
#   CELL_CPU       optional, default 1 (create)
#   CELL_MEM       optional, default 4Gi (create)
#   CREATE_WAIT_TRIES    optional, Ready polls, default 60 (create)
#   CREATE_WAIT_INTERVAL optional, secs between polls, default 10 (create)
#   BASE_IMAGE     optional, default the pinned cell image below (immutable
#                  date-shortsha tag — never retag changed content, see 04)
#   POLICY         optional, default policy/upstream-base-policy.yaml (abs path resolved)
set -euo pipefail

cmd="${1:-}"; shift || true

# Pinned cell image (immutable date-shortsha tag; baked content frozen at
# the named commit — later commits touch only unbaked files. Never retag
# changed content under an existing tag: the gateway may resolve by tag
# with pull-through cache semantics. See specs/04-worker-cell.md.)
CELL_IMAGE_PINNED="quay.io/jwesterl/worker-cell:2026-09-18-5d39c30"

resolve_policy() {
  local p="${POLICY:-policy/upstream-base-policy.yaml}"
  if [[ "$p" != /* ]]; then
    p="$(pwd)/${p}"
  fi
  if [[ ! -r "$p" ]]; then
    echo "policy not readable: $p" >&2
    exit 1
  fi
  printf '%s' "$p"
}

do_create() {
  : "${TASK_ID:?set TASK_ID}" "${WORKSPACE_DIR:?set WORKSPACE_DIR}"
  if [[ ! -d "${WORKSPACE_DIR}" ]]; then
    echo "workspace not a directory: ${WORKSPACE_DIR}" >&2
    return 1
  fi
  local uuid="${UUID4:-$(python3 -c 'import uuid; print(uuid.uuid4().hex[:4])')}"
  # Gateway names are lowercase-only (uppercase rejected at create); the
  # frame task_id (TASK-403) and the --label below keep canonical case —
  # the sandbox name is opaque after creation (see specs/04-worker-cell.md).
  local cell="cell-$(printf '%s' "${TASK_ID}" | tr '[:upper:]' '[:lower:]')-${uuid}"
  local policy
  policy="$(resolve_policy)"
  # The create CLI stays attached to the runtime keepalive and does not
  # return on its own (observed >240s both with and without an initial
  # command, cell Ready server-side meanwhile). Run it in the background
  # and poll `sandbox get` until PHASE=Ready (bounded); best-effort delete
  # on failure/timeout so retries never orphan cells.
  local log="${TMPDIR:-/tmp}/${cell}-create.log"
  local tries="${CREATE_WAIT_TRIES:-60}" interval="${CREATE_WAIT_INTERVAL:-10}"
  echo "creating ${cell} (log ${log})" >&2
  openshell sandbox create \
    --name "${cell}" \
    --from "${BASE_IMAGE:-${CELL_IMAGE_PINNED}}" \
    --policy "${policy}" \
    --provider "${CRED_PROVIDER:-opencode-go}" \
    --env "OPENCODE_CONFIG=/etc/opencode/opencode.json" \
    --approval-mode manual \
    --no-auto-providers \
    --cpu "${CELL_CPU:-1}" --memory "${CELL_MEM:-4Gi}" \
    --label "task=${TASK_ID}" \
    >"${log}" 2>&1 &
  local pid=$!
  local i phase
  for ((i = 0; i < tries; i++)); do
    if ! kill -0 "${pid}" 2>/dev/null; then
      wait "${pid}" || true
      echo "create exited before Ready; log tail:" >&2
      tail -20 "${log}" >&2 || true
      openshell sandbox delete "${cell}" >/dev/null 2>&1 || true
      return 1
    fi
    phase="$(openshell sandbox get "${cell}" -o json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("phase",""))' 2>/dev/null || true)"
    if [[ "${phase}" == "Ready" ]]; then
      kill "${pid}" 2>/dev/null || true
      wait "${pid}" 2>/dev/null || true
      # Seed the checkout now that the cell is Ready (post-create, so a
      # seeding failure deletes the cell instead of orphaning a repo-less
      # one — a repo-less cell can never produce a valid attempt).
      if ! seed_repo "${cell}" "${WORKSPACE_DIR}"; then
        openshell sandbox delete "${cell}" >/dev/null 2>&1 || true
        return 1
      fi
      printf '%s\n' "${cell}"
      return 0
    fi
    sleep "${interval}"
  done
  echo "create timed out waiting for Ready after $((tries * interval))s; log tail:" >&2
  tail -20 "${log}" >&2 || true
  kill "${pid}" 2>/dev/null || true
  wait "${pid}" 2>/dev/null || true
  openshell sandbox delete "${cell}" >/dev/null 2>&1 || true
  return 1
}

# Seed the cell checkout via tarball (deterministic under upload dir-semantics).
#
# Background (observed live 2026-09-18): `sandbox upload` treats DEST as a
# directory, so `--upload WORKSPACE_DIR:/sandbox/repo` nested the checkout
# one level down (/sandbox/repo/tmp.XXX/<files>, no .git at the top) and
# every attempt evaluated the wrong directory. A single-file tarball lands
# deterministically; extraction lays the tree flat, dotfiles and .git
# included. The trailing `ls repo/.git` asserts the pipeline invariant
# (host always seeds from a git clone) — a repo-less cell fails loudly
# here, never boots into an attempt. Local tarball lingers next to the
# create log on failure (debug artifact, same as the log itself).
seed_repo() {
  local cell="$1" workspace="$2"
  local tarball="${TMPDIR:-/tmp}/${cell}-seed.tar.gz"
  local base
  base="$(basename "${tarball}")"
  tar -czf "${tarball}" -C "${workspace}" . \
    || { echo "seed tarball build failed for ${workspace}" >&2; return 1; }
  openshell sandbox upload "${cell}" "${tarball}" /sandbox/repo/
  openshell sandbox exec -n "${cell}" --workdir /sandbox \
    --timeout 120 -- tar -xzf "repo/${base}" -C repo
  openshell sandbox exec -n "${cell}" --workdir /sandbox \
    --timeout 60 -- rm -- "repo/${base}"
  openshell sandbox exec -n "${cell}" --workdir /sandbox \
    --timeout 60 -- ls "repo/.git" >/dev/null
}

# Upload one host file to a fixed in-cell name under /sandbox/.task/.
# Driver semantics (observed live 2026-09-18): `sandbox upload` treats DEST
# as a directory (mkdir -p), so uploading straight to a file path yields a
# directory containing the file. Upload to the dir, then rename into place.
# Basename is validated before any openshell call (fail fast, no partial
# state); the scoped rm -rf repairs stale dirs from earlier attempts, so
# retries heal the same cell. Remote names are caller-fixed literals.
upload_file_to() {
  local cell="$1" local_path="$2" remote_name="$3"
  local base
  base="$(basename "${local_path}")"
  if [[ ! "${base}" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "refusing unsafe upload filename: ${base}" >&2
    return 1
  fi
  # Ensure the dir exists so fresh cells stay quiet (the rm below is
  # best-effort; real failures surface at upload).
  openshell sandbox exec -n "${cell}" --workdir /sandbox \
    --timeout 60 -- mkdir -p .task || true
  # Best-effort stale cleanup (missing dir on fresh cells is fine; real
  # failures surface at upload below).
  openshell sandbox exec -n "${cell}" --workdir /sandbox/.task \
    --timeout 60 -- rm -rf -- "${remote_name}" || true
  openshell sandbox upload "${cell}" "${local_path}" /sandbox/.task/
  openshell sandbox exec -n "${cell}" --workdir /sandbox/.task \
    --timeout 60 -- mv -- "${base}" "${remote_name}"
}

do_exec_attempt() {
  : "${CELL:?set CELL}" "${FRAME_JSON:?set FRAME_JSON}" "${ATTEMPT:?set ATTEMPT}"
  local out="${OUT_DIR:-.}"
  upload_file_to "${CELL}" "${FRAME_JSON}" current_task.json
  if [[ -n "${PROMPT_FILE:-}" ]]; then
    if [[ ! -r "${PROMPT_FILE}" ]]; then
      echo "prompt file not readable: ${PROMPT_FILE}" >&2
      return 1
    fi
    upload_file_to "${CELL}" "${PROMPT_FILE}" worker_prompt.txt
  fi
  # Receipt-first: the receipt is the key artifact (the wrapper writes it
  # even on BLOCKED/FAILED) — download it even when the harness reports
  # failure, then propagate the harness status. A missing receipt after a
  # completed exec is itself a loud failure, never a silent skip.
  local harness_status=0
  openshell sandbox exec -n "${CELL}" --workdir /sandbox \
    --timeout "${EXEC_TIMEOUT:-600}" -- /usr/local/bin/cell-harness \
    --attempt "${ATTEMPT}" --frame /sandbox/.task/current_task.json \
    --receipt /sandbox/.task/task_receipt.json || harness_status=$?
  openshell sandbox download "${CELL}" /sandbox/.task/task_receipt.json "${out}/"
  if [[ "${harness_status}" -ne 0 ]]; then
    return "${harness_status}"
  fi
}

do_destroy() {
  : "${CELL:?set CELL}"
  openshell sandbox delete "${CELL}"
}

case "$cmd" in
  create) do_create "$@" ;;
  exec-attempt) do_exec_attempt "$@" ;;
  destroy) do_destroy "$@" ;;
  *) echo "usage: $0 {create|exec-attempt|destroy}" >&2; exit 2 ;;
esac
