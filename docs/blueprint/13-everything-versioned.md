# 13 — Everything versioned (directives as code)

## Principle

Treat every natural-language instruction — prompts, skill files, rubric anchors, policy bundles, evaluation datasets — as a **version-controlled asset** with semantic diffing and formal change approval. Directives are code.

## Why this matters

An agentic system has a fundamentally larger versioning surface than a conventional backend. Alongside application code, you now version:

- **Prompts and skill files** — the primary way to control model behavior. An uncontrolled prompt tweak interacts unpredictably with a system update and is, per RisingWave's research as cited (secondhand, via InfoQ) by the Playbook, the most critical failure mode in production agent failures.
- **Tool manifests** — JSON/YAML specs of available functions, their parameters, and auth requirements. A tool addition changes what the agent *can* do, not just what it *does*.
- **Policy configurations and memory schemas** — the guardrails of Factor 06 and the context contracts of Factor 01.
- **Evaluation datasets and golden trajectories** — the ground truth of Factor 10. If the eval set isn't versioned, you can't tell whether a model upgrade helped or hurt.

Without directive-as-code discipline, you lose the ability to diff what shipped, to roll back what drifted, and to gate what lands:

- **Behavioral drift becomes untraceable.** A prompt paraphrase can flip scores or invent a rubric (Factor 01). Without Git history on prompts, you'll never find which commit did it.
- **Rollback is impossible.** Correlating a production incident with "which prompt was live at 02:14" requires the prompt to have a version to correlate against.
- **Change approval is absent.** Skill files deserve the same PR review as a library — because they *are* a library, one the model imports on every turn.

The mature posture is Infrastructure-as-Code conventions applied to directives: Git + formal approvals + progressive delivery (A/B prompt changes with automatic rollback when behavioral metrics drift) + runtime switchability while version control remains the source of truth.

## Running example

The team wants to try a new rate-limit rubric wording. They open a PR that changes *only* `rubric-rate-limit.md` — the skill diff is visible in GitHub, the eval harness runs the 20 golden trajectories against the new wording, and cost-per-item is compared. The PR merges; the production config switches to the new prompt atomically; if the next batch's score variance exceeds the threshold, the deployment rolls back to the prior prompt version by hash, not by hand-editing.

## Conformance check

1. **Version-history test:** `git log -- prompts/ skills/ policy/` — every active prompt and skill file should appear in version control with an author, a diff, and a PR. If you can change agent behavior by editing a dashboard textarea with no commit, directives are not code.
2. **Active-version test:** in production, can you answer "which exact prompt hash and eval-set hash served ticket N at time T"? If not, you can neither reproduce nor roll back the agent's behavior at that moment.
3. **Progressive-delivery test:** change one prompt's calibration anchors (Factor 07) and deploy to 10% of traffic. Does your pipeline automatically compare behavioral metrics against the control before promoting to 100%? If rollout is "merge and hope," directives are versioned but not delivered as code.
4. **Eval-delta test:** open a PR that touches only a prompt, skill, or policy file. The PR checks must report the eval-set delta (pass rate + cost differential vs. the base) before a human is asked to approve. If prompt PRs carry no behavioral evidence, reviewers are approving prose, not behavior.
5. **Source-artifact test:** the artifact the agent executes is *compiled* from versioned source through validation (schema, allowlisting, pinning, scanning) — never hand-edited in place. Ask "which validated artifact served ticket N?" If the answer is "the Markdown file itself," source and runtime are the same object and no validation stands between edit and execution.

## In this repo

Skill files are component-scoped workflows running both interactively and headlessly — the same file the IDE reads is the file CI executes. The PoC bakes prompt contracts into the cell image (`/etc/prompts/`, `config/`) and governs behavioral change through the image pin (see `specs/04-worker-cell.md`).

## Sources

- InfoQ — [Versioning as IaC: prompts, tool manifests, policy configs, memory schemas](https://www.infoq.com/articles/prompts-to-production-playbook-for-agentic-development/) + [Prompt drift as the most critical failure mode](https://www.infoq.com/articles/prompts-to-production-playbook-for-agentic-development/)
- Bynum — [Skills and plugins as versioned, distributable artifacts](https://cabynum.github.io/posts/software-factory-floor/#the-shared-infrastructure) (skills registry, container images for CI)
- HumanLayer 12-Factor — [Factor 2: Own your prompts](https://github.com/humanlayer/12-factor-agents)
- tikalk — [Factor XI: Directives as Code](https://github.com/tikalk/agentic-sdlc-12-factors)
- Fowler — [Understanding Spec-Driven Development](https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html) (spec-driven development as a versioning discipline — the source itself is skeptical of SDD's rigidity, cited here only for the versioning angle)

## Longevity: Permanent

Change management is the oldest durable discipline in the set — 12-factor's own config/codebase factors aged through every deployment revolution for the same reason. New artifact kinds (memory schemas today, capability grants tomorrow) get absorbed into the same practice: versioned, diffed, approved, rollback-capable. If an artifact can change agent behavior and isn't versioned, that's the gap, regardless of what the artifact is called this year.
