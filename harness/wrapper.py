#!/usr/bin/env python3
"""Cell harness entrypoint (skeleton).

Runs inside the worker cell as the `openshell sandbox exec` entrypoint.
Full behavior is specified in specs/04-worker-cell.md and
specs/07-contracts.md. This skeleton defines the stage order only:

1. Load /sandbox/.task/current_task.json (read-only).
2. Dispatch the agent CLI (opencode / claude) with the contract prompt.
3. Capture stdout/stderr; collect the agent's summary trailer.
4. Run forbidden_paths diff assertion -> BLOCKED / HALT:BLOCKED (no retry).
5. Run tactile_command (timeout, 50-line tail) -> nonzero means FAILED.
6. Collect git rev-parse HEAD + git diff --name-only + token telemetry
   (nullable, best-effort).
7. Serialize schema-valid task_receipt.json to
   /sandbox/.task/task_receipt.json.

Exit code mirrors the receipt outcome for `sandbox exec` propagation.
"""

from __future__ import annotations

import sys


def main() -> int:
    print("cell-harness skeleton: not yet implemented (see specs/04-worker-cell.md).")
    return 2


if __name__ == "__main__":
    sys.exit(main())
