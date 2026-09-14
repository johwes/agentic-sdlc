# Intent: CLI-Level Exit-3 Regression Test (HARDEN-01)

## 1. Problem Statement
In commit `6e99d8e`, a `NameError: name 'InitialTestsAlreadyPassingError' is not defined` was identified when running `asdlc tdd` via CLI against an already-passing test suite. While the import was added to `cli.py`, a regression test at the CLI invocation level (`main(["tdd", ...])`) is required to prove that `cli.py` cleanly intercepts `InitialTestsAlreadyPassingError` and exits with code 3 (`RED INVARIANT FAILURE`) rather than crashing with unhandled exceptions.

## 2. Scope & Invariants
- Invoke `asdlc.cli.main` with `["tdd", ...]` against an already-green test suite.
- Verify return code is 3.
- Verify no `NameError` or unhandled exceptions escape the CLI boundary.

## 3. Acceptance Criteria
- [x] Test `test_cli_tdd_handles_initial_tests_already_passing` executes `main(["tdd", ...])` on passing code.
- [x] Exit code 3 is returned deterministically.
- [x] No `NameError` or unhandled exceptions escape the CLI boundary.

## 4. Receipt
- Commit: `6e99d8e0c3b7b64b0d712de0cdf499d8344f79d8`
- Verification: `tests/test_asdlc.py::test_cli_tdd_handles_initial_tests_already_passing`
