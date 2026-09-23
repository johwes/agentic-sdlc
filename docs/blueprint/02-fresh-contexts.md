# 02 — Fresh contexts every attempt

## Principle

Every sub-agent launches into a **fresh context** that points at the same skill file on disk. No agent inherits another's conversation history.

## Why this matters

The more you leave in context, the more chances the model has to follow the wrong thread:

- **Context bleed:** an agent literally named `assess` decided its job was to *invent new ideas*, because the previous agent's brainstorm was still sitting next to its instructions. Every step of its reasoning was internally consistent — for a question nobody had asked.
- **Evidence contamination:** a `feasibility` check on item 2 passed on the strength of evidence that belonged to item 1, because the second agent had been launched with the first item's leftovers still in scope.

Both bugs share a root: agents were chained in one session instead of isolated. The fix is mechanical, not prompt-clever: fresh context per sub-agent, skill file as the single source of truth. When 50 agents read the *same file* rather than 50 paraphrases of the same instruction, a second source of drift disappears entirely.

## Running example

The rate-limit plan splits into three sub-tasks: middleware, tests, and docs. Each gets its own agent, each launched clean, each reading `middleware-spec.md` directly. The docs agent never sees the middleware agent's half-written code. The test agent never inherits the middleware agent's error messages. When the second sub-task is retried, it starts from the spec file alone — not from the failed attempt's transcript.

## Conformance check

1. Launch the same sub-agent twice on different items in the same parent run. After both finish, diff their starting prompts — they should be identical except for the item-specific input (ticket ID, file path). If one carries the other's tool outputs or reasoning, the launch isn't isolated.
2. Deliberately fail item 1 (e.g. a missing file), then launch item 2 whose fix is straightforward. If item 2's outcome changes when you run it *before* vs. *after* the failing item, evidence is leaking across launches. Fix the launch to point at the skill file and pass only item-scoped inputs.

**Also check:** `grep` your orchestrator for any place it appends one agent's result to the next agent's prompt as "context." Replace that with a file write and a pointer.

**Cold-start measurement:** fresh contexts re-pay orientation on every launch — but how much that costs depends on cache warmth, not on principle. Plot time-to-first-token *and* cache-hit-rate per attempt across 30 runs. Where the cache is warm (same model, stable prefix order, attempts inside the TTL window), re-ingest is cheap reads and the tax is latency only; where hit-rate collapses (long escalations, model switches, compaction rewrites), the tax is money. The gap between the two lines names your cold-start tax — optimize layout (Factor 01's static-first ordering) only where the gap is real, and beware proposals (pre-built indexes, preloaded contexts) whose build cost exceeds the measured gap.

**Structured exception:** total amnesia has a failure mode of its own — oscillation. A debugger that can't see which hypotheses already failed will retry the same two plausible implementations on alternating attempts forever. The fix isn't conversation, it's a **capped, text-only diagnostic receipt**: root cause + failed operations, no transcript, no reasoning trace. Enough to avoid the loop, too small to pollute.

## In this repo

One attempt = one headless process, same baked prompt, conversational memory explicitly destroyed every turn (`specs/01-principles.md`). Prior attempts ride only as capped text diagnostics, never as conversation.

## Sources

- Forrester/Greene — [Yesterday's context is today's bug](https://dev.to/jessica_jason/engineering-for-non-deterministic-coworkers-p0j#yesterdays-context-is-todays-bug) (assess inventing ideas, feasibility on wrong evidence)
- CodeDelegator — [Ephemeral-Persistent State Separation](https://ar5iv.labs.arxiv.org/html/2601.14914) (ephemeral coder with fresh context, debugging traces discarded with the instance)

## Longevity: Permanent

Attention mechanics, not model versions: more context means more threads to follow wrongly, so larger windows *raise* the contamination risk this factor guards against. The capped-receipt exception is part of the factor, not a workaround — assess any "richer context passing" proposal against the oscillation-vs-pollution tradeoff explicitly.
