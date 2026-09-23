# 05 — Don't leak internals (the screwdriver problem)

## Principle

Whatever you put in the agent's context will eventually get used. If the only thing in front of the agent is "call `submit`," the worst it can do is call `submit` again. If the context is polluted with raw errors, stack traces, and API shapes, the agent will pick up something that looks like a screwdriver, open the panel, and start rewiring.

## Why this matters

An external call failed; an error blob landed in context; and instead of retrying the helper script, the agent reasoned about the underlying system and tried to take direct action. It wasn't being malicious. It was being helpful — and it bypassed every guardrail the team had built.

The screwdriver problem is the name for this: **any internals you expose become tools the agent will use**, regardless of whether they were meant for it.

The fix is Postel's Law applied to agents — **constrain the inputs, tolerate the outputs**:

- **Constrain inputs:** helper scripts catch their own errors and report narrow, structured outcomes like `submission failed: retry advised`, not the underlying HTTP response. The agent sees a verdict it can branch on, not a system it can reason about.
- **Tolerate outputs:** when the agent gives *you* something, parse leniently. A score that comes back as `1/2`, bare `1`, or `**WHAT** (0-2): 1` is the same score.

There is a deliberate, bounded exception: sometimes the agent *needs* the failure trace to repair (Factor 03's feedback loop). The rule there is to hand over the **failing assertion only**, capped to one finding, not the execution environment (paths, env vars, full logs). One screwdriver, one cut, returned after use.

## Running example

The rate-limit tests fail with a stack trace that includes an internal dashboard URL. The harness does not forward the raw trace. It forwards: `FAILED: sliding-window test timed out after 120s (suite: rate-limit)`. The agent, seeing only that, retries with a narrower window rather than trying to curl the dashboard. The full trace is still saved — on disk, for the human (see Factor 10) — just not in the agent's context.

## Conformance check

1. **Error-surface test:** fail a helper script deliberately (e.g. a 500 from the issue tracker). Read what the agent actually sees in its next turn. If you can find an HTTP status, a stack frame, or an API shape in the agent's prompt, the helper is leaking. Narrow it to a structured verdict.
2. **Output-tolerance test:** feed your harness three differently formatted but semantically identical agent outputs (score with and without markdown, JSON with trailing commas, prose with extra whitespace). All three should be accepted. If any is rejected for formatting, your parser is too strict and your next guardrail will be "add more prompt instructions" — which, per the research, makes variance worse.

## In this repo

Each retry injects only the failing assertion tail as a single `TactileTestGate` finding, not the execution environment (`specs/03-inner-loop.md` injection bound, `specs/07-contracts.md`). Secrets are provider-injected and secret-scanned pre-push, never echoed into agent context.

## Sources

- Forrester/Greene — [Don't leak internals. Claude will use them.](https://dev.to/jessica_jason/engineering-for-non-deterministic-coworkers-p0j#dont-leak-internals-claude-will-use-them) (screwdriver problem, constrain inputs / tolerate outputs)
- egg — [Untrusted agents work inside a zero-credential sandbox; gateway sidecar enforces the boundary](https://github.com/jwbron/egg) (credentials never reach the agent)
