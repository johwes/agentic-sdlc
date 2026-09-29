# 17 — Blueprint architecture (vendor-neutral)

Source: factors `01`–`15` in this folder + [Red Hat — What even is the harness in AI?](https://www.redhat.com/en/blog/what-even-harness-ai) (Bean, 2026-05-21).
No vendor names. No repo paths. PoC bindings kept out of the normative diagrams (one labeled non-normative footnote at the end of §1).
Maintenance: re-check this diagram against §4 whenever a factor's principle or scope changes — this is a snapshot synthesis and goes stale silently otherwise.

## 1. Matryoshka doll (outside-in)

Read outside-in like Russian dolls: each layer sits inside the one above it
and cannot get around it. The picture shows structure only — what each layer
does is in the table below. Follows Bean: Infrastructure → Sandbox → Harness
→ Runtime → Model, with the blueprint's deterministic shell made explicit (F03).
Coordination (outer loop control plane + switchboard) is deliberately absent
here — it lives in §2, not inside any single doll.

```mermaid
flowchart TB
    subgraph INFRA[Infrastructure]
        subgraph SB[Sandbox]
            subgraph SHELL[Shell]
                SHELL_SUB[Substrate]
                SHELL_LOGIC[Logic]
                subgraph HARN[Harness]
                    subgraph RT[Runtime]
                        MODEL[Model]
                    end
                end
            end
        end
    end
```

| Layer (outer → inner) | Factors | What it does, in plain english |
|---|---|---|
| Infrastructure | — | The machines everything runs on (clusters, VMs, bare metal). Keeps work alive across crashes: timers, retries, resume where it left off. Also stores the switchboard ledger durably. |
| Sandbox | F08 · F05 | The locked room the agent works in. Denies everything by default, watches and records what the agent touches, and holds no real passwords or keys. Sends the provenance trail out. |
| Shell substrate | F03 | The loop engine: runs each attempt, waits, retries. |
| Shell logic | F03 · F06 | The referee: checks results against fixed rules and budgets. Plain rules with no AI involved, testable on their own. Attempt limits, quality regression blocks, pass/fail counting. What the tests say beats what the agent says. |
| Harness | F04 · F07 · F10 · F13 | Everything we teach the agent: ready-made helper scripts instead of raw APIs, must-stay-true rules with good and bad examples, version-controlled instructions, and the test suite that gates changes plus the archive of past runs. |
| Runtime | F01 · F02 | One fresh agent run per attempt: no memory of earlier runs, reads its instructions from files on disk every time. |
| Model | — | The AI itself. It only suggests answers. It cannot check, count, or limit itself. |
| Mandate gate *(permits Sandbox)* | F14 | The written permission slip from a human: no slip, no work. The original instruction always beats whatever the agent decided later. The slip itself never changes; steering only adds dated amendments. |
| Provenance trail *(leaves Sandbox)* | F14 · F10 | The receipt: who allowed the work, what the agent looked at, what it changed. Complete enough to replay later without live systems. Covers the agent session only, not build signing ([Gap 7](16-whats-missing-factor.md#7-release-supply-chain-provenance-stitching)). Records the exact inputs the agent saw, not just file versions. |
| Outside the doll (see §2) | — | The outer loop control plane + switchboard: traffic control *between* separate workstation copies, not a security layer *inside* one. Each §2 station (triage, work, verify) runs its own copy of this doll. |

Reading: a finding that the agent "fixed" something means nothing until the Shell
logic re-ran the check and the Sandbox confirms what was actually touched.
The loop engine without the referee retries blindly; the referee without the
engine forgets across crashes. The Harness makes the agent *competent*; the
Sandbox makes it *safe*. Different owners, different failure modes —
a sandbox failure (did what it shouldn't) is not a harness failure (did poorly
what it should).

*Note on physical topology:* the doll shows logical containment and constraint, not process hosting. In distributed implementations (e.g., a workflow orchestrator + container sandboxes), the Shell substrate executes on the infrastructure control plane outside the container, dispatching attempt executions into the Sandbox via isolated exec primitives. This keeps a compromised or crashing sandbox from taking the outer retry state down with it.

Non-normative PoC binding (for readers coming from this repo, not part of the
vendor-neutral diagram): inner-loop workflow = Shell logic + substrate;
parent workflow = durable projection behind BOARD (§2); dev server = Infra.

## 2. Swimlanes (coordination flow, flat)

Flow = how work moves. No layer knows the layer beside it; all coupling goes
through the switchboard (F12). Flat here because job-shop routing is not nesting.

```mermaid
flowchart TD
    PROD["Producers<br/>features · bugs · CVEs · scanners"]
    BOARD["Switchboard · F12<br/>issues + labels + queries"]
    TRIAGE["Triage · F09 · F05<br/>mediate untrusted findings"]
    WORK["Work · F02 · F04<br/>fix inside the doll"]
    VERIFY["Verify · F09 · F10<br/>fresh review + eval gates"]
    OUT["Outputs<br/>proposal + provenance + evidence"]
    HUMAN["Humans · F11<br/>dashboard · steer at gates"]

    PROD -->|"structured frame"| BOARD
    BOARD -->|"label query"| TRIAGE
    TRIAGE -->|"work order"| BOARD
    BOARD -->|"atomic claim"| WORK
    WORK -->|"receipt + diff"| BOARD
    BOARD -->|"label query"| VERIFY
    VERIFY -->|"pass"| OUT
    VERIFY -->|"remediate"| BOARD
    HUMAN <-->|"leases"| BOARD
    OUT -->|"merge decision"| HUMAN
```

TRIAGE, WORK, and VERIFY are each their own instance of the §1 doll — they differ in capability profile within Sandbox (e.g. read-only triage/verify vs Bash+git fix, per Factor 08's scorer-vs-implementer example), not in trust structure.

Notes:

* Producers never call workstations directly (F12). A scanner, a human, and a
  release failure all file the same shape and leave.
* Triage vs fix is a trust split, not a pipeline stage: untrusted external
  findings go through mediation (F05); trusted first-party checks (local
  lint/type/test the author would run pre-PR) inject directly into the Switchboard
  as ready work orders. (Within an active attempt, worker diagnostic outputs also
  inject directly into attempt N+1 per §5 delta 2).
* Verification is a *different context* from production (F09). Regression
  blocks and attempt budgets live in code outside both (F06).
* Humans never sit in the step (F11). Constant approvals per feature,
  regardless of attempts underneath; escalations arrive as objective +
  attempts-made + blocking decision + diff preview, never raw transcripts.
* Scope: this diagram shows one team's switchboard; cross-team / cross-repo
  coordination across different teams' switchboards is an open gap (Factor 16, gap 5).
* Freshness: claims and commits are conditional on state freshness (generation/lease
  token). A steering intervention or re-label mid-run invalidates the token; stale
  writes abort and the ephemeral workspace is discarded — a stale worker never
  overwrites the winner. The discarded workspace is the disposable compute
  environment (F08), not the persisted state — the next attempt reads the patched
  frame and prior receipts fresh from disk (F01/F02), which is how history stays
  intact despite the discard.

## 3. Interactive / automated tiers (F15, dotted)

* Interactive: humans explore, accumulate context, debug against warm state.
  May not execute side effects except by filing a bounded frame.
* Automated: fresh contexts, declared effects, no human in the step.
  May not open interactive sessions on its own authority.
* Handoff is files (F01), re-verified on receipt, resumable mid-attempt
  (pause → patch frame → resume with history intact).
* Mandate steering is append-only: the base mandate stays immutable; interventions
  append signed, timestamped deltas. Effective intent is resolved deterministically
  (base + deltas in order), preserving the baseline audit trail (F14).

```mermaid
flowchart LR
    INT["Interactive session<br/>explore · plan · debug"] -->|"bounded frame"| AUTO["Automated flow<br/>execute · gate · attest"]
    AUTO -->|"ambiguity: steering prompt"| INT
```

## 4. Factor → box map

| Factor | Box | Owns |
|---|---|---|
| 01 state on disk | Runtime (§1) + handoff (§3) | Files are truth; context is cache; static-first prompt order |
| 02 fresh contexts | Runtime (§1), Work (§2) | Same skill file, zero inherited conversation; capped diagnostic receipt only |
| 03 deterministic shell | Shell (§1) | Agent proposes, code decides; owns loop, waiting, verdicts |
| 04 buttons not parts | Harness (§1) | Atomic helpers with contracts; declared effects + cardinality caps |
| 05 don't leak internals | Sandbox (§1), Triage (§2) | Structured verdicts in; tolerant parsing out; assertion-only traces |
| 06 guardrails outside | Shell (§1) | Revision caps, regression block, separate infra vs revision budgets |
| 07 invariants + calibration | Harness (§1) | Must-stay-true list + good/bad anchors; third `indeterminate` where honest |
| 08 least-privilege sandbox | Sandbox (§1) | Capability restriction × reach restriction; placeholder credentials only |
| 09 adversarial review | Triage + Verify (§2) | Fresh-context verifier; deterministic score comparison; no self-review |
| 10 evals + save everything | Harness + Verify (§1/§2) | Held-out evals gate changes; trajectories/thinking/tool calls/costs saved + governed |
| 11 human on the loop | Humans (§2) | Dashboard, constant approvals, leases, in-flight steering, briefing format |
| 12 switchboard | Board (§2) | Labels + queries route; job-shop; modular adoption; atomic claims |
| 13 everything versioned | Harness + Shell (§1) | Prompts/skills/policies/evals as code: diffed, approved, rollback-capable; gate thresholds/caps versioned alongside prompts; provenance records effective inputs as served |
| 14 mandate + provenance | Gate + trail (§1) | Authorization before action; lineage on every artifact; replay without live services |
| 15 interactive tiers | §3 | Explore vs execute split; explicit handoff; escalate-don't-guess |

Factor 16's gaps are unscored and sit outside this map by design.

## 5. Resolved deltas + one proposal

1. Pre-PR gate set — resolved: synchronous in-doll gates (syntax, local unit-test
   subset, secret scan, `forbidden_paths` tripwire); asynchronous out-of-doll
   producers (integration matrices, SAST/DAST, multi-arch builds).
2. Direct inject vs review-agent mediation — resolved: worker's own execution
   outputs inject as capped diagnostic receipts (F02); all external findings pass
   through triage to a bounded work frame (F05).
3. New frame vs appended context — resolved: mid-run telemetry appends one capped
   entry without changing identity; scope shifts (acceptance or target files)
   terminate the attempt, invalidate the freshness token, and post a new frame
   requiring mandate re-authorization. This covers untrusted external findings
   implying scope change; trusted human steering during an authorized pause
   follows §3 (patch + resume), not re-framing.
4. Eval archive governance — proposal (retention TBD per compliance, not locked):
   tiered lifecycle of hot debug stream / redacted golden trajectories / immutable
   metadata index. Shape accepted; windows, redaction rules, and budgets open.
