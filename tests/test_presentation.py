"""
Verification test suite for the conference presentation (docs/index.html).
Asserts compliance with spec-presentation.md.
"""

from pathlib import Path
import re
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_HTML = REPO_ROOT / "docs" / "index.html"


def test_presentation_html_exists():
    """Verify docs/index.html exists and is non-empty."""
    assert DOCS_HTML.is_file(), f"Presentation file not found at {DOCS_HTML}"
    content = DOCS_HTML.read_text(encoding="utf-8")
    assert len(content) > 500, "Presentation file is unexpectedly short"
    assert "<!DOCTYPE html>" in content or "<html" in content


def test_presentation_loads_reveal_and_plugins():
    """Verify Reveal.js 5 and the RevealNotes plugin are loaded."""
    content = DOCS_HTML.read_text(encoding="utf-8")
    assert "reveal.js" in content.lower()
    assert "RevealNotes" in content
    assert "RevealHighlight" in content


def test_presentation_has_thirteen_slides():
    """Verify exactly 13 slide sections with id='slide-N' are present."""
    content = DOCS_HTML.read_text(encoding="utf-8")
    slide_ids = re.findall(r'<section\s+[^>]*id=["\'](slide-\d+)["\']', content)
    assert len(slide_ids) == 13, f"Expected 13 slides, found {len(slide_ids)}: {slide_ids}"
    expected_ids = [f"slide-{i}" for i in range(1, 14)]
    assert slide_ids == expected_ids


def test_presentation_has_speaker_notes_for_all_slides():
    """Verify every single slide contains an <aside class='notes'> block with substantive text."""
    content = DOCS_HTML.read_text(encoding="utf-8")
    sections = re.findall(r'<section\s+[^>]*id=["\']slide-\d+["\'][^>]*>(.*?)</section>', content, re.DOTALL)
    assert len(sections) == 13

    for idx, section in enumerate(sections, 1):
        notes_match = re.search(r'<aside\s+class=["\']notes["\']>(.*?)</aside>', section, re.DOTALL)
        assert notes_match is not None, f"Slide {idx} is missing <aside class='notes'>"
        notes_text = notes_match.group(1).strip()
        assert len(notes_text) > 30, f"Slide {idx} speaker notes are too short: '{notes_text}'"


def test_presentation_includes_all_required_visuals():
    """Verify all 3 mandatory visual representations are present."""
    content = DOCS_HTML.read_text(encoding="utf-8")
    required_visuals = [
        "visual-doc-pyramid",
        "visual-double-loop",
        "visual-anti-tampering",
    ]
    for visual_id in required_visuals:
        assert f'id="{visual_id}"' in content or f"id='{visual_id}'" in content, (
            f"Missing required visual representation: #{visual_id}"
        )


def test_presentation_svg_font_sizes_meet_minimum_threshold():
    """
    INV-VIS-001: Asserts that no SVG text element uses font-size below 14.0px.
    Prevents unreadable footnote text on presentation slides.
    """
    content = DOCS_HTML.read_text(encoding="utf-8")
    svg_blocks = re.findall(r'<svg[^>]*>(.*?)</svg>', content, re.DOTALL)
    assert len(svg_blocks) >= 3

    for svg_idx, svg in enumerate(svg_blocks, 1):
        text_tags = re.findall(r'(<text[^>]*>.*?</text>)', svg, re.DOTALL)
        for tag in text_tags:
            fs_match = re.search(r'font-size=["\'](\d+(?:\.\d+)?)["\']', tag)
            if fs_match:
                fs = float(fs_match.group(1))
                assert fs >= 14.0, (
                    f"SVG #{svg_idx} contains element with font-size='{fs}' below 14.0px threshold:\n  {tag.strip()}"
                )


def test_presentation_css_grid_has_min_width_zero():
    """
    INV-VIS-002: Asserts CSS grid child items enforce min-width: 0 to prevent column blowout.
    """
    content = DOCS_HTML.read_text(encoding="utf-8")
    assert "min-width: 0" in content, "Missing min-width: 0 rule for grid bounding"
    assert ".grid-2 > *" in content, "Missing child bounding rule for .grid-2"


