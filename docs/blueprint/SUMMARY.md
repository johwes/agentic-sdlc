# Blueprint in 30 seconds

Fifteen rules for running AI coding agents in production. Each is one imperative — the full page behind the link gives the principle, the war story, the conformance check, and the sources.

**A — State & determinism.** How the system stays predictable when the worker isn't.

- [I. Store state on disk, never in context.](01-state-on-disk.md) Compaction wipes what isn't written down — and rewrites what it half-remembers.
- [II. Launch every attempt with a fresh context.](02-fresh-contexts.md) Same skill file on disk, zero inherited conversation.
- [III. Let the agent propose; let code decide.](03-deterministic-shell.md) Tests, retries, and promotion gates belong to deterministic code.
- [IV. Give buttons, not a bag of parts.](04-buttons-not-bag-of-parts.md) The model decides *what*; atomic helper scripts decide *how*.

**B — Constraining the worker.** How to stop improvisation from becoming damage.

- [V. Never put internals in agent context.](05-dont-leak-internals.md) Anything visible becomes a tool it will use.
- [VI. Put guardrails outside the agent.](06-guardrails-outside-agent.md) Caps, regression blocks, and budgets the model can't see past.
- [VII. State invariants; anchor them with examples.](07-invariants-and-calibration.md) Close the easy out before optimization pressure finds it.
- [VIII. Sandbox with least privilege and zero credentials.](08-least-privilege-sandbox.md) Restrict what it *can* do; bound what that *reaches*.

**C — Trust & flow.** How work moves, and how you know it's good.

- [IX. Never let the author review itself.](09-adversarial-review.md) Verification runs in a fresh context; code compares the scores.
- [X. Gate every change on evals; save everything.](10-evaluations-and-save-everything.md) Golden trajectories today are the bridge to the next model.
- [XI. Keep humans on the loop, not in every step.](11-human-on-the-loop.md) Steer at critical gates; dashboard the rest.
- [XII. Route work through a switchboard, not a pipeline.](12-switchboard-coordination.md) Labels and issue state connect independent workstations.

**D — Enterprise hardening.** How this survives audit, scale, and the next model.

- [XIII. Version everything, including words.](13-everything-versioned.md) Prompts, skills, policies, and evals are code.
- [XIV. Require a mandate; keep the provenance.](14-mandate-and-provenance.md) Authorization before action; every artifact carries its lineage.

**E — Execution modes.** Which tier runs what.

- [XV. Let interactive sessions delegate to automated flows.](15-interactive-automated-tiers.md) Humans explore, machines execute, handoff is explicit.

**Known gaps, not yet rules.** [16. What's missing](16-whats-missing-factor.md) — adoption path, economics/ROI, org & people, legal/IP/compliance, cross-repo/cross-team coordination, incident response. Unscored; no conformance check exists yet for any of them.
