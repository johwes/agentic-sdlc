# Task Ledger — Temporal projection (PoC stub)

> Temporal workflow state is the source of truth (see `specs/01-principles.md`).
> This file is a Temporal-rendered projection — never hand-edit
> (see `specs/02-control-plane.md` ledger). Seed stub until the parent
> workflow projects live rows. Task states:
> `inbox → active → review → promoted | escalated`.

| task_id | state | attempt/max_attempts | child_workflow_id | commit_shas | final_receipt | pr_url | updated_at |
|---------|-------|----------------------|-------------------|-------------|---------------|--------|------------|
| TASK-402 | inbox | 1/5 | - | - | - | - | - |
