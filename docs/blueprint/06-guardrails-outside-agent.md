# 06 — Guardrails live outside the agent

## Principle

Judgments the agent can't make about itself must live **outside** the agent, in deterministic code.

## Why this matters

An agent doesn't know when it's making things worse. It will revise a document, degrade the score, and proudly present the result. It will loop forever if you let it. Some of this is optimism; some of it is pattern-copying — the "revise existing" agent inherited a "create new" template and deleted every paragraph that didn't fit, because it had no concept of preservation.

Four guardrails kept showing up:

- **Regression detection:** after an auto-revision, re-score from scratch. If the score went *down*, block submission entirely. The logic is simple: if the first revision degraded quality, a second is unlikely to help.
- **Revision caps:** at most two cycles. If it hasn't passed by then, report the final state and move on.
- **Preconditions:** the reviewer only recommends splitting an oversized spec when size is the *sole* failing criterion. If anything else scored zero, splitting won't fix it.
- **Branching caps:** the splitting loop is bounded (e.g. at most six children at any depth); beyond that, halt for a human.

Each encodes the same insight: **the agent will always think its revision is an improvement**. External checks catch what it can't see — by comparing scores, counting cycles, and checking preconditions the agent never evaluates about itself.

## Running example

The agent's first rate-limit patch fails the architecture review (middleware in the wrong layer). The harness re-scores the revision: the score dropped, so it blocks promotion outright — no second attempt, no auto-merge. A second ticket that genuinely is just too large gets split into two child tickets; a ticket that is both too large *and* underspecified does not — the "too large" flag alone doesn't trigger the split.

## Conformance check

1. **Regression test:** make the agent produce a revision that *lowers* your quality metric (worse test coverage, slower benchmark, lower rubric score). The pipeline must block, not promote, even though the agent reports success. If it promotes, your guardrail is inside the agent.
2. **Cap test:** set `max_attempts` low, then give the agent a task it cannot solve in one attempt. It should hit the cap, publish the final state, and escalate — not loop. If you can get it to loop forever by tweaking the prompt, the cap is a suggestion, not a guardrail.
3. **Transient-vs-regression test:** fail the suite with an infrastructure error (rate-limited registry, DNS blip), not a code error. The harness should classify it as transient — back off and retry without consuming the *revision* budget or, worse, letting the agent "fix" correct code to satisfy a red build. If infra failures and test failures share one counter, a flaky platform burns the budget real bugs need.
4. **Recovery test:** kill the harness mid-promotion (after the branch push, before the PR opens). Restart from persisted state: the run must resume or roll the partial promotion back — never push twice, never leave a branch with no PR. Partial world-state with no compensating path is a guardrail gap, not bad luck.

## In this repo

Attempt budget (`max_attempts` 5, linear backoff), strike-2 reset + sprawl guard, and `HALT:EXHAUSTED` / `HALT:BLOCKED` terminal states are deterministic gates the wrapper enforces regardless of agent prose (`specs/03-inner-loop.md`).

## Sources

- Forrester/Greene — [The agent will always think it's "helping"](https://dev.to/jessica_jason/engineering-for-non-deterministic-coworkers-p0j#the-agent-will-always-think-its-helping) (deletion of customer evidence, revision 0→0, two-cycle cap, six-child branching cap)
- Bynum — [Epic Creator's adversarial review and dependency ordering](https://cabynum.github.io/posts/software-factory-floor/#epic-creator) (a separate reviewer checks that epics cover the strategy)

## Longevity: Permanent

Optimism, sycophancy, and confirmation bias are training properties, not version properties — future models will justify their regressions *better*, which makes external verification more necessary, not less. Budgets, caps, and terminal states are arithmetic; arithmetic doesn't drift.
