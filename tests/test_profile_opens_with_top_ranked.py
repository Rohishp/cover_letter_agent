# Phase F addendum 3, item 1: the profile must OPEN with the top-ranked
# evidence, not just include it somewhere. A fixture where item A
# outranks item B: a profile opening with B must fail; one opening with A
# must pass.

from unittest.mock import patch

from cv.checks import first_sentence, profile_opens_with
from cv.selection_rules import top_ranked_project_name
from cv.selector import (
    CVSelection,
    ItemRank,
    ProfileSelection,
    validate_profile_selection,
    write_profile,
)
from models.jd_schema import ParsedJD


def _selection(top_project_id: str) -> CVSelection:
    return CVSelection(
        section_order_reason="test",
        section_order=["skills", "experience", "projects", "education"],
        bullet_ranks=[],
        project_ranks=[ItemRank(id=top_project_id, rank=1)],
        skill_group_ranks=[],
        target_title="Test Title",
    )


def test_first_sentence_extracts_up_to_the_first_terminator():
    assert first_sentence("First one. Second one. Third.") == "First one. "
    assert first_sentence("Only one sentence") == "Only one sentence"


def test_profile_opens_with_true_when_label_in_first_sentence():
    profile = "I built the Widget Analyzer to process real-time data. It also does other things."
    assert profile_opens_with(profile, "Widget Analyzer") is True


def test_profile_opens_with_false_when_label_only_in_later_sentence():
    profile = "I have a strong ML background. I also built the Widget Analyzer."
    assert profile_opens_with(profile, "Widget Analyzer") is False


def test_profile_opens_with_true_when_no_label_given():
    assert profile_opens_with("Anything at all.", None) is True
    assert profile_opens_with("Anything at all.", "") is True


def test_top_ranked_project_name_returns_the_rank_one_projects_name(facts):
    selection = _selection("proj.widget-analyzer")

    assert top_ranked_project_name(facts, selection) == "Widget Analyzer"


def test_validate_profile_selection_rejects_a_profile_that_buries_the_top_project(facts):
    jd = ParsedJD()
    profile = ProfileSelection(
        profile_evidence=[],
        profile="I have strong evaluation skills. I also built the Widget Analyzer.",
    )

    errors = validate_profile_selection(
        profile, facts, jd, valid_ids=set(), top_ranked_opening_label="Widget Analyzer",
    )

    assert any("does not open with the top-ranked evidence" in error for error in errors)


def test_validate_profile_selection_accepts_a_profile_that_opens_with_the_top_project(facts):
    jd = ParsedJD()
    profile = ProfileSelection(
        profile_evidence=[],
        profile="I built the Widget Analyzer to process real-time data.",
    )

    errors = validate_profile_selection(
        profile, facts, jd, valid_ids=set(), top_ranked_opening_label="Widget Analyzer",
    )

    assert not any("does not open with the top-ranked evidence" in error for error in errors)


def test_write_profile_retries_once_when_the_opening_buries_the_top_evidence(facts):
    jd = ParsedJD()

    buried = ProfileSelection(
        profile_evidence=["proj.widget-analyzer"],
        profile="I have strong evaluation skills. I also built the Widget Analyzer.",
    )
    leads = ProfileSelection(
        profile_evidence=["proj.widget-analyzer"],
        profile="I built the Widget Analyzer to process real-time data.",
    )

    responses = [buried, leads]

    def fake_call(content_block, jd_block, feedback, forced=False, top_ranked_evidence=None, requirement_coverage=None):
        return responses.pop(0)

    with patch("cv.selector._call_profile_writer", side_effect=fake_call) as mock_call:
        result = write_profile(
            facts, jd, "irrelevant content block", {"proj.widget-analyzer"},
            top_ranked_opening_label="Widget Analyzer",
        )

    assert result is leads
    assert mock_call.call_count == 2
    second_call_feedback = mock_call.call_args_list[1].args[2]
    assert "does not open with the top-ranked evidence" in second_call_feedback
