# Roadmap: Agentic SDLC Reference Harness (`asdlc`)

Source of truth for prioritized work. Status transitions are governance
events, not annotations: a status is valid only with its required artifacts
(see Governance). GitHub Projects/Milestones, if ever adopted, are read-only
views — never authority.

| ID | Title | Status | Priority | Area | Intent | Acceptance | Receipt |
|----|-------|--------|----------|------|--------|------------|---------|
| OPENSHIFT-01 | Tekton mirror of outer loop + parity run | proposed | P1 | openshift | `intents/openshift-pipeline.md` | `tekton/` pipeline YAML + structural tests; same verdict as Actions on N=3 consecutive PRs | — |
| OPENSHIFT-02 | Agent execution as Jobs in one namespace | proposed | P2 | openshift | `intents/openshift-jobs.md` | Hello workspace RED→GREEN inside a Job (restricted SCC, NetworkPolicy enforced, quota-capped); ≥1 denied-egress negative control logged | — |
| HARDEN-01 | CLI-level exit-3 regression test | done | P1 | harness | `intents/harden-cli-exit3.md` | `main(["tdd", ...])` against a green suite exits 3 with the RED banner (covers the ex-NameError handler; import fix alone is unproven) | `6e99d8e` |
| HARDEN-02 | Required-keys validation of `release-evidence.json` | proposed | P1 | harness | `intents/harden-evidence-schema.md` | `run_eval` rejects malformed evidence inputs; negative test with tampered/empty diff | — |
| HARDEN-03 | Persist or formally scope out dead states | proposed | P2 | harness | `intents/harden-lifecycle-states.md` | `TESTS_GENERATED`/`CI_REVIEW_PENDING`/`RELEASE_APPROVED`/`REJECTED` either written by code paths + tests, or removed with a recorded cut in `spec.md` | — |
| DECK-01 | Vendor reveal.js; assert zero external assets | proposed | P2 | deck | `intents/deck-vendor-assets.md` | `docs/vendor/` carries the 3 CDN files; test fails on any external `<script>`/`<link>`; deck renders offline from `file://` | — |
| DECK-02 | Self-counting slide-11 metric | proposed | P3 | deck | `intents/deck-dynamic-count.md` | Cited test count derived from collection (not hardcoded); suite expansion no longer requires a deck edit | — |
| LOOP-01 | Upload `agent-trace.jsonl` as CI artifact | proposed | P3 | harness | `intents/loop-trace-artifact.md` | Trace file uploaded per CI run; retention documented; no secrets in traces (redaction note) | — |

## Governance (example rules — adapt to your tracker)

This file is an *example* backlog, not infrastructure. In production this
role is played by Jira, Linear, or equivalent, which bring their own input
sanity and workflow guardrails. What transfers across tools is the governance
rule, not the file format:

- A status must be valid only with its required artifacts: `accepted` needs
  an intent file; `in-progress` needs the intent file (and at most one item
  may be `in-progress` at a time); `done` needs the intent file plus evidence
  linked (commit SHA / PR); `dropped` needs a recorded reason.
- Jira equivalents: workflow validators blocking transitions without linked
  evidence; board WIP limits; resolution requiring a linked PR or commit.
- Nothing here is machine-enforced; the discipline is a team convention,
  reviewed like any other process decision.
