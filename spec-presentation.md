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
| `test_presentation_svg_font_sizes_meet_minimum_threshold` | Parse all SVG `<text>` elements | No SVG font-size is below 14.0px (ensures readability). |
| `test_presentation_svg_text_fits_within_bounding_rects` | Parse all SVG `<rect>` and `<text>` elements | Estimated text width does not exceed innermost enclosing rect width. |
| `test_presentation_css_grid_has_min_width_zero` | Check CSS grid rules | Enforces `min-width: 0` on grid children to prevent horizontal blowout. |
| `test_presentation_code_boxes_wrap_preformatted_text` | Check `.code-box` style | Enforces `white-space: pre-wrap` on monospace blocks. |
| `test_presentation_reveal_config_has_responsive_scaling` | Check `Reveal.initialize` | Specifies `minScale` and `maxScale` for automatic viewport fitting. |
| `test_presentation_claims_contain_no_false_absolutes` | Inspect slide texts | Disallows false absolutes (e.g. "guarantee agents cannot cheat") and unverified names. |
| `test_presentation_slide_eleven_cites_accurate_test_count` | Inspect slide 11 text | Ensures cited test count accurately matches the verified test suite. |
| `test_presentation_slide_ten_uses_grounded_evidence_taxonomy` | Inspect slide 10 text | Enforces "Machine-Verifiable Release Evidence" and grounded gating terminology. |

---

## 6. Visual Design, Typography & Responsive Invariants (Feedback Loop Backport)

Following human acceptance review, the following permanent invariants are codified into the harness:

1. **INV-VIS-001 (SVG Minimum Readability Threshold)**:
   - Text within SVG architecture diagrams must never drop below `14.0px` (standardizing on `14px`–`16.5px`). Subtext must use high-contrast silver (`#c9d1d9`) rather than dim grey to ensure visibility from the back of a conference room.
2. **INV-VIS-002 (CSS Grid Bounding)**:
   - CSS grid layouts (`.grid-2`, `.grid-3`) must explicitly enforce `min-width: 0` on child items to override browser `min-width: auto` defaults.
3. **INV-VIS-003 (Preformatted Code Wrapping)**:
   - All `.code-box` elements must specify `white-space: pre-wrap !important` and `word-break: break-word` so terminal commands with long arguments wrap inside their parent card without stretching the slide canvas.
4. **INV-VIS-004 (Responsive Viewport Canvas)**:
   - Reveal.js must be configured with explicit canvas dimensions (`width: 1150, height: 700`, `minScale: 0.2, maxScale: 2.0`), forcing proportional auto-scaling on any screen or window dimension.
5. **INV-VIS-005 (SVG Text Box Containment)**:
   - Any SVG `<text>` element rendered inside an innermost container `<rect>` must have an estimated rendered width $(\text{char\_count} \times \text{font\_size} \times 0.55)$ less than or equal to the `<rect>` width. Text must not visibly overflow its bounding box container.

---

## 7. Claim Grounding, Factual Verifiability & Terminology Invariants

Following external review, the following credibility invariants are codified:

1. **INV-CLAIM-001 (No False Absolutes or Speculative Citations)**:
   - The presentation must never make ungrounded absolute claims such as `"guarantee agents cannot cheat"` or `"0 test regressions"` (since holdouts, memorization, and prompt injection remain open vectors per whitepaper §4).
   - Author names for citations must not be speculative (e.g. unverified "Barbaste"); references must cite verified empirical benchmark sources.
2. **INV-CLAIM-002 (Verifiable Test Metrics on Slide 11)**:
   - The test pass count cited on Slide 11 must be factually accurate and match the repository's verified test suite count.
3. **INV-CLAIM-003 (Accurate Evidence Taxonomy)**:
   - Slide 10 must accurately refer to `"Machine-Verifiable Release Evidence"` (not "Cryptographic Release Evidence"), and distinguish between automated low-risk gating and advisory review.
