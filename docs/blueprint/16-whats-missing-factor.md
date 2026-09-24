# 16 — What's missing (known gaps, not scored factors)

## Why this page exists

Factors 01–15 are scored red / yellow / green because each is a checkable practice inside the pipeline itself — state, guardrails, review, coordination. The six gaps below sit *outside* that boundary. They're organizational, financial, and legal questions that determine whether an org should build any of this and whether it survives contact with the rest of the business — not whether the pipeline is built correctly. Grouping them here, unscored, keeps 01–15 disciplined (see [`README.md`](README.md) — playbook, not protocol) instead of quietly growing into a 21-factor list that mixes pipeline mechanics with org strategy.

None of these has a conformance check yet. A gap graduates to a numbered, scored factor only when someone can write one and point at real running practice — until then it stays here as an open question, not a claim.

## 1. Adoption path

**What's missing:** guidance for going from "we have Copilot" to "we run this pipeline," sequenced for a team with legacy code, no Temporal cluster, and no existing eval harness. The README's "start at 1" is an ordering principle for the factors, not a rollout plan for an organization.

**Why it matters:** without a crawl/walk/run sequence, teams either try to build all 15 factors at once (stalls) or cherry-pick factors 3 and 9 while skipping 1 and 2 (the ones that make the others possible) and wonder why it doesn't hold together.

**Open question:** what's the minimum viable subset that's safe to run in production, and what's the deliberate order to add the rest?

## 2. Economics / ROI

**What's missing:** a cost model. Factor 10 tracks *eval* cost (tokens, cache hit rate) but nothing here tells an org how to weigh total cost — compute, human review time, incident cleanup, the eval harness itself — against the productivity claim, or what "this is working" looks like at the P&L level rather than the pipeline level.

**Why it matters:** a factor set that's all risk-and-control and no economics reads as a compliance checklist, not a business case. Whoever has to fund the Temporal cluster and the eval harness will ask for this before they ask about calibration anchors.

**Open question:** what are the leading indicators (cycle time, defect rate, cost per shipped feature) an org should track from week one, before Org Pulse-style dashboards exist?

## 3. Org & people

**What's missing:** what roles this needs (who owns the switchboard? who's on call for escalations?), how review load shifts onto senior engineers, and how to handle the trust-building problem with engineers whose job just changed underneath them.

**Why it matters:** Factor 11 assumes a dashboard exists and humans are willing to use it as "on the loop." Getting there is a change-management problem this blueprint doesn't touch, and it's usually the thing that actually kills an adoption effort — not a missing guardrail.

**Open question:** does this require a new role (an "agent ops" function, analogous to SRE), or does it fold into existing engineering roles, and at what team size does that stop being true?

## 4. Legal, IP & compliance

**What's missing:** license scanning of agent-generated code, IP ownership questions, and data-residency implications of sending proprietary code to a third-party model. Factor 14 covers *audit* trail (who authorized what, what was observed) but not whether the output is legally shippable.

**Why it matters:** this is usually the first question legal asks, and "we have provenance records" doesn't answer it — provenance tells you what happened, not whether it was permitted.

**Open question:** does license/IP screening belong as a gate inside Factor 10's eval harness, or as a separate compliance layer that sits outside the pipeline entirely?

## 5. Cross-repo / cross-team coordination

**What's missing:** Factor 12's switchboard is scoped to one factory floor. Nothing addresses coordination when a ticket spans five services owned by five teams with five different switchboards — which is where most real organizations actually live, not in a single-repo demo.

**Why it matters:** without this, the switchboard pattern looks great in the running example (one team, one repo) and becomes unclear the moment a rate-limit change touches a shared gateway service owned by a different team.

**Open question:** does cross-team coordination need a switchboard-of-switchboards, or does it stay a human problem (cross-team tickets, same as today) with the agent pipeline only ever operating inside one team's floor?

## 6. Incident response

**What's missing:** what happens when agent-shipped code causes a production incident. Factor 11 covers mid-run escalation (the agent asks a human *before* shipping); nothing covers the postmortem process *after* something ships and breaks.

**Why it matters:** the audit trail from Factor 14 gives you the forensics, but not the process — is this postmortem different from a human-caused incident? Does "the agent decided X" change blame culture, on-call rotation, or the fix-forward vs. rollback calculus?

**Open question:** does an agent-caused incident get a distinct postmortem template (e.g., trajectory review alongside the usual timeline), or does it fold into existing incident process unchanged?

## Longevity: not applicable

These aren't factors yet, so they don't carry a Longevity verdict. If and when one of them earns a real conformance check, it moves into the numbered, scored set and picks up a verdict there.
