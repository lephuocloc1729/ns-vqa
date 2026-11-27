"""tools/draft_catalog_rows.py: VISUAL_REVIEWED (the D10 visual check), offline."""

import pytest

import tools.draft_catalog_rows as dcr

pytestmark = pytest.mark.skipif(not dcr.LAW.exists(), reason="dataset not available (set VQA_DATASET_DIR)")


def test_regenerating_reproduces_the_committed_yaml():
    """The tool, with VISUAL_REVIEWED as committed, writes kb/sign_catalog_meaning.yaml
    byte for byte."""
    assert dcr.to_yaml(dcr.draft_rows()) == dcr.OUT.read_bytes().decode("utf-8")


def test_an_empty_visual_reviewed_set_gives_the_pre_d10_yaml(monkeypatch):
    """With no row in VISUAL_REVIEWED the tool writes the YAML as committed before the
    D10 check (a82c97209487), byte for byte; the set adds human lines and nothing else."""
    import subprocess
    before = subprocess.run(["git", "show", "a82c97209487:kb/sign_catalog_meaning.yaml"],
                            cwd=dcr.ROOT, capture_output=True, check=True).stdout.decode("utf-8")
    listed = set(dcr.VISUAL_REVIEWED)
    monkeypatch.setattr(dcr, "FULL_REVIEW", False)         # before the owner's full review (2026-11-27)
    monkeypatch.setattr(dcr, "VISUAL_REVIEWED", set())
    text = dcr.to_yaml(dcr.draft_rows())
    assert "visual_reviewed_by: human" not in text
    if not listed:
        assert text == before
    monkeypatch.setattr(dcr, "VISUAL_REVIEWED", listed)
    assert dcr.to_yaml(dcr.draft_rows()).count("visual_reviewed_by: human") == len(listed)


def test_the_full_review_marks_every_row_human():
    """The owner's full review (2026-11-27): every meaning row is human-checked, name and look."""
    text = dcr.OUT.read_text(encoding="utf-8")
    n = text.count("\n  - code: ")
    assert text.count("    reviewed_by: human") == n and text.count("    visual_reviewed_by: human") == n
    assert "reviewed_by: none" not in text and "visual_reviewed_by: assistant" not in text


def test_visual_reviewed_writes_human_over_the_overrides_assistant(monkeypatch):
    monkeypatch.setattr(dcr, "FULL_REVIEW", False)
    rows = dcr.draft_rows()
    monkeypatch.setattr(dcr, "VISUAL_REVIEWED", {"IE.471", "W.201b"})
    text = dcr.to_yaml(rows)

    def block(code):
        start = text.index(f"  - code: {code}\n")
        return text[start:text.index("\n\n", start)]
    assert "visual_reviewed_by: human" in block("IE.471")          # was assistant (override)
    assert "visual_reviewed_by: assistant" not in block("IE.471")
    assert "background: yellow" in block("IE.471")                 # the override still applies
    assert "visual_reviewed_by: human" in block("W.201b")          # family default look
    assert "visual_reviewed_by: assistant" in block("IE.473")      # untouched rows keep theirs
