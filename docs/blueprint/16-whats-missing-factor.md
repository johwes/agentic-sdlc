# 16 — What's missing (known gaps, not scored factors)

## Why this page exists

Factors 01–15 are scored red / yellow / green because each is a checkable practice inside the pipeline itself — state, guardrails, review, coordination. The eight gaps below sit *outside* that boundary. Most are organizational, financial, and legal questions that determine whether an org should build any of this and whether it survives contact with the rest of the business — not whether the pipeline is built correctly; one (release/supply-chain provenance) is a technical gap at the pipeline's own boundary. Grouping them here, unscored, keeps 01–15 disciplined (see [`README.md`](README.md) — playbook, not protocol) instead of quietly growing into a 22-factor list that mixes pipeline mechanics with org strategy.

None of these has a conformance check yet. A gap graduates to a numbered, scored factor only when someone can write one and point at real running practice — until then it stays here as an open question, not a claim.

## 1. Adoption path

**What's missing:** guidance for going from "we have Copilot" to "we run this pipeline," sequenced for a team with legacy code, no Temporal cluster, and no existing eval harness. The [`README.md`](README.md)'s "start at 1" is an ordering principle for the factors, not a rollout plan for an organization.

**Why it matters:** without a crawl/walk/run sequence, teams either try to build all 15 factors at once (stalls) or cherry-pick [Factor 03](03-deterministic-shell.md) and [Factor 09](09-adversarial-review.md) while skipping [Factor 01](01-state-on-disk.md) and [Factor 02](02-fresh-contexts.md) (the foundational primitives that make the others possible) and wonder why it doesn't hold together. Harnessability also varies by codebase: typed languages and clean module boundaries give you sensors for free, while legacy debt denies you the controls — the harness is most needed where it is hardest to build.

**Open question:** what's the minimum viable subset that's safe to run in production (e.g. 01, 02, 04 before 03, 07, 08), and what's the deliberate operational sequence to add the rest without stalling on infrastructure setup?

## 2. Economics / ROI

**What's missing:** a cost model. [Factor 10](10-evaluations-and-save-everything.md) tracks *eval* cost (tokens, cache hit rate) but nothing here tells an org how to weigh total cost — compute, human review time, incident cleanup, the eval harness itself — against the productivity claim, or what "this is working" looks like at the P&L level rather than the pipeline level.

**Why it matters:** a factor set that's all risk-and-control and no economics reads as a compliance checklist, not a business case. Whoever has to fund the Temporal cluster and the eval harness will ask for this before they ask about calibration anchors.

**Open question:** what are the leading indicators (cycle time, defect rate, cost per shipped feature) an org should track from week one, before Org Pulse-style dashboards exist?

**Candidate mechanism (still unscored):** value-per-token routing (Cockcroft et al., When Agents Decide; Eder, "Tokenomics for Code") — classify each request and send it to the cheapest model still meeting the SLO, with hierarchical fallback to stronger models; extend FinOps to token spend (cost per shipped feature, cache-hit economics). Mechanism, not a check: the gap stays open until someone proposes how to verify it.

## 3. Org & people

**What's missing:** what roles this needs (who owns the switchboard? who's on call for escalations?), how review load shifts onto senior engineers, and how to handle the trust-building problem with engineers whose job just changed underneath them.

**Why it matters:** [Factor 11](11-human-on-the-loop.md) assumes a dashboard exists and humans are willing to use it as "on the loop." Getting there is a change-management problem this blueprint doesn't touch, and it's usually the thing that actually kills an adoption effort — not a missing guardrail.

**Open question:** does this require a new role (an "agent ops" function, analogous to SRE), or does it fold into existing engineering roles, and at what team size does that stop being true?

## 4. Legal, IP & compliance

**What's missing:** license scanning of agent-generated code, IP ownership questions, and data-residency implications of sending proprietary code to a third-party model. [Factor 14](14-mandate-and-provenance.md) covers *audit* trail (who authorized what, what was observed) but not whether the output is legally shippable.

**Why it matters:** this is usually the first question legal asks, and "we have provenance records" doesn't answer it — provenance tells you what happened, not whether it was permitted.

**Open question:** does license/IP screening belong as a deterministic gate inside [Factor 03](03-deterministic-shell.md) / [Factor 10](10-evaluations-and-save-everything.md)'s eval harness, or as a separate compliance layer that sits outside the pipeline entirely?

