#!/usr/bin/env bash
# Worker cell lifecycle (see specs/04-worker-cell.md).
#
# One cell per task (keepalive `sleep infinity`); one `exec` per attempt.
# Temporal activity boundaries: create -> exec-attempt (xN) -> destroy.
#
# Usage:
#   ./scripts/spawn-cell.sh create       # TASK_ID, WORKSPACE_DIR, CRED_PROVIDER
#   ./scripts/spawn-cell.sh exec-attempt # CELL, FRAME_JSON, ATTEMPT [, OUT_DIR]
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
#   EXEC_TIMEOUT   sandbox exec timeout secs, default 600 (exec-attempt)
#   UUID4          optional 4-hex suffix; generated when unset (create)
#   CELL_CPU       optional, default 1 (create)
#   CELL_MEM       optional, default 4Gi (create)
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
  local cell="cell-${TASK_ID}-${uuid}"
  local policy
  policy="$(resolve_policy)"
  echo "creating ${cell}" >&2
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
    -- sleep infinity
  printf '%s\n' "${cell}"
}

do_exec_attempt() {
  : "${CELL:?set CELL}" "${FRAME_JSON:?set FRAME_JSON}" "${ATTEMPT:?set ATTEMPT}"
  local out="${OUT_DIR:-.}"
  openshell sandbox upload -n "${CELL}" "${FRAME_JSON}:/sandbox/.task/current_task.json"
  openshell sandbox exec -n "${CELL}" --workdir /sandbox \
    --timeout "${EXEC_TIMEOUT:-600}" -- /usr/local/bin/cell-harness \
    --attempt "${ATTEMPT}" --frame /sandbox/.task/current_task.json \
    --receipt /sandbox/.task/task_receipt.json
  openshell sandbox download -n "${CELL}" /sandbox/.task/task_receipt.json "${out}/"
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
