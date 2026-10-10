# Item 4 (Phase E.1) + Phase H: a targeted, hard-fail check for a claimed
# "<role> at/with/for <Organisation>" construction whose organisation
# isn't a real, closed-list employer/institution. Phase H additionally
# grounds write_cover_letter in the CV fact base (CVFacts) instead of
# parsed_cv -- the pure check functions below are unchanged.

from unittest.mock import patch

from control_plane.cover_letter_containment import (
    check_fabricated_employer,
    find_position_at_organisation_claims,
)
from agents.cover_letter_writer import write_cover_letter
from models.cover_letter_schema import CoverLetterDraft, CoverLetterParagraph
from models.jd_schema import ParsedJD
from models.match_schema import MatchAnalysis


KNOWN_ORGANISATIONS = ["Robert Bosch GmbH", "Chemnitz University of Technology"]


def test_real_employer_reference_passes():
    letter = "I worked as a Data Science Intern at Robert Bosch GmbH on manufacturing data."

    violations = check_fabricated_employer(letter, KNOWN_ORGANISATIONS)

    assert violations == []


def test_fabricated_position_at_organisation_fails():
    letter = "My background as an AI Engineer at Agentic AI, where I designed agents."

    violations = check_fabricated_employer(letter, KNOWN_ORGANISATIONS)

    assert "Agentic AI" in violations


def test_find_position_at_organisation_claims_extracts_agentic_ai():
    letter = "My background as an AI Engineer at Agentic AI, where I designed agents."

    claims = find_position_at_organisation_claims(letter)

    assert "Agentic AI" in claims


def test_real_education_institution_reference_passes():
    letter = "As a Researcher with Chemnitz University of Technology, I studied optimisation."

    violations = check_fabricated_employer(letter, KNOWN_ORGANISATIONS)

    assert violations == []


def test_org_led_clause_without_a_role_word_still_fails():
    """
    Real regression: a generated letter used "At Agentic AI, I was deeply
    involved..." -- no role word before "At" at all, so the role-word
    pattern alone missed it entirely on a live run.
    """

    letter = (
        "My background in AI engineering aligns well with this role. "
        "At Agentic AI, I was deeply involved in building agentic systems."
    )

    violations = check_fabricated_employer(letter, KNOWN_ORGANISATIONS)

    assert "Agentic AI" in violations


def test_org_led_clause_at_the_very_start_of_the_letter_still_fails():
    letter = "At Agentic AI, I led the design of several agentic systems."

    violations = check_fabricated_employer(letter, KNOWN_ORGANISATIONS)

    assert "Agentic AI" in violations


def test_org_led_clause_for_a_real_employer_passes():
    letter = "At Robert Bosch GmbH, I built automated data-quality workflows."

    violations = check_fabricated_employer(letter, KNOWN_ORGANISATIONS)

    assert violations == []


def test_org_led_clause_naming_the_target_company_does_not_false_flag():
    """
    "At Acme Corp, I would bring..." is aspirational (talking about the
    role being applied to), not an employer-history claim -- it must not
    be flagged just because the target company isn't a past employer, as
    long as the caller (apply.py) included it in known_organisations.
    """

    known_with_target_company = [*KNOWN_ORGANISATIONS, "Acme Corp"]
    letter = "At Acme Corp, I would bring my technical acumen to shaping AI products."

    violations = check_fabricated_employer(letter, known_with_target_company)

    assert violations == []


def test_org_led_clause_naming_the_target_company_flags_without_the_guard():
    """
    Same construction, but without the target company in
    known_organisations -- confirms the guard above is actually doing
    something, not just a coincidence of the regex not matching.
    """

    letter = "At Acme Corp, I would bring my technical acumen to shaping AI products."

    violations = check_fabricated_employer(letter, KNOWN_ORGANISATIONS)

    assert "Acme Corp" in violations


# --- write_cover_letter: structural retry (Phase H) -----------------------


def _jd() -> ParsedJD:
    return ParsedJD(company_name="Test Co")


def _match() -> MatchAnalysis:
    return MatchAnalysis(match_summary="Strong match.")


def _draft(*paragraphs: CoverLetterParagraph) -> CoverLetterDraft:
    return CoverLetterDraft(paragraphs=list(paragraphs))


def test_write_cover_letter_retries_once_after_a_fabricated_employer(facts):
    """
    First model response fabricates "Agentic AI"; the retry (fed the
    specific violation) returns a letter using only real organisations.
    write_cover_letter must retry exactly once and return the clean
    result, assembled from the validated paragraphs.
    """

    bad = _draft(
        CoverLetterParagraph(kind="connective", text="Dear Hiring Team,"),
        CoverLetterParagraph(
            kind="factual",
            fact_ids=["exp.acme.b1"],
            text="My background as an AI Engineer at Agentic AI shaped my approach.",
        ),
    )
    good = _draft(
        CoverLetterParagraph(kind="connective", text="Dear Hiring Team,"),
        CoverLetterParagraph(
            kind="factual",
            fact_ids=["exp.acme.b1"],
            text="My background as a Senior Thing Doer at Acme Corp shaped my approach.",
        ),
    )

    responses = [bad, good]

    def fake_call(**kwargs):
        return responses.pop(0)

    with patch("agents.cover_letter_writer._call_writer", side_effect=fake_call) as mock_call:
        result = write_cover_letter(facts, _jd(), _match(), applied_for_role="AI Engineer")

    assert "Acme Corp" in result
    assert "Agentic AI" not in result
    assert mock_call.call_count == 2
    second_call_grounding_feedback = mock_call.call_args_list[1].kwargs["grounding_feedback"]
    assert "Agentic AI" in second_call_grounding_feedback


def test_write_cover_letter_raises_after_max_attempts_if_still_fabricating(facts):
    bad = _draft(
        CoverLetterParagraph(
            kind="factual",
            fact_ids=["exp.acme.b1"],
            text="My background as an AI Engineer at Agentic AI shaped my approach.",
        ),
    )

    with patch("agents.cover_letter_writer._call_writer", return_value=bad) as mock_call:
        try:
            write_cover_letter(facts, _jd(), _match(), applied_for_role="AI Engineer")
            assert False, "expected a ValueError"
        except ValueError as error:
            assert "Agentic AI" in str(error)

    from agents.cover_letter_writer import MAX_ATTEMPTS

    assert mock_call.call_count == MAX_ATTEMPTS