**Candidate mechanism (still unscored):** regulators already describe the substrate — NIST AI RMF, ISO/IEC 42001, and the EU AI Act converge on traceability, auditability, and controlled execution (Cockcroft et al., When Agents Decide). An org that builds decision tracking + policy enforcement for its agents pre-builds most of what compliance will require; "the agent decided" alone is not an answer a court accepts.

## 5. Cross-repo / cross-team coordination

**What's missing:** [Factor 12](12-switchboard-coordination.md)'s switchboard is scoped to one factory floor. Nothing addresses coordination when a ticket spans five services owned by five teams with five different switchboards — which is where most real organizations actually live, not in a single-repo demo.

**Why it matters:** without this, the switchboard pattern looks great in the running example (one team, one repo) and becomes unclear the moment a rate-limit change touches a shared gateway service owned by a different team.

**Open question:** does cross-team coordination need a switchboard-of-switchboards, or does it stay a human problem (cross-team tickets, same as today) with the agent pipeline only ever operating inside one team's floor?

## 6. Incident response

**What's missing:** what happens when agent-shipped code causes a production incident. [Factor 11](11-human-on-the-loop.md) covers mid-run escalation (the agent asks a human *before* shipping); nothing covers the postmortem process *after* something ships and breaks.

**Why it matters:** the audit trail from [Factor 14](14-mandate-and-provenance.md) gives you the forensics, but not the process — is this postmortem different from a human-caused incident? Does "the agent decided X" change blame culture, on-call rotation, or the fix-forward vs. rollback calculus?

**Open question:** does an agent-caused incident get a distinct postmortem template (e.g., trajectory review alongside the usual timeline), or does it fold into existing incident process unchanged?

## 7. Release / supply-chain provenance stitching

**What's missing:** a connection between this blueprint's notion of provenance ([Factor 14](14-mandate-and-provenance.md) — agent-session lineage: who authorized it, what it consumed, what it changed) and supply-chain provenance in the SLSA/in-toto sense (which source commit, which build system, which inputs produced a given binary). Release engineering — SBOM generation, VEX statements, cryptographic signing, GitOps deployment — is deliberately out of scope for this blueprint; it's mature, well-specified practice that doesn't change based on who authored the diff. But nothing here answers whether an artifact's build attestation should also record that its source commits were agent-authored, under what mandate, gated by which eval run. Release engineering — SBOM generation, VEX statements, cryptographic signing, GitOps deployment — is deliberately out of scope for this blueprint; it's mature, well-specified practice that doesn't change based on who authored the diff. But nothing here answers whether an artifact's build attestation should also record that its source commits were agent-authored, under what mandate, gated by which eval run.

**Why it matters:** an org running both disciplines will eventually be asked "show me every artifact in this release whose source was AI-generated, and what governed it" — a real audit/compliance question neither SLSA nor this blueprint currently answers. Without it, agent-session provenance (Factor 14) and build provenance (SLSA) stay two disconnected audit trails that happen to share a name.

**Open question:** does agent-session provenance get embedded as a field in existing attestation formats (an in-toto predicate, a SLSA provenance extension), or does it stay a separate record cross-referenced by commit hash at audit time?

## 8. Continuous model churn & silent drift

**What's missing:** an operational lifecycle for managing upstream model deprecations and silent behavioral drift. Model vendors retire API endpoints on 3–6 month cadences and silently alter inference optimizations and alignment weights under fixed tags.

**Why it matters:** an enterprise cannot manually re-calibrate prompts, invariant anchors ([Factor 07](07-invariants-and-calibration.md)), and adversarial review thresholds ([Factor 09](09-adversarial-review.md)) across dozens of production pipelines whenever a foundational model is deprecated. Cockcroft et al. (When Agents Decide) give this failure its anecdote: an 18-month-old forecasting platform still running while its models were replaced three times underneath, tooling acquired, and a framework breaking-changed — "a museum" answering last week's questions.

**Open question:** how should the eval harness ([Factor 10](10-evaluations-and-save-everything.md)) automate upstream model canary qualification before a new model checkpoint is permitted to take over production switchboard queues?

## Longevity: not applicable

These aren't factors yet, so they don't carry a Longevity verdict. If and when one of them earns a real conformance check, it moves into the numbered, scored set and picks up a verdict there.
