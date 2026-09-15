# Technical Specification: Conference Presentation on the Agentic SDLC Control Plane

## 1. Specification Metadata
- **Status**: DRAFT / APPROVED FOR TDD
- **Target Deliverable**: `docs/index.html` (Reveal.js Presentation) + `.github/workflows/deploy_presentation.yml`
- **Derived From**: [intent-presentation.md](file:///var/home/jwesterl/Downloads/opencode/agentic-sdlc/intent-presentation.md)
- **Governing Architecture**: [agentic-sdlc.md](file:///var/home/jwesterl/Downloads/opencode/agentic-sdlc/agentic-sdlc.md) — control-plane thesis (price tradeoffs, enforce mechanically, ration attention); SDD × TDD × EDD as instantiations

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
Every slide will be enclosed in `<section id="slide-{number}">` and contain an `<aside class="notes">` speaker note. Narrative arc (101/201 audience): **Act I — what an Agentic SDLC is** (slides 1–5), **Act II — tradeoffs** (slides 6–8), **Act III — implementation choices** (slides 9–13):

| Slide ID | Title | Key Concept & Visual Component |
| :--- | :--- | :--- |
| `slide-1` | **The Agentic SDLC Control Plane** | Title slide: price tradeoffs, enforce mechanically, ration attention. |
| `slide-2` | **The Problem in One Frame** | Autonomy without governance relocates cost: tokens $\to$ review minutes $\to$ incidents. |
| `slide-3` | **The Answer: A Control Plane** | Four properties (price, enforce, separate, ration); SDD $\times$ TDD $\times$ EDD as instantiations. |
| `slide-4` | **The Loop, Concretely** | **Visual 1**: Architecture Pyramid (`agentic-sdlc.md` $\to$ `intent.md` $\to$ `spec.md`) + SDD contract summary. |
| `slide-5` | **The Nested Double-Loop** | **Visual 2**: Double-Loop Diagram (fast local inner loop vs. governed CI/CD outer loop). |
| `slide-6` | **Enforcement, Not Instruction** | **Visual 3**: SHA-256 Tripwire stopping agents from cheating on tests; mechanisms-not-messages doctrine. |
| `slide-7` | **The Balance Sheet** | Three coupled tradeoff pairs (tokens↔review, rigor↔speed, autonomy↔assurance); price-every-control doctrine. |
| `slide-8` | **What Measurement Shows** | Grounded evidence with scoping: 27% function hit rate vs ~80% file localization (arXiv:2511.00197); benchmark-leakage vs deployment-residual split. |
| `slide-9` | **Open Disputes, 60 Seconds** | Ritual skepticism, test-authorship limits, metric boundaries — each with its mind-changer. |
| `slide-10` | **Inner-Loop Choices** | Sealed TDD vs upfront-design-first; turn/time budgets; sandboxing rungs; test-authorship ladder. |
| `slide-11` | **Outer-Loop Choices** | Deterministic gates $\to$ judges $\to$ human review; N-seed minima; trajectory eval; `ReleaseEvidence` schema and verdicts; proven here — all 29 suite tests green. |
| `slide-12` | **Entries, Autonomy & Proof** | Human flow vs event-triggered dark flow (eligibility, reversibility, kill switch); self-hosting case study (PR #1 / PR #2); economics budgets. |
| `slide-13` | **Takeaways for Monday Morning** | Tier context, price controls twice, enforce-don't-instruct; repo link. |

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
| `test_presentation_claims_contain_no_false_absolutes` | Inspect normalized slide text | Disallows false absolutes (e.g. "guarantee agents cannot cheat", "fake exit codes") and unverified names using tag-stripped normalized text. |
| `test_presentation_slide_eleven_cites_accurate_test_count` | Inspect slide 11 text | Ensures cited test count matches the verified test suite count (serves as an intentional forcing function). |
| `test_presentation_slide_ten_uses_grounded_evidence_taxonomy` | Inspect slide 10 text | Enforces "Machine-Verifiable Release Evidence" and rubric scaffold terminology (Security enforced; Bugs & Spec Alignment roadmap). |
| `test_presentation_slide_two_cites_accurate_localization_metrics` | Inspect slide 2 text | Asserts quantitative claims cite reported literature figures (27% function hit rate vs ~80% file localization, arXiv:2511.00197). |

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

1. **INV-CLAIM-001 (No False Absolutes, Speculative Citations, or Nonexistent Threat Vectors)**:
   - The presentation must never make ungrounded absolute claims such as `"guarantee agents cannot cheat"` or `"0 test regressions"` (since holdouts, memorization, and prompt injection remain open vectors per whitepaper §4).
   - Research citations must carry full author attribution (all authors), venue, and year — e.g. Barbaste, Darrigol, Vu & Wiltberger for the harness-anatomy study — never a lone surname, and never a speculative author name; references must cite verified empirical benchmark sources.
   - Named threat vectors must map to implemented controls; nonexistent threats (e.g. "fake exit codes", which the harness structurally precludes) must not be claimed.
   - Verification tests MUST run against normalized text (stripping HTML tags, unescaping entities, collapsing whitespace) so tag formatting cannot evade assertions.
2. **INV-CLAIM-002 (Verifiable Test Metrics on Slide 11 & Intentional Forcing Function)**:
   - The test pass count cited on Slide 11 must be factually accurate and match the repository's verified test suite count.
   - Enforcing the exact count in tests is an intentional architectural forcing function compelling synchronized documentation updates whenever the test suite expands.
3. **INV-CLAIM-003 (Accurate Evidence Taxonomy & Rubric Scaffold Status)**:
   - Slide 10 must accurately refer to `"Machine-Verifiable Release Evidence"` (not "Cryptographic Release Evidence"), and distinguish between automated low-risk gating and advisory review.
   - The 3-bucket rubric must be explicitly labeled as a scaffold with security path-isolation enforced today and automated bug / spec-alignment checks on the roadmap.
4. **INV-CLAIM-004 (Empirical Localization Metrics on Slide 2)**:
   - Quantitative citations on Slide 2 must match published literature findings (e.g. 27% function localization vs ~80% file localization from arXiv:2511.00197) rather than rounded or unsourced generalizations.
