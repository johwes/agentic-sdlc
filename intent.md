# Intent: Minimal Nested-Loop Agentic SDLC Reference Implementation ("Hello World")

## 1. Problem Statement & Background
Software engineering organizations are moving from human-in-the-loop code generation to autonomous agentic workflows. However, deploying coding agents without structured verification leads to reward hacking, test erosion, regression loops, and unsustainable code review fatigue. 

Based on the architectural specification in [agentic-sdlc.md](file:///var/home/jwesterl/Downloads/opencode/agentic-sdlc/agentic-sdlc.md), we need a working, minimal reference implementation ("Hello World") of the **Nested-Loop Architecture for Agentic SDLC (SDD × TDD × EDD)**.

This harness will demonstrate how to wrap existing, commodity coding agents (e.g., OpenCode, Claude Code, Antigravity) into a deterministic inner loop (SDD × TDD) and an outer loop (EDD) driven by standard CI/CD pipelines (GitHub Actions).

---

## 2. Core Objectives & Capabilities
1. **Intake & Specification-Driven Development (SDD Inner Loop)**:
   - Accept high-level human intent (`intent.md`).
   - Derive an unambiguous, bounded technical specification (`spec.md`) and initial interface contracts before any implementation code is generated.
2. **Deterministic Test-Driven Development (TDD Inner Loop)**:
   - Generate an isolated, executable test suite (`test_spec.py`) that fails against the empty interface (**RED** state).
   - Wrap an external coding agent CLI (or deterministic mock adapter) to iterate on implementation files until deterministic test execution succeeds with exit code 0 (**GREEN** state).
   - Enforce read-only test boundaries (prevent agent reward hacking or modification of the test suite via hook or path constraints).
3. **Evaluation-Driven Development (EDD Outer Loop in CI/CD)**:
   - Implement the outer loop as a GitHub Actions workflow triggered on pull requests.
   - Run independently isolated verification tests (`FAIL_TO_PASS` and `PASS_TO_PASS`).
   - Execute an LLM evaluation judge assessing diff compliance against `spec.md` (Bugs, Security, Spec Alignment, max 5 nits).
   - Generate and output a canonical `release-evidence.json` artifact conforming to [§5.1 schema](file:///var/home/jwesterl/Downloads/opencode/agentic-sdlc/agentic-sdlc.md#L354).

---

## 3. Explicit Scoping & Constraints
- **Subprocess Wrapper Model**: Do **not** build a custom ReAct agent or LLM prompt engine from scratch. The harness must act as a supervisory wrapper invoking existing coding CLIs (e.g., `claude`, `opencode`, `agy`) or fallback adapters via standard CLI invocation, capturing structured logs (`agent-trace.jsonl`).
- **No Heavy Container Sandboxing**: For this reference implementation, do not require Docker, Podman, e2b, or Modal. The harness will operate within local directories or Git worktrees on the developer's system.
- **CI/CD Outer Loop**: The outer loop governance belongs strictly in standard CI/CD (GitHub Actions), maintaining clear physical separation between the developer's inner loop and enterprise release gates.
- **Minimal Dependencies**: Python 3.10+ standard library and minimal dependencies (`pytest`, `pydantic`, `pyyaml`).

---

## 4. User Journeys & Workflow

### Journey A: Developer Inner Loop (Local CLI)
1. Developer edits `intent.md` with a desired feature or bug fix.
2. Developer runs `asdlc run --intent intent.md --agent opencode`.
3. The harness:
   - Generates `spec.md` conforming to the architectural invariants.
   - Generates deterministic pytest tests (`tests/test_spec.py`).
   - Executes tests $\to$ Confirms failure (**RED**).
   - Launches the specified agent subprocess targeting the source files (with `test_spec.py` protected from writes).
   - Re-evaluates test suite upon agent completion until green or max turns reached.
4. On success, creates git branch and prepares commit with `agent-trace.jsonl` metadata.

### Journey B: Pull Request Outer Loop (GitHub Actions)
1. The branch is pushed and a Pull Request is opened.
2. GitHub Actions workflow triggers:
   - Checks out the branch and executes verification test suite in clean environment.
   - Computes `semantic_delta` summary comparing PR diff against `spec.md`.
   - Runs evaluation judge.
   - Emits `release-evidence.json` as a build artifact and posts the `semantic_delta` summary as a PR review comment.

---

## 5. Non-Goals
- Building custom neural models or complex prompt-routing meshes.
- Full-scale multi-agent swarm orchestration across distributed clusters.
- Real-time cloud production telemetry scraping (simulated static metric fixtures will be used to demonstrate statistical band triggers).

---

## 6. Acceptance Criteria
- [ ] `asdlc init` bootstraps the required directory structure (`.asdlc/`, `intent.md`, `specs/`, `tests/`).
- [ ] `asdlc run` executes the SDD $\to$ TDD cycle to completion without human intervention.
- [ ] Test harness detects and halts tampering if the agent attempts to modify verification tests (Inner Loop).
- [ ] CI outer loop (`.github/workflows/agentic_outer_loop.yml`) isolates tests against target base branch (`main`), preventing PRs from altering verification criteria.
- [ ] `asdlc eval` detects unauthorized modifications to protected directories (`tests/`) in diffs and rejects auto-merge (Outer Loop).
- [ ] GitHub Actions workflow passes syntax validation and successfully produces `release-evidence.json`.
- [ ] Architectural alignment: Directly implements state transitions defined in [agentic-sdlc.md §1.2.2](file:///var/home/jwesterl/Downloads/opencode/agentic-sdlc/agentic-sdlc.md#L91).
