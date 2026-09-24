# 14 — Mandate + provenance (govern the memory)

## Principle

Every autonomous session needs a **principal-authored mandate** before it is valid — the gate that determines whether work can begin at all. And every artifact the system produces must carry its **provenance** — who authorized it, what evidence it consumed, and what it changed — so audit and replay are possible without live services.

## Why this matters

### The mandate gate

Every prior context-memory model (MemGPT, CoALA, Generative Agents) treats memory as a working resource the agent draws from *during* work. Governance-first memory treats it as a **precondition**. The model is:

- **Intent (highest trust):** the principal's mandate — governs all sessions. `destination.md`, written before the agent ever starts. No mandate, no valid session.
- **Trace (medium trust):** the agent's decision history — append-only `audit-trail.md`, `orientation.md`, rewritten only by explicit operations, never silently overwritten.
- **Evidence (independent):** captured LLM interactions — `sessions/*.jsonl`, written by the harness, **agent-inaccessible**. The agent cannot author its own observation record.

This is the RBAC principle — *authorization before action* — applied to agent memory. Without the gate, agency preservation is behavioral hope. With it, it's structural.

### Provenance and replay

Mandate alone isn't enough when multiple agents collaborate across trust boundaries. Three more mechanisms complete the hardening:

- **No bypass, layered gates:** every side-effecting operation (tool use, memory writes, promotion, publishing) traverses deterministic enforcement points — authentication, schema validation, policy evaluation, budgets — with no network or IAM path around them. Where one control is probabilistic (e.g. injection detection), at least one downstream control is deterministic. High-impact actions require multiple independent gates.
- **Data quality at the retrieval boundary:** the memory gateway enforces ACLs and provenance checks (TTL, confidence, provenance-required flags) — the last point at which the control plane can apply minimum quality gates before content reaches the model.
- **Deterministic replay + cryptographic audit trail:** every run emits replay traces with request/response hashes and immutable, hash-linked, signed evidence (decision records, ledger events). A run is *replay-deterministic* if, given the trace and snapshots, the system reproduces the same tool/memory operations without live services.

Together: the mandate says *whether* to start, the trace says *what was decided*, the evidence says *what was observed*, and the gates say *whether the next side effect may proceed*.

## Running example

The rate-limit ticket can only be worked because `destination.md` ("Implement rate-limiting for unauthenticated search, satisfy the existing test suite, do not change billing logic — approved by Platform Lead") exists *before* the first agent spawns. The agent's plan is written to the trace tier (append-only). Every tool call goes through the gateway with policy checks. When the fix ships, its audit chain contains: the mandate hash, the trace of decisions, the captured tool outputs, and the signed ledger event — replayable tomorrow without the agent, without the network.

## Conformance check

1. **Mandate-gate test:** delete `destination.md` (or your equivalent intent file) and try to start an agent session. It must refuse to begin — no fallback, no auto-generated mandate. If it starts anyway, the session is unauthorized by definition.
2. **No-bypass test:** attempt a side-effecting operation (e.g. a file write or a PR creation) that deliberately skips the harness — direct SDK call, raw `gh` invocation, network shortcut. It must be blocked or absent. If the agent can merge because "merge endpoint exists," the capability model is behavioral, not structural (see egg's "no merging — the capability is simply absent").
3. **Replay test:** take a past run's trace and replay it against *snapshots* alone, no live services. The tool/memory boundary operations should replay deterministically with matching hashes. If replay requires the original model or network, evidence is incomplete. Note what "replay" means here: verifying downstream gates against *recorded* outputs — never re-querying the model and expecting identical tokens (GPU batching and floating-point nondeterminism make that impossible even at temperature 0).
4. **Tier-conflict test:** make Intent and Trace disagree (mandate says "do not change billing," agent trace says "changed billing to fix tests"). The resolver must prefer Intent over Trace over Evidence. If the agent's trace can override the mandate, trust-tiered resolution doesn't exist.

## In this repo

The triage adapter's `_sentinel_state` / `current_task.json` is a lightweight analogue, but the mandates/provenance are still early. Broader governance and supply-chain hardening are post-PoC slots (the harness already owns the promotion path and the ledger projection, two of the evidence pieces — but mandate gating, replay-determinism, and signed audit are future work).

## Sources

- Holmager — [Agent Context Memory: the mandate gate, three-tier structure, capture-author separation](https://github.com/ntholm86/agent-context-memory) (an independent spec, not the ACM professional society)
- GATE — [Deterministic control-plane boundaries + replay-determinism](https://deterministicagents.ai/) (tool/memory mediation, no bypass, layered enforcement; cited for the mediation/replay pattern, not a specific control number range)
- egg — [Zero-credential sandbox, gateway sidecar, no merging, phase-locked operations, broadcast-review-converge](https://github.com/jwbron/egg) (infrastructure enforcement over behavioral control)
- Fowler — [Coding Assistants Threaten the Software Supply Chain](https://martinfowler.com/articles/exploring-gen-ai/software-supply-chain-attack-surface.html) (why provenance and mandate matter at the supply-chain boundary)
- Fullsend agents — [phase-gated policy/profile enforcement around skill execution](https://github.com/fullsend-ai/agents) (governance lives in `policies/`/`profiles/`, separate from `skills/` — cited here for the phase-gating pattern)

## Longevity: Constraint-stable, mechanism-evolving

The constraint — *authorization before action; intent outranks trace; every side effect replayable from evidence* — is access-control canon (RBAC/MAC/capabilities predate LLMs by decades). The mechanisms rotate: mandate files today, signed capability tokens and Macaroon-style attenuating credentials tomorrow, whatever attestation comes next. Adopt the token formats as they mature; never renegotiate the gate.
