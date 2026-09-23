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

Two known failure modes of the reviewer itself: **hyper-criticism** (a reviewer instructed to find flaws rejects correct work over style and traps the primary agent in revision ping-pong — bound it with the same revision caps as Factor 06 and require concrete failure scenarios in findings) and **reviewer blindness** (a fresh reviewer re-suggests approaches the producer already tried and discarded — the capped diagnostic receipt from Factor 02 is the reviewer's context too). Single-model review additionally carries correlated blind spots; heterogeneous quorum (distinct models cross-evaluating) is the enterprise answer when one reviewer's bias becomes the system's bias. Scale the depth by risk: mechanically-tested low-risk changes can bypass full LLM review; security-sensitive or structural changes mandate it — review everything equally and the cost doubles for no safety gain.

## In this repo

Adversarial review is explicitly named as a post-PoC slot: a different-model review pass with quorum rules, held-out evals behind the forbidden-paths tripwire, and re-scoring on revision. The harness already separates "what the agent said" from "what the tests said" (`agent_summary` never overrides ground truth).

## Sources

- Forrester/Greene — [The author can't review itself](https://dev.to/jessica_jason/engineering-for-non-deterministic-coworkers-p0j#the-author-cant-review-itself) (anchoring, fresh-context assessor, `autorevise_reject`, "ask a different agent")
- Red Hat — [Engineering reliable agents: adversarial review](https://www.redhat.com/en/blog/building-future-core-concepts-red-hats-agentic-software-development-life-cycle) ("nothing should review its own work")
- arXiv A-SDLC — [Six-layer governance, L5 as the bottleneck](https://arxiv.org/abs/2604.26275) + [Auditable separation of proposal from enforcement](https://arxiv.org/abs/2604.26275) (same separation, formalized)

## Longevity: Permanent

No future model grades its own homework fairly — reasoning depth increases the confidence of the rationalization along with everything else. Review separation is structural (different context, deterministic comparison of scores), so it survives reviewer upgrades: swap the reviewer model freely, keep the fresh-context launch and the external verdict arithmetic.
