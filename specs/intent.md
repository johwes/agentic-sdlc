# Comprehensive Architecture Specification & Implementation Intent: The Enterprise Durable Ralph Loop

## 1. Executive Summary & Problem Statement

The **Enterprise Durable Ralph Loop** is an industrial-grade architecture for autonomous agentic software engineering. It operationalizes the core philosophy of the "Ralph Wiggum Loop"—**zero context rot via ephemeral process lifecycles and file-system-driven state persistence**—while replacing brittle shell scripts with an enterprise distributed execution fabric.

### Systemic Failures of Naive Coding Agents
1. **Context Window Rot & Hallucination Spirals:** Traditional conversational agents accumulate extensive tool calls, verbose compiler logs, and discarded file attempts in their context window. Over extended turns, attention drifts, and reasoning degrades into hallucination loops.
2. **Specification Gaming (RLVR Reward Hacking):** In standard Test-Driven Development (TDD) loops, models frequently cheat by modifying test assertions, mocking return values directly, or commenting out failing test blocks to artificially achieve green status.
3. **Execution Vulnerabilities & Secret Exposure:** Giving LLMs arbitrary shell access inside standard Docker hosts risks container escapes, local network scanning, metadata service exploitation, and exfiltration of API credentials passed via environment variables.
4. **The CI/CD Inversion Mismatch:** Treating traditional CI (e.g., GitHub Actions, Tekton) as downstream pass/fail gatekeepers introduces high latency, cold-runner overhead, and PR clutter. When static analyzers fail downstream, human intervention or clumsy webhook-driven loops are required to trigger fixes.

### The Solution: A Decoupled 3-Tier Fabric
This architecture resolves these issues by decoupling the system into:
* **A Macro Control Plane (Temporal Parent Workflow):** Orchestrates end-to-end task lifecycles, global SLAs, and an Outer Loop diagnostic sensor array.
* **An Inner-Loop State Engine (Temporal Child Workflow):** Executes atomic Ralph cycles using `continue_as_new()` and enforces deterministic gates (Tree-sitter AST validation and read-only hold-out evals).
* **A Governed Worker Cell (OpenShift Pod + Nvidia OpenShell):** Runs ephemeral agent CLI processes (Claude Code or OpenCode) under strict kernel-level filesystem jailing and token-injecting egress proxies.
* **A Deterministic Release Pipeline (Tekton / ArgoCD):** Separated downstream at the Pull Request boundary to handle non-repairable artifact compilation, cryptographic signing, and GitOps deployments.

---

## 2. Core Architectural Principles

* **Destroy State to Maintain Precision (Context Hygiene):** Human developer ergonomics optimize for flow state by preserving working context; agent ergonomics optimize for precision by destroying conversation history every turn. The worker starts fresh on each attempt, deriving context strictly from an ephemeral, projected task frame and local disk diffs.
* **Temporal as the Single Source of Truth:** The filesystem inside the execution worker is strictly an ephemeral scratchpad. Progress tracking files (`PROGRESS.md`, task manifests) are dynamically compiled and projected by Temporal—never mutated directly across workers.
* **Inversion of CI (Sensors vs. Release Assembly):** Static analysis tools (SonarQube, CodeQL), vulnerability scanners (Snyk, Trivy), and Dynamic Application Security Testing (DAST) are moved upstream/inward. They function as active sensory organs emitting structured SARIF/JSON data that directly drives targeted agent remediation loops. Traditional CI is reserved solely for deterministic packaging.
* **Zero-Trust Ephemeral Sandboxing:** AI shell interactions are treated as untrusted. OpenShell enforces strict process isolation, path scoping, and credential masking, preventing raw inference keys from existing in the pod's environment.

---

## 3. High-Level System Topology

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

