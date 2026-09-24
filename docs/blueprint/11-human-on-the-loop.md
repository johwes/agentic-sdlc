# 11 — Human *on* the loop, not *in* every step

## Principle

The system runs autonomously; humans **steer at critical gates** rather than approving every minor action. Dashboarding surfaces exactly where intervention is needed — the rest of the time, humans do higher-value work.

## Why this matters

Two structures contrast directly:

- **In the loop:** a human gates every step. Safe, but a bottleneck — it doesn't scale.
- **On the loop:** the system alerts engineers when intervention is required. Humans act as pilots, not gatekeepers.

The shift doesn't diminish the engineer's role — it elevates it. The work that historically consumed the most time (boilerplate, first drafts, manual review) moves to the pipeline. The engineer's scarce attention shifts to:

- Understanding customer problems deeply.
- Shaping solutions against real-world constraints.
- Exercising domain judgment no pipeline can provide on its own.

The mechanism that makes this possible is a **central management layer** — a dashboard that is the source of truth for what the system is doing:

- **Metric tracking:** throughput baselines (planned vs. past delivery, contextualized with activity from the code forge) so you can spot overcommitment early and measure how AI changes team velocity — not just agent activity.
- **Release and team visibility:** where every feature sits, where bottlenecks form, without hunting through five reports.
- **Steering infrastructure:** the signals that tell humans *when* to intervene, surfaced at the exact moment intervention is required — distinguishing this from "in the loop" where humans are required at every iteration.

The trust contract is explicit: the pipeline *proposes* — humans *approve* merges, deployments, and critical decisions. The dashboard is how humans know when a proposal is ready and whether it's worth their time.

## Running example

The rate-limit feature moves through triage → plan → code → review → verify, all autonomously. The team doesn't watch each step. They watch a single dashboard row: green for "ready for human merge review," amber for "blocked — needs a plan decision," red for "escalated after max attempts." When the row turns amber (the agent needs to know whether to rate-limit at the gateway or in the service), a human is paged with the two options and the evidence for each — not with a raw agent transcript.

## Conformance check

1. **Dashboard test:** without asking the pipeline, can a team lead answer "which features are in `Verify` and which are stuck in `Build`"? If the answer requires opening Temporal UI + Jira + GitHub + a spreadsheet, you have four sources of truth, not one.
2. **Intervention-load test:** count human approvals per feature end-to-end. If the number scales linearly with the number of agent steps (every draft, every tool call needs a click), you're *in* the loop. The target is a small constant (spec approval, merge approval, plus escalations) regardless of how many agent attempts ran underneath.
3. **Overcommit test:** can your dashboard compare planned work against *historical* throughput and flag when the plan exceeds what the team (humans + agents) actually delivers? If not, planning is detached from the system's demonstrated capacity.
4. **In-flight steering test:** pause a running task mid-attempt, patch its work order (narrow the scope, add a constraint), and resume. The next attempt must pick up the patch with execution history intact — no restart-from-scratch, no lost receipts. If steering requires killing the run and its history, humans can only approve or abort, never redirect. Break-glass overrides (emergency approvals that bypass a gate) must be logged as distinct from normal approvals, or the audit can't tell courage from routine.
5. **Escalation-briefing test:** take the last escalated item and time a human reading only the handoff. The briefing format is fixed: objective (one line), attempts made (count + last error only, never full logs), the specific blocking decision required, and a diff preview. If the human needs the raw transcript to decide, the handoff failed — five attempts of logs cause cognitive overload, not insight.

Authorizations the pipeline carries should be **leases, not grants**: scoped, time-bounded, and revocable — task-scoped credentials that die with the task, delegation chains that can only narrow (never widen) authority, expiry enforced by the runtime clock rather than by hoping every holder cleans up. Multiple independent implementations (task-based authz with expiry + call-count conditions, signed capability tokens, HMAC-chained attenuating credentials) converge on the same shape: authority that attenuates by default and must be re-earned, so a compromised or stale agent's blast radius is bounded by time as well as scope. The steering interface follows the same precedents: pause-and-resume decisions that preserve state (egg's HITL `provide_input`), frame patching via workflow signals (Temporal's signal mechanism over state carried across continuations), and pre-flight gates where refusal is free only *before* side effects (the saga pattern applied to agent orchestration).

## In this repo

Humans approve the merge that ships the draft PR; the harness never auto-merges. The Temporal UI and ledger projection (`tasks/ledger.md`, `LEDGER_PATH=/tmp` for demos) are the PoC-scale version of the management layer — the production Org Pulse equivalent is explicitly a post-PoC slot.

## Sources

- Red Hat — [The "on the loop" philosophy + Org Pulse](https://www.redhat.com/en/blog/building-future-core-concepts-red-hats-agentic-software-development-life-cycle) (in vs. on the loop, steering infra, metric tracking — the most quoted passage in this blueprint)
- Forrester/Greene — [Define invariants or . . . branching & escalation caps](https://dev.to/jessica_jason/engineering-for-non-deterministic-coworkers-p0j#the-agent-will-always-think-its-helping) (when to escalate *to* the human)
- Fowler — [To vibe or not to vibe](https://martinfowler.com/articles/exploring-gen-ai/to-vibe-or-not-vibe.html) (continuous human risk calibration)
- Carnegie Council — [Seven Myths of Using the Term "Human on the Loop"](https://www.carnegiecouncil.org/media/article/7-myths-of-using-the-term-human-on-the-loop) (traces the term's real pre-LLM lineage in autonomy-policy discourse — and argues, as an honest counterpoint, that the phrase can mask reduced control if the "loop" itself isn't well-designed)

## Longevity: Constraint-stable, mechanism-evolving

The constraint — *bounded human attention at critical gates, scaled by risk* — survives autonomy growth; if anything, more capable agents raise the stakes of each gate. What evolves is the instrumentation: Org Pulse today, whatever observability substrate comes next. Keep the gate *set* (spec approval, merge approval, escalations) stable while the dashboard underneath churns, and re-derive the risk tiers each time agent capability steps up.
