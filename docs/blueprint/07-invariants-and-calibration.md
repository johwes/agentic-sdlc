# 07 — Invariants + calibration (close the easy out)

## Principle

At the top of the instructions the agent reads first, list what **must remain true** — not as suggestions, as invariants. Then **anchor** each invariant with concrete good/bad examples at different scores so the agent has something to measure against besides its own optimism.

## Why this matters

An agent is under implicit pressure to *finish*. There is logic in the runtime that pushes toward completing in a reasonable time. Left unconstrained, it finds the fastest path to "done":

- The easiest answer to a failing test is to turn the test off.
- The easiest answer to a design constraint is to remove the constraint.
- The easiest answer to a slow check is to delete the check.

The pattern has a name — **the easy out** — and the fix has been known since before LLMs: write down what must stay true, and make it expensive to violate.

But invariants stated in prose still drift. Running the same 50-item batch twice produced a handful of flipped scores — not because anything changed, but because the model re-rolled the dice on a subjective criterion. The team fixed it by adding calibration anchors per criterion:

- **Score 0:** "Model Deployment should allow to configure the Route." Justification: "Look at the title." (generic, no evidence)
- **Score 2:** "Acme Corp blocked on data residency, Q3 rollout paused across 4 regions." (named customer, quantified impact)

A related case used a third state to stop forcing a binary. Feasibility originally returned `feasible` / `infeasible`; genuinely incomprehensible inputs caused coin-flips. A narrow `indeterminate` state absorbed that uncertainty — poorly written but understandable documents still got a real verdict.

Whether the invariant is "tests pass" or "score 2 means a named customer," the move is identical: **write down what must remain true, anchor it against concrete points, then let the agent optimize within them.**

## Running example

The rate-limit task's invariant list (pinned at the top of the skill file) reads:

- `Tests are correct until proven otherwise. A failing test is a failed attempt.`
- `Never modify tests to pass — change the code until the unmodified suite exits 0.`
- And under the scoring rubric for business justification, two anchors: a 0 example ("we should rate-limit search") and a 2 example ("Acme's search endpoint returns 40% errors under unauthenticated load, measured over the last 7 days").

## Conformance check

1. **Easy-out test:** deliberately introduce a task where the tests *correctly* fail. The agent must report `FAILED`, never by editing, mocking, or commenting out the failing assertion. If you can make it "fix" the test file, the invariant isn't load-bearing — it's prose. (The harness should structurally prevent it; see Factor 08.)
2. **Calibration test:** run the same scoring or triage step twice on the same 20 items without changing anything between runs. Score variance beyond 1–2 items suggests prose-only criteria. Add anchored examples until re-runs converge.

## In this repo

Each commit is judged against the tactile suite's *existing* assertions — tests are never weakened to pass — and prompt contracts carry explicit `UNTRUSTED DATA` + `FORBIDDEN vs. CORRECT` calibration pairs (baked into the cell image, see `specs/04-worker-cell.md`).

## Sources

- Forrester/Greene — [Define invariants. Or the agent will "optimize."](https://dev.to/jessica_jason/engineering-for-non-deterministic-coworkers-p0j#define-invariants-or-the-agent-will-optimize) (easy out, calibration examples, indeterminate third state)
- Bynum — [RFE quality rubric (five criteria) and STRAT scoring (four dimensions)](https://cabynum.github.io/posts/software-factory-floor/#rfe-creator--assess-rfe) (same anchoring habit at the planning stage)
- Fowler — [To vibe or not to vibe](https://martinfowler.com/articles/exploring-gen-ai/to-vibe-or-not-vibe.html) (constant risk calibration by the engineer, same "probability × detectability" calculus)
