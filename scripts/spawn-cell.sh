#!/usr/bin/env bash
# Spawn a worker cell sandbox (skeleton — see specs/04-worker-cell.md).
#
# Implements the spawn contract: fresh sandbox per attempt, adopted policy
# baseline, credential provider (never --env secrets), OPENCODE_CONFIG
# pointer, --upload ingestion, manual approval mode, explicit-delete-in-
# finally cleanup (never --no-keep: receipt first, then delete).
#
# Usage:
#   TASK_ID=TASK-402 ATTEMPT=1 FRAME_JSON=tasks/inbox/TASK-402.json \
#     WORKSPACE_DIR=/tmp/w-TASK-402 CRED_PROVIDER=opencode-creds \
#     ./scripts/spawn-cell.sh
#
# Env (all required unless noted):
#   TASK_ID        e.g. TASK-402
#   ATTEMPT        1-indexed attempt number
#   FRAME_JSON     local current_task.json frame to upload
#   WORKSPACE_DIR  fresh target_branch checkout to upload
#   CRED_PROVIDER  openshell provider name for inference creds
#   UUID4          optional; generated when unset
#   CELL_CPU       optional, default 1
#   CELL_MEM       optional, default 4Gi
#   BASE_IMAGE     optional, default quay.io/jwesterl/openshell-base:latest
#   POLICY         optional, default policy/upstream-base-policy.yaml
set -euo pipefail

: "${TASK_ID:?set TASK_ID}" "${ATTEMPT:?set ATTEMPT}"
: "${FRAME_JSON:?set FRAME_JSON}" "${WORKSPACE_DIR:?set WORKSPACE_DIR}"
: "${CRED_PROVIDER:?set CRED_PROVIDER}"

UUID4="${UUID4:-$(python3 -c 'import uuid; print(uuid.uuid4().hex[:4])')}"
CELL_NAME="cell-${TASK_ID}-att${ATTEMPT}-${UUID4}"
BASE_IMAGE="${BASE_IMAGE:-quay.io/jwesterl/openshell-base:latest}"
POLICY="${POLICY:-policy/upstream-base-policy.yaml}"

echo "spawning ${CELL_NAME} (skeleton: exec line commented until wrapper lands)" >&2

# openshell sandbox create \
#   --name "${CELL_NAME}" \
#   --from "${BASE_IMAGE}" \
#   --policy "${POLICY}" \
#   --provider "${CRED_PROVIDER}" \
#   --env "OPENCODE_CONFIG=/etc/opencode/opencode.json" \
#   --upload "${FRAME_JSON}:/sandbox/.task/current_task.json" \
#   --upload "${WORKSPACE_DIR}:/sandbox/repo" \
#   --approval-mode manual \
#   --no-auto-providers \
#   --cpu "${CELL_CPU:-1}" --memory "${CELL_MEM:-4Gi}" \
#   --label "task=${TASK_ID}" --label "attempt=${ATTEMPT}" \
#   -- /usr/local/bin/cell-harness

# Post-attempt (Temporal activity owns this ordering):
#   openshell sandbox download -n "${CELL_NAME}" /sandbox/.task/task_receipt.json <dest>
#   openshell sandbox delete "${CELL_NAME}"   # finally block / on timeout
