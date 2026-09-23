# 01 — State on disk, or it doesn't exist

## Principle

Every piece of state the agent needs — flags, queues, counters, timestamps, instructions, the rubric it scores against — lives in a file the moment it is known. The context window is a cache, not the source of truth.

## Why this matters

A long-running agent conversation gets **compacted** to stay inside the model's context limit. Anything that only lived in the conversation can disappear. The production system that taught this ran 50-item batches and watched retry queues silently empty, scores drift, and midnight timestamps appear as `20260401-000000` — all because counters and queues had never been written down.

Writing to disk is necessary but not sufficient. Compaction also **changes behavior**: an orchestrator told to "re-run assessment" on revised items invented its *own* rubric after its memory was wiped — five neat criteria, applied with full confidence, none of them the ones the team had specified. Same agent, same prompt, different understanding of the job on the other side of compaction. The fix was replacing every natural-language pointer with the *same explicit template* (same file paths, same substitution variables like `{KEY}`, `{DATA_FILE}`) pasted verbatim into both steps. Consistency went from coin-flip to 49/50 identical.

Saving state to disk controls **data loss**. Reusing identical templates controls **behavior drift**. You need both.

## Running example

The rate-limit ticket is triaged: the team writes `search-scope.md` (which endpoint, which users), `rate-limit-plan.md` (middleware choice, test strategy), and `progress.json` (step counter). The agent reads them at the start of *every* attempt. If compaction wipes its memory mid-run, the next attempt re-reads the same files and picks up exactly where it left off — no hallucinated queue, no reinvented scope.

## Conformance check

You can verify this in your pipeline today:

1. Pick a long batch (≥ 30 items, or one item through 5+ retries — long enough that at least one compaction has had time to fire).
2. During the run, kill the agent process mid-batch and restart it from the persisted state — no replaying the conversation, only the files on disk.
3. Compare before/after: retry queue length, item counts, and any scoring or labeling decisions on items that were already processed. They should be byte-identical. If the resumed run invented a new label, dropped a retry, or reset a counter to zero, something is still living only in context.

**Also check:** `grep` your skill files and agent prompts for phrases like "as before," "re-run the earlier step," or "using the rubric mentioned above." Replace each with an explicit file path and template. Two steps that share a rubric should point at the *same* file, not two paraphrases of the same instruction.

**Cost discipline:** the same files double as prompt-cache architecture. Providers key their prompt cache on the exact bytes of the rendered prefix — stable instructions first, volatile content last. A timestamp or per-request ID near the front silently voids the cache for everything behind it (cache reads cost ~0.1× base input; misses re-bill at full price). So: order prompts static-first / dynamic-last, freeze tool lists deterministically, and alarm on cache-hit-rate (`cache_read_input_tokens` / total input) the way you'd alarm on latency. Parallel sub-agents need **isolated workspaces first** (per-task git worktrees or discard-on-failure overlays, merged back through an orchestrator-managed reducer) — shared checkouts with lockfiles or SQLite WAL prevent corruption but not stale reads, so locks are the fallback, not the default. Every shared-state write is atomic (tmp file + rename — our receipt path already does this at `harness/wrapper.py:947-950`); no watchdog or orchestrator should ever read a half-flushed file mid-compaction.

## In this repo

This principle is structural: each attempt starts as a fresh process, the work order (`current_task.json`) is a file, and Temporal — not the conversation — is the source of truth (see `specs/01-principles.md` Destroy state to maintain precision).

## Sources

- Forrester/Greene — [Compaction doesn't just drop data](https://dev.to/jessica_jason/engineering-for-non-deterministic-coworkers-p0j#compaction-doesnt-just-drop-data-it-changes-behavior) (queues emptying, drift after compression, `{KEY}` templates, 98% consistency)
- InfoQ — [Prompts, tool manifests, and evaluation datasets require versioning as IaC](https://www.infoq.com/articles/prompts-to-production-playbook-for-agentic-development/) (same "if it isn't versioned on disk, it isn't real" consequence at the config layer)
- HumanLayer 12-Factor — [Factor 5: Unify execution state and business state](https://github.com/humanlayer/12-factor-agents) + [Factor 12: Make your agent a stateless reducer](https://github.com/humanlayer/12-factor-agents) (state-machine foundation for "disk is truth")

## Longevity: Permanent

Compaction economics don't retire with bigger windows: billing per token plus truncation means business state can't live in context at any size, and larger windows *increase* contamination surface. Prompt-cache mechanics (exact-prefix match, static-first ordering) are provider-agnostic physics both OpenAI and Anthropic document identically. This factor constrains an interface, not an implementation — it ages like 12-factor's config factor.
