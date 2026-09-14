# Minimal Nested-Loop Agentic SDLC Reference Harness (`asdlc`)

A reference implementation of the **Nested-Loop Architecture for Agentic SDLC (SDD × TDD × EDD)**, based on the principles in [agentic-sdlc.md](agentic-sdlc.md) and [intent.md](intent.md).

## 🖥️ Live Conference Presentation
- **Interactive Slide Deck**: [https://johwes.github.io/agentic-sdlc/](https://johwes.github.io/agentic-sdlc/)
- *Tip: Press **`S`** while viewing the slides to open Presenter Mode with live speaker notes, timers, and previews.*

## Core Principles
1. **SDD Inner Loop**: Intake from `intent.md` strictly bounds task scope to generate `spec.md` before code is generated.
2. **TDD Inner Loop**: Wraps commodity coding agents (`opencode`, `claude`, `antigravity`, `mock`) with deterministic halting (`pytest`) and SHA-256 test anti-tampering verification.
3. **EDD Outer Loop (CI/CD)**: GitHub Actions workflow evaluating PR diffs, computing `semantic_delta`, and emitting machine-verifiable `release-evidence.json`.

## Quickstart

### Installation
```bash
git clone https://github.com/johwes/agentic-sdlc.git
cd agentic-sdlc
pip install -e .
```

### Try the Runnable Reference Project (`examples/hello/`)
The repository includes a ready-to-run reference project in `examples/hello/`:

```bash
cd examples/hello

# 1. Initialize harness in the project
asdlc init

# 2. Run SDD intake on intent.md to produce/verify spec.md
asdlc sdd --intent intent.md --out spec.md

# 3. Run the TDD loop with a coding agent
# Uses mock adapter by default (zero tokens, deterministic):
asdlc tdd --spec spec.md --test-file tests/test_spec.py --agent mock

# Or run with live commodity agents if installed:
# asdlc tdd --spec spec.md --test-file tests/test_spec.py --agent opencode
# asdlc tdd --spec spec.md --test-file tests/test_spec.py --agent claude
# asdlc tdd --spec spec.md --test-file tests/test_spec.py --agent antigravity

# 4. Outer loop CI evaluation
asdlc eval --spec spec.md --diff pr.diff --tests-passed
```

### Running Test Verification
To run the automated verification suite asserting all architectural invariants:
```bash
pytest tests/ -v
```
