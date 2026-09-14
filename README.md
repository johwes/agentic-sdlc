# Minimal Nested-Loop Agentic SDLC Reference Harness (`asdlc`)

A reference implementation of the **Nested-Loop Architecture for Agentic SDLC (SDD × TDD × EDD)**, based on the principles in [agentic-sdlc.md](agentic-sdlc.md) and [intent.md](intent.md).

## 🖥️ Live Conference Presentation
- **Interactive Slide Deck**: [https://johwes.github.io/agentic-sdlc/](https://johwes.github.io/agentic-sdlc/)
- **Speaker Guide & Talk Manual**: [docs/speaker-guide.md](docs/speaker-guide.md) (Timing matrix, plain-English analogies, live demo script, and Q&A defense)
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

# 3. Observe Deterministic Halting & TDD Loop
# Act 1: Run with default mock adapter (inert no-op) to observe the halting guarantee:
asdlc tdd --spec spec.md --test-file tests/test_spec.py --agent mock
# -> Starts RED (test_add fails on baseline return 0)
# -> Executes 5 turns without solution
# -> Deterministically halts with exit code 1:
#    ✗ TDD RED: Max turns (5) reached without achieving green.
#    (Persists terminal state {"status": "ABORTED"} in .asdlc/state.json)

# Act 2: Run with a live coding agent to reach GREEN:
# asdlc tdd --spec spec.md --test-file tests/test_spec.py --agent opencode
# asdlc tdd --spec spec.md --test-file tests/test_spec.py --agent claude
# asdlc tdd --spec spec.md --test-file tests/test_spec.py --agent antigravity
# -> Agent implements `return a + b` in src/app.py
# -> pytest runner detects exit code 0 and halts immediately:
#    ✓ TDD GREEN: Iteration succeeded in 1 turn(s).
#    (Persists terminal state {"status": "INTEGRATED"} in .asdlc/state.json)

# 4. Outer Loop CI Evaluation
# Evaluates the committed sample pull request diff (pr.diff) against spec.md:
asdlc eval --spec spec.md --diff pr.diff --tests-passed
# -> ✓ Evaluated outer loop. Verdict: AUTO_MERGE_APPROVED
#    Evidence written to: release-evidence.json (modifies 1 file: src/app.py)
```

### Running Test Verification
To run the automated verification suite asserting all architectural invariants:
```bash
pytest tests/ -v
```

## Security & Branch Protection
The agentic SDLC harness implements **multi-tier test isolation and anti-tampering**:
- **Inner Loop (`asdlc tdd`)**: Computes a SHA-256 hash of the test suite before agent execution; halts immediately with `TestTamperingError` if the agent modifies tests.
- **Outer Loop CI (`asdlc eval`)**: Runs on pull requests, overlaying test files directly from the base branch (`main`) and rejecting PR diffs that modify protected test directories unless explicitly allowed.
- **Production Requirement**: Direct pushes to `main` legitimately bypass PR diff checks to permit authoring tests. Production repositories deploying agentic workflows **must enable GitHub branch protection on `main`** (disallowing direct pushes, requiring pull requests, and enforcing passing CI checks) to ensure all agent-authored code is subject to outer-loop isolation.
