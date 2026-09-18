"""File-trigger starter: inbox frame -> parent workflow (PoC).

PoC accepts the file trigger only: a hand-written current_task.json frame
dropped in tasks/inbox/TASK-<n>.json (see specs/02-control-plane.md inputs).
The frame shape is preserved so a future GitHub webhook receiver can slot
in as an alternate input adapter; until then anything webhook-shaped is
rejected with a clear signal (see 02 failure modes).

Usage:
    pip install -r temporal/requirements.txt
    python3 temporal/starter.py tasks/inbox/TASK-402.json [--address localhost:7233]
    python3 temporal/starter.py --dry-run tasks/inbox/TASK-402.json  # no server needed
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

try:
    from parent import (
        ParentInputs,
        ParentWorkflow,
        TASK_QUEUE,
        TEMPORAL_ADDRESS,
        load_frame,
    )
except ImportError:  # allow `python3 -m temporal.starter` / package-style import
    from temporal.parent import (
        ParentInputs,
        ParentWorkflow,
        TASK_QUEUE,
        TEMPORAL_ADDRESS,
        load_frame,
    )


def describe_dry_run(frame_path: str, frame: dict) -> str:
    task_id = frame.get("task_id", "unknown")
    return (
        f"dry-run: would open ParentWorkflow "
        f"(workflow_id=parent-{task_id}, task_queue={TASK_QUEUE!r}) "
        f"from {frame_path} "
        f"(attempt {frame.get('attempt', '?')}/{frame.get('max_attempts', '?')}, "
        f"branch {frame.get('target_branch', '?')})"
    )


async def _start(address: str, frame_path: str, frame: dict) -> str:
    try:
        from temporalio.client import Client
    except ImportError:
        print(
            "temporalio not installed; run: pip install -r temporal/requirements.txt "
            "or use --dry-run",
            file=sys.stderr,
        )
        raise SystemExit(2)
    client = await Client.connect(address)
    task_id = str(frame.get("task_id", "unknown"))
    handle = await client.start_workflow(
        ParentWorkflow.run,
        ParentInputs(frame=frame, inbox_path=frame_path),
        id=f"parent-{task_id}-{uuid.uuid4().hex[:6]}",
        task_queue=TASK_QUEUE,
    )
    return str(handle.id)


def main() -> None:
    parser = argparse.ArgumentParser(description="File-trigger starter (PoC: file trigger only)")
    parser.add_argument("frame", help="Path to tasks/inbox/TASK-<n>.json")
    parser.add_argument("--address", default=TEMPORAL_ADDRESS)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the frame and print the workflow open, without a server",
    )
    parser.add_argument(
        "--webhook",
        action="store_true",
        help="Reserved future slot (see 02 open questions); rejected in PoC",
    )
    args = parser.parse_args()
    if args.webhook:
        print(
            "PoC accepts file trigger only: drop a frame in tasks/inbox/ "
            "(webhook adapter is a post-PoC slot, see specs/02-control-plane.md)",
            file=sys.stderr,
        )
        raise SystemExit(2)
    frame, err = load_frame(args.frame)
    if err is not None or frame is None:
        print(f"starter: invalid frame: {err}", file=sys.stderr)
        raise SystemExit(1)
    if args.dry_run:
        print(describe_dry_run(args.frame, frame))
        return
    workflow_id = asyncio.run(_start(args.address, args.frame, frame))
    print(f"started {workflow_id} (task_queue={TASK_QUEUE!r})")


if __name__ == "__main__":
    main()
