# Item 1: a profile over PROFILE_MAX_CHARS must trigger the existing
# retry path (validate_profile_selection -> write_profile), never a
# silent truncation to exactly the limit.

from unittest.mock import patch

from cv.schema import PROFILE_MAX_CHARS
from cv.selector import ProfileSelection, validate_profile_selection, write_profile
from models.jd_schema import ParsedJD


def _profile_selection(text: str) -> ProfileSelection:
    return ProfileSelection(profile_evidence=[], profile=text)


def test_over_limit_profile_has_no_hard_max_length_on_the_field():
    # A ProfileSelection over PROFILE_MAX_CHARS must construct without
    # error -- there is no schema-level max_length left to enforce a
    # silent cut. (If this raised a pydantic ValidationError, the hard
    # slice would still be in place.)
    text = "x" * (PROFILE_MAX_CHARS + 5)
    profile = _profile_selection(text)

    assert len(profile.profile) == PROFILE_MAX_CHARS + 5


def test_over_limit_profile_is_rejected_by_validation(facts):
    jd = ParsedJD()
    profile = _profile_selection("x" * (PROFILE_MAX_CHARS + 5))

    errors = validate_profile_selection(profile, facts, jd, valid_ids=set())

    assert any("over the" in error and "char limit" in error for error in errors)


def test_write_profile_retries_once_after_an_over_limit_profile(facts):
    """
    First model response is 325 characters -- over the 320 limit. The
    retry (fed the specific violation) returns a clean, in-limit profile.
    write_profile must retry exactly once and return the clean result,
    not a truncated version of the first one.
    """

    jd = ParsedJD()
    valid_ids = {"exp.acme.b1", "proj.widget-analyzer"}

    too_long = ProfileSelection(
        profile_evidence=["exp.acme.b1", "proj.widget-analyzer"],
        profile="Built a Widget Analyzer at Acme Corp. " * 10,  # well over 320 chars
    )
    good = ProfileSelection(
        profile_evidence=["exp.acme.b1", "proj.widget-analyzer"],
        profile="I built a Widget Analyzer processing 1000 widgets per second at Acme Corp.",
    )

    responses = [too_long, good]

    def fake_call(content_block, jd_block, feedback, forced=False, top_ranked_evidence=None, requirement_coverage=None):
        return responses.pop(0)

    with patch("cv.selector._call_profile_writer", side_effect=fake_call) as mock_call:
        result = write_profile(facts, jd, "irrelevant content block", valid_ids)

    assert result is good
    assert mock_call.call_count == 2
    second_call_feedback = mock_call.call_args_list[1].args[2]
    assert "char limit" in second_call_feedback
