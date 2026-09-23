# Blueprint — The Agentic SDLC

A vendor-neutral set of **14 factors** for running AI coding agents in production. Built on learnings from teams already doing this at scale, not on framework marketing.

> **How to use it:** score each factor red / yellow / green against your pipeline. Red means the agent can hurt you in a way your current controls won't catch. The factors are ordered so earlier ones make later ones possible — start at 1.

## The four parts

| Part | Question it answers | Factors |
|------|---------------------|---------|
| **A — State & determinism** | How does the system stay predictable when the worker isn't? | [01](01-state-on-disk.md) [02](02-fresh-contexts.md) [03](03-deterministic-shell.md) [04](04-buttons-not-bag-of-parts.md) |
| **B — Constraining the worker** | How do we stop the agent improvising its way into trouble? | [05](05-dont-leak-internals.md) [06](06-guardrails-outside-agent.md) [07](07-invariants-and-calibration.md) [08](08-least-privilege-sandbox.md) |
| **C — Trust & flow** | How do we know the work is good, and how does it move? | [09](09-adversarial-review.md) [10](10-evaluations-and-save-everything.md) [11](11-human-on-the-loop.md) [12](12-switchboard-coordination.md) |
| **D — Enterprise hardening** | How does this survive audit, scale, and the next model? | [13](13-everything-versioned.md) [14](14-mandate-and-provenance.md) |

## Factor list

| # | Factor | One-line |
|---|--------|----------|
| [01](01-state-on-disk.md) | State on disk, or it doesn't exist | Every flag, queue, and instruction lives in a file; compaction can wipe context at any time |
| [02](02-fresh-contexts.md) | Fresh contexts every attempt | Each agent starts with a clean context pointing at the same skill file on disk |
| [03](03-deterministic-shell.md) | Deterministic shell around the probabilistic worker | The agent proposes; deterministic code decides what actually happens |
| [04](04-buttons-not-bag-of-parts.md) | Buttons, not a bag of parts | The LLM decides *what*; helper scripts decide *how* and run atomically |
| [05](05-dont-leak-internals.md) | Don't leak internals (the screwdriver problem) | Anything in the agent's context becomes a tool it will use |
| [06](06-guardrails-outside-agent.md) | Guardrails live outside the agent | Caps, regression blocks, and branching limits the agent can't see past |
| [07](07-invariants-and-calibration.md) | Invariants + calibration (close the easy out) | Write down what must stay true, anchored with concrete good/bad examples |
| [08](08-least-privilege-sandbox.md) | Least-privilege sandbox, zero credentials | Capability restriction limits what the agent *can* do; sandbox limits what that *reaches* |
| [09](09-adversarial-review.md) | Adversarial review — never self-review | The author can't review itself; verification runs in a fresh context |
| [10](10-evaluations-and-save-everything.md) | Evaluations gate every change + save everything | Golden trajectories, held-out evals, thinking blocks — the bridge between models |
| [11](11-human-on-the-loop.md) | Human *on* the loop, not *in* every step | Dashboarded steering at critical gates, scaled by risk, not by habit |
| [12](12-switchboard-coordination.md) | Switchboard coordination (the factory floor) | Labels and issue state route work through a job-shop of independent workstations |
| [13](13-everything-versioned.md) | Everything versioned (directives as code) | Prompts, skill files, policy bundles, and evals are version-controlled assets |
| [14](14-mandate-and-provenance.md) | Mandate + provenance (govern the memory) | A principal-authored mandate gates every session; every artifact carries its lineage |

## Aging (will this survive the next model generation?)

12-factor apps aged well because each factor constrained an *interface*, not an implementation. Same test here — every factor page ends with a `Longevity` verdict:

- **Permanent (01, 02, 03, 06, 07, 08, 09, 13):** constrain a boundary that isn't moving (probabilistic inference can't verify itself; instructions and data share one pipeline; optimization pressure always seeks the easy out). Capability growth *strengthens* most of these.
- **Constraint-stable, mechanism-evolving (04, 05, 10, 11, 12, 14):** the constraint stands while the mechanism rotates (scripts → compiled tools, redaction → mediation, Jira → whatever's next). Re-read these when the tooling shifts; the check stays valid.
- **One watch item:** Factor 10's trajectory-matching is the only mechanism that can punish the model for getting *better* — gate on outcomes + invariants, review trajectory diffs as advisories.

## Spine

The blueprint's spine is **Forrester/Greene — [Engineering for Non-Deterministic Coworkers](https://dev.to/jessica_jason/engineering-for-non-deterministic-coworkers-p0j)** (learnings from Red Hat running this in production). Each factor page links the passage it builds on, plus the corroborating sources:

- [Red Hat — Core Concepts of the Agentic SDLC](https://www.redhat.com/en/blog/building-future-core-concepts-red-hats-agentic-software-development-life-cycle) (Huels) — Org Pulse, on-the-loop, Plan/Build/Verify/Ship
- [Bynum — What's on our Factory Floor](https://cabynum.github.io/posts/software-factory-floor/) — job-shop, switchboard, shared infra
- [InfoQ — From Prompts to Production](https://www.infoq.com/articles/prompts-to-production-playbook-for-agentic-development/) — decision-science capability matrix, versioning, golden trajectories
- [HumanLayer — 12-Factor Agents](https://github.com/humanlayer/12-factor-agents) — own your context/prompts/control flow, human as tool call, stateless reducer
- [Fowler — Exploring Generative AI](https://martinfowler.com/articles/exploring-gen-ai.html) — supply-chain attack surface, harness engineering, context discipline
- [tikalk — The Twelve-Factor Agentic SDLC](https://github.com/tikalk/agentic-sdlc-12-factors) + [arXiv A-SDLC](https://arxiv.org/abs/2604.26275) + [egg](https://github.com/jwbron/egg) / [GATE](https://assets.whitepaper.download/gate/v1.3/) / [CodeDelegator](https://ar5iv.labs.arxiv.org/html/2601.14914) — cross-checks for scope, governance, and isolation

> **Scope:** `agentic-sdlc` (this repo's PoC loop) implements many of these factors already and is cited on factor pages where it does — but the blueprint is vendor-neutral and does not assume this repo.

## Running example

Each factor page uses the same neutral running example so the reader can follow continuity:

> **A small product team ships a customer-facing web service. A ticket arrives: "Rate-limit the public API — unauthenticated callers are hammering the search endpoint." The ticket is vague, the codebase is Java + React, and the team has one production cluster.**

No tic-tac-toe, no model names, no vendor SDKs.

## Scoring template

Copy for each factor when auditing your pipeline:

```text
Factor 03 — Deterministic shell ................ [  ] red  [  ] yellow  [  ] green
Evidence: ___________________________________________________________
Next step: __________________________________________________________
```
