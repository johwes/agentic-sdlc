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
#   BASE_IMAGE     optional, default quay.io/jwesterl/openshell-base:latest
#   POLICY         optional, default policy/upstream-base-policy.yaml (abs path resolved)
set -euo pipefail

cmd="${1:-}"; shift || true

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
    --from "${BASE_IMAGE:-quay.io/jwesterl/openshell-base:latest}" \
    --policy "${policy}" \
    --provider "${CRED_PROVIDER:-opencode-go}" \
    --env "OPENCODE_CONFIG=/etc/opencode/opencode.json" \
    --upload "${WORKSPACE_DIR}:/sandbox/repo" \
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

do_exec_attempt() {
  : "${CELL:?set CELL}" "${FRAME_JSON:?set FRAME_JSON}" "${ATTEMPT:?set ATTEMPT}"
  local out="${OUT_DIR:-.}"
  openshell sandbox upload "${CELL}" "${FRAME_JSON}" /sandbox/.task/current_task.json
  if [[ -n "${PROMPT_FILE:-}" ]]; then
    if [[ ! -r "${PROMPT_FILE}" ]]; then
      echo "prompt file not readable: ${PROMPT_FILE}" >&2
      return 1
    fi
    openshell sandbox upload "${CELL}" "${PROMPT_FILE}" /sandbox/.task/worker_prompt.txt
  fi
  openshell sandbox exec -n "${CELL}" --workdir /sandbox \
    --timeout "${EXEC_TIMEOUT:-600}" -- /usr/local/bin/cell-harness \
    --attempt "${ATTEMPT}" --frame /sandbox/.task/current_task.json \
    --receipt /sandbox/.task/task_receipt.json
  openshell sandbox download "${CELL}" /sandbox/.task/task_receipt.json "${out}/"
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
