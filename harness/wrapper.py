#!/usr/bin/env python3
"""Cell harness command (skeleton).

Invoked explicitly per attempt via `openshell sandbox exec` (see
specs/04-worker-cell.md) — never PID 1. One invocation = one attempt = one
fresh agent process (the Ralph freshness unit).

Usage:
    cell-harness --attempt N --frame /sandbox/.task/current_task.json \
        --receipt /sandbox/.task/task_receipt.json

Stage order per invocation:

1. Load --frame (read-only).
2. Dispatch the agent CLI (opencode / claude) with the contract prompt.
3. Capture stdout/stderr; collect the agent's summary trailer.
4. Run forbidden_paths diff assertion -> BLOCKED / HALT:BLOCKED (no retry).
5. Run tactile_command (timeout, 50-line tail) -> nonzero means FAILED.
6. Collect git rev-parse HEAD + git diff --name-only + token telemetry
   (nullable, best-effort).
7. Serialize schema-valid task_receipt.json to --receipt.

Exit code mirrors the receipt outcome for `sandbox exec` propagation.

Auth note: OpenCode reads OPENCODE_API_KEY from env (provider-injected,
placeholder-masked) natively — no auth.json seeding required.
"""

from __future__ import annotations

import sys


def main() -> int:
    print("cell-harness skeleton: not yet implemented (see specs/04-worker-cell.md).")
    return 2


if __name__ == "__main__":
    sys.exit(main())
