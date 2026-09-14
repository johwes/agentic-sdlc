# Technical Specification: Conference Presentation on Nested-Loop Agentic SDLC

## 1. Specification Metadata
- **Status**: DRAFT / APPROVED FOR TDD
- **Target Deliverable**: `docs/index.html` (Reveal.js Presentation) + `.github/workflows/deploy_presentation.yml`
- **Derived From**: [intent-presentation.md](file:///var/home/jwesterl/Downloads/opencode/agentic-sdlc/intent-presentation.md)
- **Governing Architecture**: [agentic-sdlc.md](file:///var/home/jwesterl/Downloads/opencode/agentic-sdlc/agentic-sdlc.md)

---

## 2. Presentation Technical Architecture

### 2.1 Dependencies & Delivery
- **Engine**: Reveal.js 5.x via cdnjs (CSS + JS).
- **Plugins**:
  - `RevealNotes` (Presenter mode, speaker notes, timer via key 'S').
  - `RevealHighlight` (Code syntax highlighting).
- **Theme**: Dark, high-contrast engineering theme (`black.css` with custom typography and accent gradients).
- **Assets**: Inline CSS and SVG diagrams for zero external network failure points.

### 2.2 Slide Outline & Identification Contract
Every slide will be enclosed in `<section id="slide-{number}">` and contain an `<aside class="notes">` speaker note:

| Slide ID | Title | Key Concept & Visual Component |
| :--- | :--- | :--- |
| `slide-1` | **The Autonomous Coding Dilemma** | Title slide: From Copilot chat to autonomous agent execution. |
| `slide-2` | **The Honeymoon is Over** | The 3 failure modes: Reward hacking, test erosion, reviewer fatigue. |
| `slide-3` | **The Harness Problem** | Prompt engineering vs. Harness engineering (Barbaste 2026 / Bölük). |
| `slide-4` | **The 3-Tier Document Hierarchy** | **Visual 1**: Architecture Pyramid (`agentic-sdlc.md` $\to$ `intent.md` $\to$ `spec.md`). |
| `slide-5` | **The Nested-Loop Architecture** | **Visual 2**: Double-Loop Diagram (SDD $\times$ TDD $\times$ EDD). |
| `slide-6` | **The Inner Loop: Workstation TDD** | Fast, local iteration: Intent $\to$ Spec $\to$ RED $\to$ Agent $\to$ GREEN. |
| `slide-7` | **Hard Guardrails: The Anti-Tampering Shield** | **Visual 3**: SHA-256 Tripwire stopping agents from cheating on tests. |
| `slide-8` | **The Subprocess Wrapper Pattern** | Wrapping commodity agents (`opencode`, `claude`, `agy`) vs. custom engines. |
| `slide-9` | **The Outer Loop: CI/CD Governance** | Physical separation: GitHub Actions as the immutable release gate. |
| `slide-10` | **Machine-Verifiable Evidence** | `ReleaseEvidence` JSON schema, `semantic_delta`, and auto-merge gates. |
| `slide-11` | **Live Case Study: Self-Hosting asdlc** | The meta-loop: How PR #1 built the harness and PR #2 built this deck! |
| `slide-12` | **The Economics of Agentic SDLC** | Token cost ($0.80–$2.50) vs engineer cycle time ($80+/hr triage). |
| `slide-13` | **Key Takeaways & Action Plan** | 3 steps any team can take Monday morning to adopt nested-loop SDLC. |

---

## 3. Required Visual Elements Contract

1. **Document Hierarchy Pyramid (`#visual-doc-pyramid`)**:
   - High-contrast SVG/CSS pyramid showing:
     - Foundation: Macro Architecture Whitepaper (`agentic-sdlc.md`)
     - Aperture: Scoped Intent Work Order (`intent.md`)
     - Contract: Technical Specification (`spec.md`)
2. **Nested Double-Loop Workflow (`#visual-double-loop`)**:
   - Visual comparison of:
     - Inner Loop (Developer Workstation, Fast, Local pytest halting, SHA-256 protected).
     - Outer Loop (GitHub Actions Runner, Clean environment, LLM Judge, Evidence generation).
3. **Anti-Tampering Tripwire (`#visual-anti-tampering`)**:
   - Visual representation of the agent attempting to edit `assert False` $\to$ `assert True`, intercepted by SHA-256 checksum verification raising `TestTamperingError`.

---

## 4. GitHub Pages Deployment Specification
- GitHub Actions workflow (`deploy_presentation.yml` or integrated into `agentic_outer_loop.yml`) triggered on push to `main`.
- Uses official GitHub Actions Pages deploy action (`actions/deploy-pages@v4` with `actions/upload-pages-artifact@v3`).

---

## 5. Verification Matrix (`tests/test_presentation.py`)

| Test Case | Scenario | Expected Behavior |
| :--- | :--- | :--- |
| `test_presentation_html_exists` | Inspect `docs/index.html` | File exists and contains valid HTML structure. |
| `test_presentation_has_thirteen_slides` | Parse `docs/index.html` with BeautifulSoup or regex | Exactly 13 `<section id="slide-X">` elements present. |
| `test_presentation_has_speaker_notes_for_all_slides` | Verify every `<section>` has `<aside class="notes">` | 13/13 slides have non-empty speaker notes. |
| `test_presentation_includes_all_required_visuals` | Check for `#visual-doc-pyramid`, `#visual-double-loop`, `#visual-anti-tampering` | All 3 visual IDs are present in DOM. |
| `test_presentation_loads_reveal_and_plugins` | Verify script and CSS tags | Contains Reveal.js 5 CDN links and `RevealNotes` plugin initialization. |
