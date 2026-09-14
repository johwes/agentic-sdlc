# Minimal Nested-Loop Agentic SDLC Reference Harness (`asdlc`)

A reference implementation of the **Nested-Loop Architecture for Agentic SDLC (SDD × TDD × EDD)**, based on the principles in [agentic-sdlc.md](agentic-sdlc.md) and [intent.md](intent.md).

## Core Principles
1. **SDD Inner Loop**: Intake from `intent.md` strictly bounds task scope to generate `spec.md` before code is generated.
2. **TDD Inner Loop**: Wraps commodity coding agents (`opencode`, `claude`, `antigravity`, `mock`) with deterministic halting (`pytest`) and SHA-256 test anti-tampering verification.
3. **EDD Outer Loop (CI/CD)**: GitHub Actions workflow evaluating PR diffs, computing `semantic_delta`, and emitting machine-verifiable `release-evidence.json`.

## Quickstart

### Installation
```bash
pip install -e .
```

### CLI Usage
```bash
# 1. Initialize project
asdlc init

# 2. Run SDD intake on intent.md
asdlc sdd --intent intent.md --out spec.md

# 3. Run TDD inner loop wrapping an agent
asdlc tdd --spec spec.md --test-file tests/test_spec.py --agent mock

# 4. Outer loop CI evaluation
asdlc eval --spec spec.md --diff pr.diff --tests-passed
```
