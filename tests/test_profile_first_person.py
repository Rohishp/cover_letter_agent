# Item 3: the CV profile must be written in first person -- a deterministic
# check catches third-person candidate-referring phrasing and gates the
# profile-writer's retry loop, the same pattern as the banned-phrase check.

from unittest.mock import patch

from cv.checks import check_profile_first_person, find_third_person_phrases
from cv.schema import CVContent, EducationEntry
from cv.selector import ProfileSelection, validate_profile_selection, write_profile
from models.jd_schema import ParsedJD


def _content(profile: str) -> CVContent:
    return CVContent(
        full_name="Test Person",
        target_title="Test Title",
        location="Testville",
        contact_details=["test@example.com"],
        contact_links=[],
        profile=profile,
        skill_groups=[],
        experience=[],
        education=[
            EducationEntry(
                position="Degree", organisation="University", city="City",
                dates="2015 - 2018", bullets=[],
            )
        ],
        projects=[],
        certifications=[],
        languages=[],
        coursework=[],
    )


def test_third_person_profile_fails_the_check():
    content = _content(
        "This candidate has strong Python skills and their experience spans "
        "several AI projects."
    )

    check_id, passed, detail = check_profile_first_person(None, content=content)

    assert check_id == "profile_first_person"
    assert passed is False
    assert "this candidate" in detail


def test_first_person_profile_passes_the_check():
    content = _content(
        "I built several AI projects using Python and have strong hands-on "
        "experience shipping them to production."
    )

    check_id, passed, detail = check_profile_first_person(None, content=content)

    assert check_id == "profile_first_person"
    assert passed is True
    assert detail == "clean"


def test_find_third_person_phrases_is_case_insensitive():
    assert find_third_person_phrases("THE CANDIDATE excels at this.") == ["the candidate"]
    assert find_third_person_phrases("I excel at this.") == []


def _profile_selection(text: str) -> ProfileSelection:
    return ProfileSelection(profile_evidence=[], profile=text)


def test_third_person_profile_is_rejected_by_validation(facts):
    jd = ParsedJD()
    profile = _profile_selection("This candidate delivered strong results at Acme Corp.")

    errors = validate_profile_selection(profile, facts, jd, valid_ids=set())

    assert any("third-person candidate language" in error for error in errors)


def test_write_profile_retries_once_after_third_person_phrasing(facts):
    jd = ParsedJD()
    valid_ids = {"exp.acme.b1"}

    bad = ProfileSelection(
        profile_evidence=["exp.acme.b1"],
        profile="This candidate has hands-on experience with widgets.",
    )
    good = ProfileSelection(
        profile_evidence=["exp.acme.b1"],
        profile="I have hands-on experience with widgets.",
    )

    responses = [bad, good]

    def fake_call(content_block, jd_block, feedback, forced=False, top_ranked_evidence=None, requirement_coverage=None):
        return responses.pop(0)

    with patch("cv.selector._call_profile_writer", side_effect=fake_call) as mock_call:
        result = write_profile(facts, jd, "irrelevant content block", valid_ids)

    assert result is good
    assert mock_call.call_count == 2
    second_call_feedback = mock_call.call_args_list[1].args[2]
    assert "third-person candidate language" in second_call_feedback
