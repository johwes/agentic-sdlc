# Intent: Conference Presentation on the Agentic SDLC Control Plane

## 1. Problem Statement
Software engineering conferences are saturated with hype around AI copilots, but engineering leaders and senior developers face harsh operational realities: autonomy without governance relocates cost (tokens $\to$ review minutes $\to$ incidents), agents bypass advisory instructions under pressure, and review capacity does not scale with generated output.

We need an engaging, visually compelling conference presentation hosted on GitHub Pages that clearly explains the **Agentic SDLC Control Plane** for a 101/201 audience: what an Agentic SDLC is (a control plane that prices tradeoffs, enforces mechanically, and rations attention — with SDD $\times$ TDD $\times$ EDD as instantiations), what the tradeoffs are (coupled cost ledgers and the evidence behind them, scoped honestly), and which implementation choices teams can make (inner-loop options, outer-loop options, human vs event-triggered entries). The deck must demystify autonomous coding, present hard empirical evidence with scoping caveats, showcase the architecture, and demonstrate the working reference implementation (`asdlc`).

---

## 2. Scope & Target Audience
- **Target Audience**: General Tech / Conference audience (Engineers, Tech Leads, Architects, Engineering Managers).
- **Format**: Responsive, self-contained HTML5 presentation using **Reveal.js** (CDN-backed, zero node build tooling required) located at `docs/index.html`.
- **Slide Count**: ~13 curated slides following a 3-Act narrative arc:
  1. *Act I: What an Agentic SDLC Is* (control-plane thesis, problem-in-one-frame, the loop concretely, enforcement-not-instruction).
  2. *Act II: Tradeoffs* (balance sheet, grounded evidence with scoping, 60-second open disputes).
  3. *Act III: Implementation Choices* (inner-loop options, outer-loop options, entries/autonomy/proof, economics, takeaways).
- **Visual Representations (Mandatory)**:
  1. *The Nested Double-Loop Diagram*: Visualizing the fast local inner loop vs. the governed CI/CD outer loop.
  2. *The Anti-Tampering Shield*: Showing how SHA-256 test manifests prevent agent cheating.
  3. *The 3-Tier Document Pyramid*: Architecture (`agentic-sdlc.md`) $\to$ Intent (`intent.md`) $\to$ Spec (`spec.md`).
- **Speaker Notes**: Every slide must include rich, actionable speaker notes in `<aside class="notes">` blocks so the presenter can press `S` to access live presenter mode.
- **Hosting**: GitHub Pages hosting served from `docs/` or deployed via GitHub Actions.

---

## 3. Non-Goals
- Heavy JavaScript framework build steps (no webpack/vite/npm requirements).
- Video-heavy multimedia embeds that require external streaming bandwidth.
- Proprietary or paid presentation platforms (Marp/Pitch/Keynote).

---

## 4. Acceptance Criteria
- [ ] `docs/index.html` exists and loads Reveal.js with core plugins (notes, syntax highlighting).
- [ ] All 13 slides are present with specific identifiers and responsive styling.
- [ ] All 3 visual representations (Double Loop, Anti-Tampering Shield, Document Pyramid) are embedded.
- [ ] Every slide has non-empty `<aside class="notes">` speaker notes.
- [ ] Automated pytest suite (`tests/test_presentation.py`) validates HTML integrity, slide counts, diagrams, and notes.
- [ ] GitHub Actions workflow deploys the presentation to GitHub Pages on merges to `main`.
