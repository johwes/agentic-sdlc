"""Laptop-local Temporal worker (PoC).

Runs the parent workflow (+ future child) as local processes on the same
machine as the `openshell` CLI — no cluster deployment (see
specs/02-control-plane.md locality). Pair with ./dev-server.sh first.

Usage:
    pip install -r temporal/requirements.txt
    python3 temporal/worker.py [--address localhost:7233]
"""

from __future__ import annotations

import argparse
import asyncio
import sys

try:
    from parent import (
        ParentWorkflow,
        dispatch_child,
        open_draft_pr,
        sensor_review,
        TASK_QUEUE,
        TEMPORAL_ADDRESS,
    )
except ImportError:  # allow `python3 -m temporal.worker` / package-style import
    from temporal.parent import (
        ParentWorkflow,
        dispatch_child,
        open_draft_pr,
        sensor_review,
        TASK_QUEUE,
        TEMPORAL_ADDRESS,
    )


async def _run(address: str) -> None:
    try:
        from temporalio.client import Client
        from temporalio.worker import Worker
    except ImportError:
        print(
            "temporalio not installed; run: pip install -r temporal/requirements.txt",
            file=sys.stderr,
        )
        raise SystemExit(2)
    client = await Client.connect(address)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[ParentWorkflow],
        activities=[dispatch_child, sensor_review, open_draft_pr],
    )
    print(f"worker polling task queue {TASK_QUEUE!r} on {address} (Ctrl-C to stop)")
    await worker.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Laptop-local Temporal worker (PoC)")
    parser.add_argument("--address", default=TEMPORAL_ADDRESS)
    args = parser.parse_args()
    asyncio.run(_run(args.address))


if __name__ == "__main__":
    main()
