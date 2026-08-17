# The LLM is mocked throughout: CVSelection objects are built by hand.

import pytest

from cv.checks import convert_to_pdf
from cv.density_floor import FIGURE_DENSITY_FLOOR, _normalize, _try_one_swap, enforce_figure_density_floor
from cv.selection_rules import PROFILE_PLACEHOLDER, SelectionState, initial_state
from cv.selector import CVSelection, ItemRank
from models.jd_schema import ParsedJD


def _pdf_available() -> bool:
    import tempfile
    from pathlib import Path

    from docx import Document

    with tempfile.TemporaryDirectory() as tmp:
        docx_path = Path(tmp) / "probe.docx"
        Document().save(str(docx_path))
        pdf_path, _detail = convert_to_pdf(docx_path)
        return pdf_path is not None


def _skip_without_pdf_converter():
    if not _pdf_available():
        pytest.skip("no PDF converter (MS Word/LibreOffice) available")


def _empty_selection(**overrides) -> CVSelection:
    base = dict(
        section_order_reason="test",
        section_order=["skills", "experience", "projects", "education"],
        bullet_ranks=[],
        project_ranks=[],
        skill_group_ranks=[],
        target_title="Test Title",
    )
    base.update(overrides)
    return CVSelection(**base)


def test_swap_replaces_worst_kept_non_figure_bullet_with_dropped_figure_bullet(facts):
    # Acme's bullets, in order: b1 "...42 widgets." (digit), b2 "Did
    # thing two." b3 "...10x speedup." (digit), b4 "Did thing four.",
    # b5 "Did thing five.", b6 "Did thing six.". Rank b1 (digit) worst
    # so it's the one bullet dropped under cap=5; b6 is the worst-ranked
    # among the five non-digit-or-already-kept bullets.
    selection = _empty_selection(
        bullet_ranks=[
            ItemRank(id="exp.acme.b2", rank=1),
            ItemRank(id="exp.acme.b4", rank=2),
            ItemRank(id="exp.acme.b5", rank=3),
            ItemRank(id="exp.acme.b6", rank=4),   # worst-ranked kept, no digit
            ItemRank(id="exp.acme.b3", rank=10),  # kept (has a digit, so the
                                                   # bonus keeps it in-budget)
            ItemRank(id="exp.acme.b1", rank=11),  # dropped, has a digit
        ],
    )

    state = SelectionState(
        project_ids=[],
        skill_group_ids=[],
        bullet_caps={"exp.acme": 5},
    )

    page1_text = _normalize("Did thing six.")

    swapped = _try_one_swap(facts, selection, state, page1_text)

    assert swapped is True
    assert state.bullet_overrides["exp.acme"] == [
        "Did thing one with 42 widgets.",
        "Did thing two.",
        "Did thing three with 10x speedup.",
        "Did thing four.",
        "Did thing five.",
    ]


def test_swap_returns_false_when_no_dropped_figure_bullet_exists(facts):
    # Beta's 3 bullets are all kept (cap == total), so nothing is dropped
    # at all -- no swap is possible regardless of page-1 content.
    selection = _empty_selection()

    state = SelectionState(
        project_ids=[],
        skill_group_ids=[],
        bullet_caps={"exp.beta": 3},
    )

    page1_text = _normalize("Helped with thing A. Helped with thing B.")

    assert _try_one_swap(facts, selection, state, page1_text) is False
    assert state.bullet_overrides == {}


def test_swap_returns_false_when_no_kept_bullet_is_on_page1(facts):
    selection = _empty_selection(
        bullet_ranks=[ItemRank(id=f"exp.acme.b{i}", rank=i) for i in range(1, 7)],
    )

    state = SelectionState(
        project_ids=[],
        skill_group_ids=[],
        bullet_caps={"exp.acme": 5},
    )

    # Page 1 contains none of the kept bullets' text.
    page1_text = _normalize("Something completely unrelated to any bullet.")

    assert _try_one_swap(facts, selection, state, page1_text) is False


def test_enforce_figure_density_floor_improves_or_meets_floor(facts, tmp_path):
    _skip_without_pdf_converter()

    # Rank the non-digit bullet best and the digit bullet worst so the
    # naive (bonus-free) selection would favor the non-digit one, forcing
    # the floor mechanism to do real work via swaps.
    selection = _empty_selection(
        bullet_ranks=[
            ItemRank(id="exp.acme.b2", rank=1),   # "Did thing two." (no digit)
            ItemRank(id="exp.acme.b4", rank=2),   # "Did thing four." (no digit)
            ItemRank(id="exp.acme.b5", rank=3),   # "Did thing five." (no digit)
            ItemRank(id="exp.acme.b6", rank=4),   # "Did thing six." (no digit)
            ItemRank(id="exp.acme.b1", rank=100), # "...42 widgets." (digit) -- ranked worst
            ItemRank(id="exp.acme.b3", rank=101), # "...10x speedup." (digit) -- ranked worst
        ],
    )

    state, _report = initial_state(facts, selection, ParsedJD())

    result = enforce_figure_density_floor(
        facts, ParsedJD(), selection, state, PROFILE_PLACEHOLDER, tmp_path / "density.docx"
    )

    assert result.density_after >= result.density_before
    assert result.density_after >= FIGURE_DENSITY_FLOOR or result.swap_count > 0
