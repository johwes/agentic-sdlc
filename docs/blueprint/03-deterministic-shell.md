# 03 — Deterministic shell around the probabilistic worker

## Principle

The agent **proposes**. Deterministic code **decides**. Everything mechanical — waiting, routing, verdict arithmetic, health detection, state transitions — belongs to code. The model is consulted only for judgment.

## Why this matters

A non-deterministic worker is useful *because* it explores many possible answers. That same property makes it the wrong place to put branching, counting, or gating logic: the answer you get depends on which run you happened to watch. The fix that emerged independently across teams is a deterministic shell — a state machine — around the worker:

- The **agent** generates a candidate (a patch, a triage verdict, a fix).
- The **harness** validates it against a schema, runs the tests, computes the verdict, and decides what happens next.
- If the harness says "failed," it is failed — no paragraph of model justification can override the exit code.

Three patterns kept reappearing in the research:

- **Owned control flow:** the `while` loop that calls the model, dispatches a tool, and appends the result is code a human can step through — not a framework abstraction. Frameworks hide error handling and retries where you can't see them.
- **Orchestrator-owned event loop:** agents never idle and never wait on a message bus. The orchestrator owns all waiting and spawns a short-lived, one-shot agent only when there is actionable work. Long-horizon autonomy fails when the model holds control flow: it forgets what it was supposed to do next.
- **Detection before judgment:** the monitoring plane is a layer of cheap deterministic detectors. Only a genuinely ambiguous finding spawns an overseer model to adjudicate — and its verdict is advisory, executed by the orchestrator through a bounded vocabulary (`nudge`, `respawn`, `escalate`).

## Running example

The rate-limit middleware is attempted. The agent says "done." The harness ignores the word and runs the test suite. The suite fails → the harness marks the attempt `FAILED`, decides (by a rule, not by asking the model) whether to repair or reset the workspace, and re-queues the next attempt with a *text-only* failure trace. The agent never decides its own retry policy.

## Conformance check

1. **Shell ownership test:** `grep` for your main agent loop. You should find one `while` (or state-machine dispatch) in repository code, with the model call on one line and the tool dispatch + error handling on the next few. If the loop lives inside a framework object you can't step through in a debugger, you don't own your control flow.
2. **Exit-code overrides nothing:** make the agent produce a patch that the tests reject, then have it claim the tests are wrong. The harness must still report `FAILED` and block any merge or promotion path. If any amount of model prose can flip a `FAILED` to `COMPLETE`, the shell has a hole.
3. **Idle-agents test:** after a task completes, list running agent processes/pods. There should be none. If agents idle holding a conversation, the orchestrator doesn't own the lifecycle.
4. **Flaky-rerun test:** fail the suite with an infrastructure blip (rate-limited registry, DNS timeout), not a code defect. The shell must re-execute the suite once to arbitrate flakiness *before* marking the attempt failed — a single nonzero exit from a flaky platform must never consume an agent revision or trigger a rewrite.

## In this repo

Each attempt is a fresh headless process; the wrapper (harness) owns the receipt envelope, gates, and promotion — the LLM never constructs the JSON and nonzero test exit is absolute ground truth (`specs/03-inner-loop.md`, `specs/07-contracts.md`).

## Sources

- Forrester/Greene — [The pattern that kept appearing is a state machine](https://dev.to/jessica_jason/engineering-for-non-deterministic-coworkers-p0j#looking-back) + [If CI depends on it, code must execute it](https://dev.to/jessica_jason/engineering-for-non-deterministic-coworkers-p0j#avoid-generic-mcp-use-helper-scripts)
- egg — [Orchestrator-owned event loop](https://github.com/jwbron/egg) / [Deterministic health detection, on-demand adjudication](https://github.com/jwbron/egg) ("everything mechanical belongs to deterministic code")
- HumanLayer 12-Factor — [Factor 8: Own your control flow](https://github.com/humanlayer/12-factor-agents)
- InfoQ — [Nondeterministic reasoning vs. deterministic state](https://www.infoq.com/articles/prompts-to-production-playbook-for-agentic-development/) (capability-matrix framing: LLM reasoning only where alternative interpretations are possible)
- arXiv A-SDLC — [Governance and Safety as the least mature layer](https://arxiv.org/abs/2604.26275) (L5 governance as the bottleneck)

## Longevity: Permanent

The math of probabilistic inference doesn't version: a sampler cannot impartially verify, count, or bound itself. Capability growth improves plans, not state tracking — extended reasoning makes better proposals inside the shell, never a reason to move branching, caps, or promotion gates into the model. Asymmetric failure modes (one bad auto-merge vs. one wasted retry) keep the shell's conservatism rational at any capability level.
