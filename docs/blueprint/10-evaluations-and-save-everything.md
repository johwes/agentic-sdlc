# 10 — Evaluations gate every change + save everything

## Principle

Before any code ships or any agent skill is updated, it passes a **held-out evaluation** grounded in real-world data. And everything that makes that evaluation possible — every intermediate artifact, thinking block, tool call, and token count — is **saved**, even when you don't yet know you'll need it.

## Why this matters

### The gate

The pipeline's trust comes from a harness that catches regressions early: pinned known-good behavior against which every change (agent update, prompt tweak, model swap) is measured. Without it, a new model that is "better in aggregate" ships quietly and degrades your workload in specifics you won't notice for weeks.

Two war stories set the threshold for what "gate every change" must mean:

- A model upgrade shifted **38% extra token cost** for marginal accuracy gain — invisible without a saved dataset that included cost tracking.
- Thinking blocks stopped showing up in the event stream by default after an upgrade. All debug data vanished until the team found the re-enable flag. The pipeline had been blind and didn't know it.

### The saving

The team backed into saving everything because they needed artifacts for dry runs — then discovered it was the best decision they made:

- **Thinking blocks** — where the agent's reasoning lives. When something weird happens, the explanation is almost always visible there (and some runtimes now default to *not* emitting them — explicitly enable them).
- **All intermediate artifacts** — the draft the revise agent wrote *before* submission, superseded revisions, JSON scorer outputs. Never keep only the final.
- **Tool calls and their inputs/outputs** — every external action with full parameters.
- **OpenTelemetry traces with token counts** — cost per item, cross-span correlation, and the feed into analysis (MLflow or equivalent).

The bigger payoff arrives at model-upgrade time. The principles that survived are:

- Pin production workloads to known models.
- Run the full eval set before anything else. A new release is guilty until it proves otherwise on *your* data.
- Measure cost per item, not just accuracy.
- Inspect output *shapes*, not just values.
- Use the model itself to scan for behavioral differences: "here are 50 runs on the old model and 50 on the new — what's different" is a question the agent answers faster than any human can.

The eval set is the bridge between models. It only exists because you saved everything.

### Behavioral regression testing

The conceptual unit is a **golden trajectory** — a validated trace capturing not just the final output but the complete reasoning chain, tool invocations, and decision points. Frameworks like LangSmith make this instrumented; bare logs do not. A golden trajectory lets you answer "did the agent change *how* it reaches a correct answer, even when the answer still looks correct?"

Two qualifiers keep the practice honest. First, **trajectory matching punishes improvement**: a model upgrade that finds a *shorter valid path* registers as a regression in a rigid trajectory diff. Gate on outcomes + invariants, and review trajectory diffs as advisories — never auto-block on "different steps, same result." Second, **traces are data with a cost model**: terabytes of thinking blocks across CI runs need indexing budgets, retention windows, and privacy scrubbing (customer data and secrets land in traces exactly as easily as in code). Save everything, then govern the archive like production data — because it is.

## Running example

The team ships a rate-limit middleware. Their eval harness has 20 golden trajectories: good patches, bad patches (missing header, wrong layer), and edge cases (authenticated vs. anonymous callers). Before the PR merges, the harness runs them all — including the thinking-block comparison. After a model upgrade, one golden trajectory that used to emit `scope: api/search` now emits `scope: api/*` — still green on the final test, but visibly broader. The team catches it before it ships overly broad rate-limiting to production.

## Conformance check

1. **Missing-evaluation test:** pick your most recent agent skill change and ask "which eval set gated it on merge?" If the answer is "we ran the product's own tests and they passed," you have no agent evaluation — product tests measure that the product works, not that the *agent* still behaves. Add a skill-level eval set (≥ 10 trajectories, at least half expected-to-fail) that must go green before the skill change lands.
2. **Saved-artifacts test:** replay yesterday's run from saved artifacts alone — no re-running the agents. Can you reconstruct every tool call, every intermediate draft, and every thinking block? If thinking blocks are missing, enable them in your runtime and re-run. If only final outputs were saved, widen capture to include superseded drafts.
3. **Cost-per-item test:** plot `input_tokens + output_tokens` per ticket over the last 30 runs. If you can't, you don't have the trace data Factor 10 requires. A 38% cost drift should be a visible line, not a surprise invoice.

## In this repo

Evaluation harness and thinking-block capture are explicitly deferred: no held-out suite is required to run, but the `forbidden_paths` tripwire on eval locations is enforced today so agents habituate to the boundary (see `specs/05-sensors.md`, `specs/03-inner-loop.md` reserved-but-inactive gates). The PoC sensor review is a logged no-op — the slot is there; the evals are not. Token metrics are best-effort (`task_receipt.json: token_metrics`).

## Sources

- Forrester/Greene — [Save everything. You don't know what you'll need.](https://dev.to/jessica_jason/engineering-for-non-deterministic-coworkers-p0j#save-everything-you-dont-know-what-youll-need) (38% token cost, thinking blocks, golden eval set, pin production models)
- Red Hat — [Evaluations gate every change](https://www.redhat.com/en/blog/building-future-core-concepts-red-hats-agentic-software-development-life-cycle) (third reliability principle — eval harness grounded in real datasets)
- Bynum — [Agent Evals + Architecture context as shared infra](https://cabynum.github.io/posts/software-factory-floor/#the-shared-infrastructure) (MLflow integration, pre-merge quality gates)
- InfoQ — [Golden trajectories + behavioral regression testing](https://www.infoq.com/articles/prompts-to-production-playbook-for-agentic-development/) + [SWE-bench as a forcing function with known gaps](https://www.infoq.com/articles/prompts-to-production-playbook-for-agentic-development/) (LangSmith traces, Python-dominated bug-fix bias, need for delegation-focused evals)
- arXiv A-SDLC — [Five open problems: evaluation & governance as the bottleneck](https://arxiv.org/abs/2604.26275)

## Longevity: Constraint-stable, mechanism-evolving — with one caution

The constraint — *no change ships without passing a held-out eval grounded in real data* — is permanent; silent model drift is the failure that never retires. But the mechanism needs active gardening: span formats churn, thinking-block availability changes per runtime, trajectory diffs punish improvement (see above). And the one genuine aging risk in this blueprint lives here: **trajectory-matching is the only mechanism that can punish the model for getting better**. Treat trajectory diffs as advisories reviewed by a human, outcomes + invariants as the gates.
