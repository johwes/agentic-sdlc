#!/usr/bin/env bash
# Laptop-local Temporal dev server (PoC first runs).
#
# The control plane runs on the owner's laptop — no cluster deployment, no
# remote Temporal server (see specs/02-control-plane.md locality). This
# script starts the local dev server the workers poll; a durable backend is
# a later step only if laptop-restart history loss bites.
#
# Usage:
#   ./temporal/dev-server.sh            # foreground, file-persisted dev DB
#   ./temporal/dev-server.sh --port 7233 --ui-port 8233
set -euo pipefail

PORT="7233"
UI_PORT="8233"
DB="temporal-dev.db"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --ui-port) UI_PORT="$2"; shift 2 ;;
    --db) DB="$2"; shift 2 ;;
    *) echo "usage: $0 [--port N] [--ui-port N] [--db FILE]" >&2; exit 2 ;;
  esac
done

if ! command -v temporal >/dev/null 2>&1; then
  echo "temporal CLI not found; install it to run the laptop-local dev server" >&2
  echo "(workers still poll ${PORT} once a server is up; see temporal/worker.py)" >&2
  exit 1
fi

echo "starting laptop-local Temporal dev server on ${PORT} (UI ${UI_PORT}, db ${DB})" >&2
exec temporal server start-dev --port "${PORT}" --ui-port "${UI_PORT}" --db-filename "${DB}"
