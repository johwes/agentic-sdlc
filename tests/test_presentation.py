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
    INV-VIS-001: Asserts that no SVG text element uses font-size below 11.5px.
    Prevents unreadable footnote text on presentation slides.
    """
    content = DOCS_HTML.read_text(encoding="utf-8")
    svg_blocks = re.findall(r'<svg[^>]*>(.*?)</svg>', content, re.DOTALL)
    assert len(svg_blocks) >= 3

    for svg_idx, svg in enumerate(svg_blocks, 1):
        font_sizes = re.findall(r'font-size=["\'](\d+(?:\.\d+)?)["\']', svg)
        for fs_str in font_sizes:
            fs = float(fs_str)
            assert fs >= 11.5, (
                f"SVG #{svg_idx} contains font-size='{fs}' below the minimum readability threshold of 11.5px"
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

