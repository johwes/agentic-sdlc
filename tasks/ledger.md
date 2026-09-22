# Task Ledger — Temporal projection (PoC stub)

> Temporal workflow state is the source of truth (see `specs/01-principles.md`).
> This file is a Temporal-rendered projection — never hand-edit
> (see `specs/02-control-plane.md` ledger). Seed stub until the parent
> workflow projects live rows. Task states:
> `inbox → active → review → promoted | escalated`.

| task_id | state | attempt/max_attempts | child_workflow_id | commit_shas | final_receipt | pr_url | updated_at |
|---------|-------|----------------------|-------------------|-------------|---------------|--------|------------|
| TASK-1 | promoted | 1/5 | child-TASK-1 | 2fbb119ef54b7a533445da4310423bb36ea99f5e | SUCCESS/COMPLETE | https://github.com/johwes/tic-tac-toe/pull/4 | 2026-09-21T12:50:14+00:00 |
| TASK-402 | inbox | 1/5 | - | - | - | - | - |
| TASK-403 | promoted | 1/5 | child-TASK-403 | c087968c2bdaed978433a39d0e0675dc0f5da497 | SUCCESS/COMPLETE | https://github.com/johwes/tic-tac-toe/pull/1 | 2026-09-21T08:07:27+00:00 |
