# Phase F item 1: the profile writer must be given the same top-ranked
# evidence the cover letter already receives (top_ranked_project_text /
# top_ranked_experience_bullet_text), and the prompt actually sent to the
# model must include it -- not just that the helper functions compute the
# right text in isolation.

from unittest.mock import patch

from cv.selection_rules import (
    top_ranked_evidence_block,
    top_ranked_experience_bullet_text,
    top_ranked_project_text,
)
from cv.selector import CVSelection, ItemRank, ProfileSelection, write_profile
from models.jd_schema import ParsedJD


def _selection(**overrides) -> CVSelection:
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


def test_top_ranked_experience_bullet_text_finds_the_best_experience_bullet(facts):
    selection = _selection(
        bullet_ranks=[
            ItemRank(id="exp.acme.b1", rank=5),
            ItemRank(id="exp.acme.b3", rank=1),
        ],
    )

    text = top_ranked_experience_bullet_text(facts, selection)

    assert text == "Did thing three with 10x speedup."


def test_top_ranked_experience_bullet_text_ignores_project_and_education_bullets(facts):
    # Rank 1 belongs to a project bullet, not an experience bullet -- the
    # function must still return the best *experience* bullet, not None
    # and not the project bullet.
    selection = _selection(
        project_ranks=[ItemRank(id="proj.widget-analyzer", rank=1)],
        bullet_ranks=[
            ItemRank(id="proj.widget-analyzer.b1", rank=1),
            ItemRank(id="exp.acme.b2", rank=3),
        ],
    )

    text = top_ranked_experience_bullet_text(facts, selection)

    assert text == "Did thing two."


def test_top_ranked_evidence_block_combines_project_and_bullet(facts):
    selection = _selection(
        project_ranks=[ItemRank(id="proj.widget-analyzer", rank=1)],
        bullet_ranks=[ItemRank(id="exp.acme.b1", rank=1)],
    )

    block = top_ranked_evidence_block(facts, selection)

    assert "Widget Analyzer" in block
    assert "Did thing one with 42 widgets." in block
    assert block == (
        f"Top-ranked project: {top_ranked_project_text(facts, selection)}\n"
        f"Top-ranked experience evidence: {top_ranked_experience_bullet_text(facts, selection)}"
    )


def test_top_ranked_evidence_block_is_none_with_nothing_ranked(facts):
    selection = _selection()

    assert top_ranked_evidence_block(facts, selection) is None


def test_write_profile_includes_top_ranked_evidence_in_the_prompt(facts):
    """
    The prompt actually sent to the model must contain the top-ranked
    evidence text -- not just that the helper computes it correctly.
    """

    jd = ParsedJD()
    good = ProfileSelection(
        profile_evidence=["proj.widget-analyzer", "exp.acme"],
        profile="I built a Widget Analyzer at Acme Corp.",
    )

    captured = {}

    def fake_call(content_block, jd_block, feedback, forced=False, top_ranked_evidence=None, requirement_coverage=None):
        captured["top_ranked_evidence"] = top_ranked_evidence
        return good

    with patch("cv.selector._call_profile_writer", side_effect=fake_call):
        write_profile(
            facts, jd, "irrelevant content block", {"proj.widget-analyzer", "exp.acme"},
            top_ranked_evidence="Top-ranked project: Widget Analyzer, a real standout.",
        )

    assert captured["top_ranked_evidence"] == "Top-ranked project: Widget Analyzer, a real standout."


def test_write_profile_without_top_ranked_evidence_passes_none(facts):
    jd = ParsedJD()
    good = ProfileSelection(
        profile_evidence=["proj.widget-analyzer", "exp.acme"],
        profile="I built a Widget Analyzer at Acme Corp.",
    )

    captured = {}

    def fake_call(content_block, jd_block, feedback, forced=False, top_ranked_evidence=None, requirement_coverage=None):
        captured["top_ranked_evidence"] = top_ranked_evidence
        return good

    with patch("cv.selector._call_profile_writer", side_effect=fake_call):
        write_profile(facts, jd, "irrelevant content block", {"proj.widget-analyzer", "exp.acme"})

    assert captured["top_ranked_evidence"] is None
