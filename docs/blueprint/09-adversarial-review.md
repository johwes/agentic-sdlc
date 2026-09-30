# 09 — Adversarial review — never self-review

## Principle

If the same context that produced something also reviews it, the review is anchored to the production. The reasoning is still warm. The agent will find its own work convincing not because it is good but because it is familiar. A fresh agent — **no memory of the production** — must do the verification, and a deterministic gate outside both must decide whether the result is an improvement.

## Why this matters

The team watched a revision agent degrade its own score and proudly present the result. The team watched a second agent defend its earlier choices as correct precisely because those choices *looked* correct from the inside. This is the same anchoring bias humans have editing their own writing, except the model has no instinct to sleep on it. No prompt reliably says "now forget what you just thought and grade harshly."

Their pipeline enforces separation mechanically:

- The revision agent writes a revised file to disk.
- **In a brand-new context**, the assessor reads that file and scores it from scratch.
- If the revised score is *worse*, a deterministic guardrail (Factor 06) blocks submission and tags the item `autorevise_reject`. Simple rule: if the first revision degraded quality, a second is unlikely to help.

The same pattern recurs wherever verification matters: comparing options runs in a fresh context; verifying one agent's result launches as a separate background job rather than as the next turn in the same conversation. The cost of an extra context is small. The cost of biased self-review is invisible until it ships.

The pragmatic rule: if you find yourself writing "and then ask the agent to double-check its work," stop. Ask a *different* agent — a fresh one with no history of the work — to evaluate the result.

## Running example

The middleware patch is drafted by coder agent A. Reviewer agent B is launched clean — it never sees A's reasoning trace, only the patch and the tests. B finds that the rate-limit header is missing. Coder A's second attempt fixes the header. B (launched fresh *again*) re-scores. The orchestrator compares B's second score to B's first — not to A's self-assessment — before allowing any promotion.

## Conformance check

1. **Context-separation test:** log the context IDs (or conversation/session handles) for the producer and the verifier on the same item. They must be different. If you find the verifier's prompt contains the producer's chain-of-thought, the launch isn't isolated — see Factor 02.
2. **Degradation test:** seed a case where the revision *demonstrably* makes things worse (e.g. a test that used to pass now fails). The pipeline must block even though the producer reports `COMPLETE`. If human or automated review is the same context that produced the revision, this gate will never fire — the model will rationalize the regression.
3. **"Double-check" grep:** `grep -i "double-check\|self-review\|verify your own"` across your skill files and agent prompts. Each hit is a place where the pipeline trusts an agent to be its own judge.
4. **Ping-pong bounding test:** Simulate a persistent reviewer rejection on subjective criteria. Verify that the pipeline halts at the revision limit (Factor 06), tags the task with an autorevise rejection receipt, and escalates to human-on-the-loop review rather than looping indefinitely.

### Reviewer failure modes and enterprise mitigations

A fresh reviewer introduces distinct failure modes that must be governed structurally:

1. **Hyper-criticism (Review ping-pong):** A reviewer instructed to find flaws will inevitably flag subjective stylistic choices, trapping the primary agent in an endless revision loop.
   - *Mitigation:* Bound review cycles using Factor 06 revision caps (maximum 2 attempts) and require concrete failure scenarios (reproducible test failures or violated requirements) in all review findings.
2. **Reviewer blindness (Amnesia loop):** A clean reviewer lacking context may re-propose approaches the primary agent already attempted and discarded.
   - *Mitigation:* Supply the reviewer with Factor 02's capped diagnostic receipt (`prior_diagnostics` tail and execution logs) without exposing the producer's subjective chain-of-thought.
3. **Correlated blind spots:** Single-model evaluation carries shared pre-training and inductive biases. If the model family has a systemic blind spot, both coder and reviewer will overlook it.
   - *Mitigation:* Enforce a **heterogeneous quorum** (cross-evaluation across distinct foundation model families or formal linters) when evaluating critical paths.
4. **Uniform-cost overkill:** Running exhaustive multi-agent quorums on trivial changes doubles compute latency without safety gains.
   - *Mitigation:* Scale review depth by blast-radius risk. Mechanically tested, low-risk changes bypass full LLM review; structural, cryptographic, or security-sensitive changes mandate adversarial quorum.
5. **Multi-agent oscillation (system dynamics):** individually well-governed reviewers interacting through delayed signals can amplify noise into oscillation — with no single faulty decision for any gate to catch.
   - *Mitigation:* govern the loop, not just the decision — revision caps, freshness-scoped re-review, and severity decay (a finding surviving N rounds downgrades to advise + human, never round N+1).

## In this repo

Adversarial review is explicitly named as a post-PoC slot: a different-model review pass with quorum rules, held-out evals behind the forbidden-paths tripwire, and re-scoring on revision. The harness already separates "what the agent said" from "what the tests said" (`agent_summary` never overrides ground truth).

## Sources

- Forrester/Greene — [The author can't review itself](https://dev.to/jessica_jason/engineering-for-non-deterministic-coworkers-p0j#the-author-cant-review-itself) (anchoring, fresh-context assessor, `autorevise_reject`, "ask a different agent")
- Red Hat — [Engineering reliable agents: adversarial review](https://www.redhat.com/en/blog/building-future-core-concepts-red-hats-agentic-software-development-life-cycle) ("nothing should review its own work")
- arXiv A-SDLC — [Agentic AI in the Software Development Lifecycle](https://arxiv.org/abs/2604.26275) (Bhati, 2026 — six-layer governance, L5 review bottleneck, and the auditable separation of proposal from enforcement)
- Huang et al. — [Large Language Models Cannot Self-Correct Reasoning Yet](https://arxiv.org/abs/2310.01798) (Google DeepMind + UIUC, ICLR 2024 — intrinsic self-correction without external feedback fails and can degrade performance)
- Valmeekam et al. — [Can LLMs Really Improve by Self-Critiquing Their Own Plans?](https://arxiv.org/abs/2310.08118) (Arizona State — self-critique diminishes plan quality versus external sound verifiers)
- Anthropic — [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) (isolated subagents with separate context windows report to an orchestrator, rather than reviewing each other)
- Cockcroft et al. — [When Agents Decide](https://itrevolution.com/product/when-agents-decide/) (multi-agent system dynamics: delayed signals amplify noise into oscillation — govern the loop, not just the decision)

## Longevity: Permanent

No future model grades its own homework fairly — reasoning depth increases the confidence of the rationalization along with everything else. Review separation is structural (different context, deterministic comparison of scores), so it survives reviewer upgrades: swap the reviewer model freely, keep the fresh-context launch and the external verdict arithmetic.
