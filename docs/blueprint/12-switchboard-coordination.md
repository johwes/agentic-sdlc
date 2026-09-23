# 12 — Switchboard coordination (the factory floor)

## Principle

There is no central conveyor belt. There are **specialized workstations** — each watching for its kind of work — wired into a **shared switchboard** (issue tracker + labels) that routes work without a central router knowing every station exists.

## Why this matters

The early metaphor for an agentic SDLC was a pipeline: left-to-right, RFE → Feature → Epic → Code → Test → Docs → Build. The real factory floor is a **job shop**: the pipeline diagram is the *recommended routing*, but the shop is more flexible. The test-plan generator can pull directly from a feature's acceptance criteria without waiting for code. The bug fixer handles issues from any source, independent of where they sit in the usual sequence. Modular adoption is the payoff — you don't need the whole pipeline to get value from one station.

The switchboard pattern is what makes this possible without a central orchestrator knowing every component:

- Issues are the work items. Labels signal state transitions. Queries are how each agent finds its work.
- When an agent finishes, it updates the issue — and the next station's query matches.
- None of the stations know about each other directly. They know about the switchboard.

The switchboard also surfaces **institutional memory** — architecture context, component mapping, feasibility checks — as shared infrastructure the stations query, not as context each agent has to be spoon-fed. Specialized registries (architecture docs, eval harness, skills catalog) serve the whole floor rather than one stage.

## Running example

The rate-limit ticket lands as an issue labeled `type: feature`. The triage workstation sees it (label query), scores it, and advances the label to `ready-to-code`. The code workstation's query — "any `ready-to-code` not yet assigned?" — matches, and it picks the ticket up. Review, test generation, and docs each have their own label triggers. If tomorrow the team adds a security-review workstation, it wires in by defining *its* label query — no pipeline rewrite, no central routing table change.

## Conformance check

1. **Switchboard test:** list every label and status that drives a transition in your SDLC. If a transition requires opening the orchestrator's code to understand, it's not on the switchboard yet — promote it to a visible label whose query you can run from the tracker alone.
2. **Job-shop test:** pick a station (e.g. docs generation) and trigger it directly from a feature's acceptance criteria, bypassing the code station. If the only way to produce docs is to run the full pipeline left-to-right, every station is coupled to one linear flow — the factory is an assembly line, not a job shop.
3. **Adoption test:** can one team adopt a single station (say, the autofix agent) without enrolling in the entire factory? If not, the stations share more coupling than their label contract suggests.

## In this repo

The ledger states (`inbox → active → review → promoted | escalated`) and per-task labels are the PoC switchboard; decomposition is 1 file = 1 task, with human override for splitting (see `specs/02-control-plane.md`). The switchboard widens as workstations are added.

## Sources

- Bynum — [What's on our Factory Floor](https://cabynum.github.io/posts/software-factory-floor/) (job shop vs. assembly line, JQL-as-wiring, modular adoption — the defining passage for this factor)
- Red Hat — [The end-to-end workflow: Plan / Build / Verify / Ship](https://www.redhat.com/en/blog/building-future-core-concepts-red-hats-agentic-software-development-life-cycle) (four-phase backdrop this factor makes non-linear)
- HumanLayer 12-Factor — [Factor 5: Unify execution state and business state](https://github.com/humanlayer/12-factor-agents) (unified state as the precondition for switchboard routing)

## Longevity: Constraint-stable, mechanism-evolving

The constraint — *stations coordinate through visible shared state, no private channels* — outlives any tracker. Jira + labels today, another substrate tomorrow; the job-shop-over-assembly-line property is about coupling, not tooling. When migrating substrates, port the label contract first (every transition must stay expressible as a query) and the stations follow.
