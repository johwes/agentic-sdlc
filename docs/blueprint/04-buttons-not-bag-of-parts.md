# 04 — Buttons, not a bag of parts

## Principle

The agent decides **what** should happen. A purpose-built helper script decides **how** and runs it **atomically**. Give the agent a button to push, not a bag of parts to assemble.

## Why this matters

Fine-grained generic toolsets (dozens of API wrappers, each exposing the underlying service one-to-one) are the right design for interactive exploration and the wrong design for an autonomous pipeline. Two things go wrong at 2am:

- **The agent improvises.** It calls APIs in the wrong order, skips steps, hallucinates parameters, or picks a non-atomic path that leaves the world half-changed on partial failure.
- **The tool list pollutes the context.** Hundreds of tool descriptions dropped into the window waste the budget that Factor 01 just taught you to protect.

The same instinct shows up far from API calls. The team told an agent to write to `{ID}-feasibility.md`; the agent saw an input file named `RFE-005-gpu-observability-per-team.md` and *helpfully* wrote to `RFE-005-gpu-observability-per-team-feasibility.md`. The progress checker waited for `RFE-005-feasibility.md` forever. The fix was "write to `{ID}-feasibility.md` where `{ID}` is exactly the ID passed to you — do not include the slug." Creativity is a feature until it meets a filename.

The most absurd case: CI watched for the exact string `FULL RUN COMPLETE`. The agent, being helpful, wrote "Pipeline finished!" — same meaning, different string, CI hangs forever. They moved it to a Python script that prints the exact string, because even "say these four words" is too creative a task to leave to a language model.

The rule that survived: **if CI depends on it, code must execute it.** The spectrum runs from "split a 200-page spec into three issues (archive parent, create three children, link, close)" down to "print four words." Same rule everywhere.

Two maintenance truths come with the pattern. First, **buttons have contracts**: when a helper's parameter shape changes, every skill definition that invokes it must update synchronously, or the model will call the new button with obsolete arguments and fail unrecoverably. Version buttons with the skills that call them (Factor 13). Second, **evidence for the constraint is measured**: replacing a generic shell with a constrained interface (100-line file viewer, 50-result search cap, edit bundled with a syntax linter) moved SWE-bench resolution from 3.8% (prior retrieval baseline) to 12.5% on identical model weights (SWE-agent, NeurIPS'24) — the interface, not the parameters, was the lever.

At enterprise scale, statically baking every domain helper into every prompt stops working — codebases are too large. The grown-up form is a **verified tool registry**: agents query for validated atomic tools on demand, loading schemas only for the active sub-task. Same constraint (atomic, owned, transactional), discovered rather than preloaded.

## Running example

The rate-limit feature involves a middleware file and a new test file. The agent doesn't call seven file and git APIs in sequence. It calls one helper: `submit_rate_limit_patch(files=[...])`, which stages, diffs, and commits atomically and returns a one-line outcome. If the commit fails, the helper reports `FAILED: dirty workdir` — not a raw stack trace the agent could act on (see Factor 05).

Splitting a ticket that bundles two concerns is the same: one `split_issue(parent, children)` script, not four Jira API calls the agent could reorder.

## Conformance check

1. **Atomicity test:** pick a multi-step operation that touches two or more external systems (e.g. close parent ticket + open child ticket + link). Run it through your agent 20 times, injecting a transient failure on the second step every 5th run. Half-changed world state (orphaned children, closed parents with no children) should be impossible. If you can produce one, you have a bag of parts where you need a button.
2. **Completion-signal test:** `grep` your pipeline for any string the agent is asked to emit that a downstream step `watch`es for. Replace each with a script that emits the string deterministically, and make the downstream step watch the script's exit code, not the agent's prose.
3. **Tool-surface test:** list the tools available in one agent's context. If the list is the entire API surface of a service, narrow it to one purpose-built script per task that agent actually performs. Everything else is menu pollution.

## In this repo

The wrapper owns the `task_receipt.json` envelope (the LLM only supplies a summary trailer); cell git ops are a fixed allowlist; promotion and triage are helper scripts rather than agent tool chains.

## Sources

- Forrester/Greene — [Prefer buttons over a bag of parts](https://dev.to/jessica_jason/engineering-for-non-deterministic-coworkers-p0j#constrain-creativity-prefer-buttons-over-a-bag-of-parts) + [If CI depends on it, code must execute it](https://dev.to/jessica_jason/engineering-for-non-deterministic-coworkers-p0j#avoid-generic-mcp-use-helper-scripts)
- HumanLayer 12-Factor — [Factor 4: Tools are just structured outputs](https://github.com/humanlayer/12-factor-agents)
- Fullsend agents — `skills/` as task-scoped buttons (one skill per station, not one API per endpoint) — [fullsend-ai/agents](https://github.com/fullsend-ai/agents)

## Longevity: Constraint-stable, mechanism-evolving

The constraint — *multi-step world changes execute atomically through owned code* — is permanent; unconstrained primitives yield invalid states at any capability level. The form evolves: hand-maintained scripts → declarative API schemas compiled into transactional tools → registry-discovered verified tools. Review this factor when the button catalog, not the principle, starts creaking.