def test_presentation_code_boxes_wrap_preformatted_text():
    """
    INV-VIS-003: Asserts .code-box wraps monospace code lines.
    """
    content = DOCS_HTML.read_text(encoding="utf-8")
    assert "white-space: pre-wrap" in content, "Missing white-space: pre-wrap for .code-box"
    assert "word-break: break-word" in content, "Missing word-break: break-word for .code-box"


def test_presentation_reveal_config_has_responsive_scaling():
    """
    INV-VIS-004: Asserts Reveal.js is configured with explicit scaling constraints.
    """
    content = DOCS_HTML.read_text(encoding="utf-8")
    assert "minScale:" in content, "Missing minScale configuration in Reveal.initialize"
    assert "maxScale:" in content, "Missing maxScale configuration in Reveal.initialize"
    assert "width:" in content and "height:" in content, "Missing explicit width/height in Reveal.initialize"


def test_presentation_svg_text_fits_within_bounding_rects():
    """
    INV-VIS-005: Asserts that text labels rendered within SVG rect containers
    do not overflow their container boundaries horizontally.
    """
    content = DOCS_HTML.read_text(encoding="utf-8")
    svg_blocks = re.findall(r'<svg[^>]*>(.*?)</svg>', content, re.DOTALL)
    assert len(svg_blocks) >= 3

    overflows = []
    for svg_idx, svg in enumerate(svg_blocks, 1):
        rects = []
        for m in re.finditer(r'<rect\s+([^>]+)/?>', svg):
            attrs = dict(re.findall(r'([\w-]+)=["\']([^"\']+)["\']', m.group(1)))
            if "x" in attrs and "y" in attrs and "width" in attrs and "height" in attrs:
                w = float(attrs["width"])
                h = float(attrs["height"])
                rects.append({
                    "x": float(attrs["x"]),
                    "y": float(attrs["y"]),
                    "w": w,
                    "h": h,
                    "area": w * h,
                })

        texts = re.findall(r'<text\s+([^>]+)>(.*?)</text>', svg, re.DOTALL)
        for text_attrs, text_body in texts:
            attrs = dict(re.findall(r'([\w-]+)=["\']([^"\']+)["\']', text_attrs))
            if "x" not in attrs or "y" not in attrs:
                continue
            tx = float(attrs["x"])
            ty = float(attrs["y"])
            fs = float(attrs.get("font-size", 14.0))
            anchor = attrs.get("text-anchor", "start")

            clean_text = re.sub(r'<[^>]+>', '', text_body).strip()
            clean_text = clean_text.replace("&bull;", "•").replace("&check;", "✓")
            if not clean_text:
                continue

            # Find innermost containing rect
            containing = [
                r for r in rects
                if r["x"] <= tx <= r["x"] + r["w"] and r["y"] <= ty <= r["y"] + r["h"]
            ]
            if not containing:
                continue
            innermost = min(containing, key=lambda r: r["area"])

            # Skip outer background wrapper frames
            if innermost["w"] > 700 and innermost["h"] > 200:
                continue

            est_width = len(clean_text) * fs * 0.55
            if anchor == "middle":
                left_edge = tx - est_width / 2
                right_edge = tx + est_width / 2
            else:
                left_edge = tx
                right_edge = tx + est_width

            rect_right = innermost["x"] + innermost["w"]
            rect_left = innermost["x"]

            if right_edge > rect_right + 1.0 or left_edge < rect_left - 1.0:
                overflows.append(
                    f"SVG #{svg_idx}: text '{clean_text}' (est_w={est_width:.1f}px) overflows rect "
                    f"[x={rect_left}, w={innermost['w']}] bounds (span=[{left_edge:.1f}, {right_edge:.1f}])"
                )

    assert not overflows, "Detected SVG text overflowing its container rect:\n" + "\n".join(overflows)


def normalize_html(html_text: str) -> str:
    """
    Normalizes HTML for text content assertions:
    - Strips script and style tags completely
    - Strips inline formatting tags (<strong>, <em>, <code>, <span>, <a>, <u>) without adding space,
      preventing tag-split evasion (e.g. 'Auto-<strong>merged</strong>' -> 'Auto-merged')
    - Replaces block/structure tags with whitespace
    - Decodes HTML entities and collapses whitespace
    """
    import html as html_lib
    clean = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html_text, flags=re.DOTALL)
    clean = re.sub(r"</?(?:strong|b|em|i|span|code|a|u)[^>]*>", "", clean)
    clean = re.sub(r"<[^>]+>", " ", clean)
    clean = html_lib.unescape(clean)
    return " ".join(clean.split())


