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
