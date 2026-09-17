# Specs — Enterprise Durable Ralph Loop

High-level index for agents. Raw source: [`intent.md`](./intent.md) (frozen provenance).
Per-topic files below are the normative detail — load only what you need.

## What this is

Industrial-grade autonomous coding loop based on the "Ralph Wiggum Loop":
zero context rot via ephemeral process lifecycles and filesystem-driven state
persistence, replacing brittle shell scripts with a durable distributed fabric
(Temporal orchestration + governed worker cells + deterministic release at the PR boundary).

## Topology (copied verbatim from `intent.md` §3)

```mermaid
flowchart TD
    subgraph T1 [Tier 1: Macro Control Plane - Temporal Parent Workflow]
        A1[Webhook Ingestion: Issue / PR / Label] --> A2[Task Decomposition Ledger]
        A2 --> A3[Sensor Inversion: SonarQube / Snyk / DAST]
        A3 --> A4[Multi-Agent Review Panel]
        A4 --> A5[PR Promotion & Downstream Release Trigger]
    end

    subgraph T2 [Tier 2: Inner-Loop State Engine - Temporal Child Workflow]
        B1[Project Task Frame: current_task.json] --> B2[Dispatch to Worker Pod]
        B2 --> B3[Evaluate Deterministic Gates: Tree-sitter & Hold-Out Tests]
        B3 -->|Pass| B4[Commit Checkpoint to Git Branch]
        B3 -->|Fail| B5[Atomic Git Reset & continue_as_new]
    end

    subgraph T3 [Tier 3: Governed Worker Cell - OpenShift + Nvidia OpenShell]
        C1[Nvidia OpenShell Policy Boundary] --> C2[Filesystem Jailing: Read-Only Root & Evals]
        C1 --> C3[Egress Proxy with In-Flight Token Injection]
        C1 --> C4[Ephemeral Worker CLI: Claude Code / OpenCode]
    end

    T1 -->|Spawns & Coordinates| T2
    T2 -->|Executes Non-Interactive Command| T3
    T3 -->|Emits task_receipt.json| T2
```

## Spec index

| Spec | Read this when… |
|------|-----------------|
| [`01-principles.md`](./01-principles.md) | You need the architectural invariants (context hygiene, Temporal as source of truth, CI inversion, zero-trust sandbox). |
| [`02-control-plane.md`](./02-control-plane.md) | You work on the Temporal Parent: ingestion, decomposition ledger, SLAs, review panel, PR promotion. |
| [`03-inner-loop.md`](./03-inner-loop.md) | You work on the Temporal Child: Ralph cycle, `continue_as_new`, gates, commit vs. atomic reset. |
| [`04-worker-cell.md`](./04-worker-cell.md) | You work on the OpenShift + OpenShell worker: jailing, egress proxy, ephemeral CLI invocation. |
| [`05-sensors.md`](./05-sensors.md) | You work on upstream static/security sensors (SonarQube, CodeQL, Snyk, Trivy, DAST) and their SARIF/JSON contracts. |
| [`06-release.md`](./06-release.md) | You work on the deterministic release pipeline (Tekton/ArgoCD) at/after the PR boundary. |
| [`07-contracts.md`](./07-contracts.md) | You need artifact schemas: `current_task.json`, `task_receipt.json`, `PROGRESS.md` projection rules. |

## Conventions

- `intent.md` is frozen raw source. If a per-topic spec conflicts with it, flag it — don't silently diverge.
- Per-topic files follow: Goal → Non-goals → Inputs/Outputs → Flow → Failure modes → Open questions.
- Gaps go under Open questions, not invented detail.