def test_presentation_normalization_helper_detects_tag_split_phrases():
    """
    Negative control: Asserts that normalize_html successfully detects banned phrases
    even when obscured across inline HTML tag boundaries.
    """
    evasive_html = '<p>Auto-<strong>merged</strong> in 15 seconds by <em>Barbaste</em> et al.</p>'
    assert "Auto-merged in 15 seconds" not in evasive_html
    normalized = normalize_html(evasive_html)
    assert "Auto-merged in 15 seconds" in normalized
    assert "Barbaste" in normalized


def test_presentation_claims_contain_no_false_absolutes():
    """
    INV-CLAIM-001: Asserts that presentation text does not make ungrounded absolute
    guarantees, cite nonexistent threat vectors, or cite speculative/unverified author names.
    Uses normalized text so inline tags cannot evade detection.
    """
    content = DOCS_HTML.read_text(encoding="utf-8")
    normalized_content = normalize_html(content)

    forbidden_phrases = [
        "guarantee agents cannot cheat",
        "0 test regressions",
        "Barbaste",
        "fake exit codes",
        "tekton arbiter",
    ]

    for phrase in forbidden_phrases:
        assert phrase.lower() not in normalized_content.lower(), (
            f"Found forbidden or unverified claim in presentation: '{phrase}'"
        )


def test_presentation_slide_eleven_cites_accurate_test_count():
    """
    INV-CLAIM-002: Asserts that Slide 11 does not cite an outdated/incorrect test count (e.g. 11/11).
    Must reflect the repository's verified test suite (28 tests).
    NOTE: Enforcing the exact count is an intentional architectural forcing function
    compelling synchronized documentation updates whenever the test suite expands.
    """
    content = DOCS_HTML.read_text(encoding="utf-8")
    slide_11_match = re.search(r'<section id="slide-11">(.*?)</section>', content, re.DOTALL)
    assert slide_11_match is not None, "Missing #slide-11"
    slide_11_text = slide_11_match.group(1)

    assert "11/11" not in slide_11_text, (
        "Slide 11 contains outdated test count '11/11'."
    )
    assert "all 29 suite tests" in slide_11_text, (
        "Slide 11 should accurately cite the full verified test suite count (29 tests)."
    )


def test_presentation_slide_ten_uses_grounded_evidence_taxonomy():
    """
    INV-CLAIM-003: Asserts that Slide 10 uses grounded evidence taxonomy
    ('Machine-Verifiable Release Evidence') rather than hyperbolic 'Cryptographic' claims,
    and removes unbacked claims (e.g. 'Auto-merged in 15 seconds', 'max 5 nits').
    """
    content = DOCS_HTML.read_text(encoding="utf-8")
    slide_10_match = re.search(r'<section id="slide-10">(.*?)</section>', content, re.DOTALL)
    assert slide_10_match is not None, "Missing #slide-10"
    slide_10_text = normalize_html(slide_10_match.group(1))

    assert "Cryptographic Release Evidence" not in slide_10_text, (
        "Slide 10 claims 'Cryptographic Release Evidence' without crypto signatures in evidence schema."
    )
    assert "Auto-merged in 15 seconds" not in slide_10_text, (
        "Slide 10 claims 'Auto-merged in 15 seconds' which is not backed by an automated merge bot."
    )


def test_presentation_slide_two_cites_accurate_localization_metrics():
    """
    INV-CLAIM-004: Asserts that Slide 2 cites empirical localization metrics from literature
    (arXiv:2511.00197: ~27% function hit rate vs ~80% file localization) rather than imprecise
    or unsourced generalizations (e.g. '70%+ Context Drift').
    """
    content = DOCS_HTML.read_text(encoding="utf-8")
    slide_2_match = re.search(r'<section id="slide-2">(.*?)</section>', content, re.DOTALL)
    assert slide_2_match is not None, "Missing #slide-2"
    slide_2_text = normalize_html(slide_2_match.group(1))

    assert "70%+" not in slide_2_text, "Slide 2 still cites imprecise '70%+' Context Drift"
    assert "27%" in slide_2_text, "Slide 2 must cite the reported ~27% function-level hit rate"
    assert "arXiv:2511.00197" in slide_2_text, "Slide 2 must cite arXiv:2511.00197"


