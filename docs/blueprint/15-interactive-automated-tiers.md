# 15 — Interactive sessions delegate to automated flows

## Principle

Research, planning, and live debugging stay **interactive** — a human present, context accumulated, exploration cheap. Bounded execution goes **automated** — fresh contexts, declared effects, no human in the step. The handoff between tiers is an explicit protocol: the interactive session files bounded work (ticket, spec, failing run), the automated flow executes it without re-asking, and anything the flow can't bound escalates back to interactive.

## Why this matters

Each tier covers the other's failure mode. Interactive sessions are efficient precisely where autonomy is unsafe: ambiguous goals, live debugging against warm state, judgment calls with no rubric. Automated flows are safe precisely where interactivity doesn't scale: retries, gates, promotion, audit. Collapsing them — autonomous agents asked to do open-ended research, or humans babysitting bounded retries — gets the worst of both: drift without a watcher, bottlenecks without judgment.

The handoff is the design surface: what state transfers (the ticket, the spec, the failing trace — files, per Factor 01), what gets re-derived (never trust transferred conclusions; the flow re-verifies), and who owns the session at each moment. An automated flow never initiates an interactive session on its own authority; an interactive session never executes side effects except by delegating to a bounded flow.

## Running example

The rate-limit investigation starts interactive: the engineer and the agent poke at production traffic together and conclude gateway-level limiting is right. That conclusion is filed as a bounded ticket (scope, acceptance, proof command). The automated flow picks it up, implements, gates, and opens the draft PR. Mid-run the agent hits an ambiguous tradeoff (gateway vs. service); instead of guessing, it escalates to a steering comment — the engineer's reply arrives as a new bounded input, not as a hijacked session.

## Conformance check

1. **Handoff test:** start an interactive investigation, then hand its output to the automated flow as the *only* input. The flow must complete without asking a question the investigation already answered — and must re-verify every transferred conclusion rather than trusting it. If the flow re-opens exploration, the handoff wasn't bounded.
2. **Tier-discipline test:** audit one week of runs. No automated flow may have initiated an interactive session; no interactive session may have executed a side effect directly (push, merge, close) except through a bounded flow. Each violation is a tier breach, regardless of outcome.
3. **Escalation-roundtrip test:** force an ambiguity mid-run. The flow must pause into a steering prompt, accept a bounded human answer, and resume with history intact — not restart, not guess, not wait silently forever.

## In this repo

Headless-only today: every attempt is non-interactive by construction, and there is no interactive tier to hand off from — the human authors the frame by hand (see `specs/02-control-plane.md` override) and approves the merge. The steering primitives in Factor 11 are specified; the interactive side that would invoke them is future work.

## Sources

- Walters — [Agentic AI and software forges](https://blog.verbum.org/2026/08/21/agentic-ai-and-software-forges/) (hybrid prediction: interactive flows delegating to per-repo automated flows; tmate-style dynamic interactivity)
- gh-aw — [`steer:` run-scoped steering issues](https://github.github.com/gh-aw/reference/safe-outputs/) (keyword comments read mid-run — the closest shipped handoff protocol, though gh-aw's own docs still label it experimental)
- egg — [HITL `provide_input` pause-and-resume](https://github.com/jwbron/egg) (state-preserving human answer as bounded input)
- Microsoft — [VS Code Custom Agents — Handoffs](https://code.visualstudio.com/docs/agent-customization/custom-agents) (a shipping product feature implementing exactly this planning→implementation handoff, human-approval-by-default)

## Longevity: Constraint-stable, mechanism-evolving

The constraint — *humans explore, machines execute, handoff is explicit* — survives autonomy growth; only the boundary line moves (more tasks graduate from interactive to automated as capability rises). Re-derive the tier split each capability step; never let either tier borrow the other's authority.
