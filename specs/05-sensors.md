# 05 — Sensors (Upstream Static & Security Analysis)

Source: `intent.md` §§1–2 (sensor inversion), §3 (T1 sensor step).

## Goal

Move SonarQube, CodeQL, Snyk, Trivy, and DAST upstream/inward so they act as
sensory organs emitting structured findings that directly drive remediation
loops — instead of downstream pass/fail gates needing human intervention.

## Non-goals

- Release-time signing/scanning-as-gatekeeping (see `06-release.md`).
- Inner-loop AST/hold-out gates (see `03-inner-loop.md`).

## Inputs

- Candidate code checkpoints / diffs.

## Outputs

- Structured SARIF/JSON findings routable to ledger tasks (parent) or targeted
  remediation frames (child).

## Flow

1. Sensor suite runs against candidate output.
2. Findings normalize to SARIF/JSON.
3. Parent ledger converts findings into remediation work items.
4. Child loop re-attempts with sensor context in the projected frame.

## Failure modes

- Unactionable findings (no file/line/rule mapping) — must not spawn empty loops.
- Sensor flakiness causing infinite remediation (needs severity thresholds and
  suppression policy, TBD).
- DAST environment drift (target must be pinned per run).

## Open questions

- Sensor versions, rule packs, and severity → action mapping?
- SARIF normalization schema location?
- DAST target provisioning and scoping?
- Suppression/baseline policy for pre-existing findings?
