# Phase F addendum 3, item 2: a letter must never volunteer a skill/tool
# gap, blunt or softened as forward-looking enthusiasm -- even one the
# deterministic match gate didn't find disqualifying. Genuine,
# self-contained enthusiasm that doesn't reference a specific missing
# skill must still pass. Phase H additionally grounds write_cover_letter
# in the CV fact base (CVFacts) instead of parsed_cv -- the pure check
# functions below are unchanged.

from unittest.mock import patch

from control_plane.cover_letter_containment import check_hedge_disclosure, find_hedge_phrases
from agents.cover_letter_writer import write_cover_letter
from models.cover_letter_schema import CoverLetterDraft, CoverLetterParagraph
from models.jd_schema import ParsedJD
from models.match_schema import MatchAnalysis


def test_literal_soft_hedge_sentence_fails():
    letter = (
        "While my AWS certification underscores my commitment to continuous learning, "
        "I am eager to expand my expertise in Azure AI and orchestration frameworks, "
        "aligning with Allianz Technology's technical environment."
    )

    violations = check_hedge_disclosure(letter)

    assert "eager to expand my expertise in" in violations


def test_blunt_hedge_fails():
    letter = "Although I lack direct experience with Kubernetes, I am confident I can learn quickly."

    violations = check_hedge_disclosure(letter)

    assert "although i lack" in violations


def test_genuine_enthusiasm_without_a_specific_gap_passes():
    letter = "I'm excited to bring these skills to your team and contribute from day one."

    violations = check_hedge_disclosure(letter)

    assert violations == []


def test_find_hedge_phrases_is_case_insensitive():
    assert find_hedge_phrases("I DON'T HAVE experience with that.") == ["i don't have"]


def test_eager_to_bring_existing_expertise_does_not_false_flag():
    """
    Real regression from a first, too-broad regex attempt (\\w+ verb):
    "eager to BRING my expertise in Python to your team" offers EXISTING
    strength, not a gap -- must not be caught by the same pattern that
    catches "eager to expand/leverage/develop my skills in X".
    """

    letter = "I am eager to bring my expertise in Python and AI development to your team."

    assert check_hedge_disclosure(letter) == []


def test_eager_to_leverage_construction_fails():
    """
    Real regression: "I am eager to leverage my skills in Azure AI and
    Databricks" -- the original phrase list only covered "expand",
    "develop", "build", not "leverage". Generalized to a regex covering
    any verb in this construction rather than enumerating one by one.
    """

    letter = (
        "While I have primarily worked with AWS, I am eager to leverage my skills "
        "in Azure AI and Databricks, as required by Allianz Technology."
    )

    violations = check_hedge_disclosure(letter)

    assert "eager to leverage my skills in" in violations


def test_have_not_yet_worked_with_construction_fails():
    """
    Real regression: "While I have not yet worked with Azure AI, my
    experience with AWS..." slipped through the original phrase list
    (which only covered "i haven't had"/"i have not had", not "yet").
    """

    letter = "While I have not yet worked with Azure AI, my experience with AWS positions me well."

    violations = check_hedge_disclosure(letter)

    assert violations != []


def test_worked_directly_with_construction_fails():
    """
    Phase J item 3: real shipped letter -- "While I have not worked
    directly with Azure AI or Databricks, my background in cloud and
    data technologies positions me well..." -- slipped through both the
    phrase list ("have not yet worked with"/"haven't worked with" both
    require strict adjacency) and every existing pattern. "directly"
    breaks the "worked with" adjacency every prior entry assumed.
    """

    letter = (
        "While I have not worked directly with Azure AI or Databricks, my "
        "background in cloud and data technologies positions me well to quickly "
        "adapt to these platforms and contribute effectively to Allianz "
        "Technology's projects."
    )

    violations = check_hedge_disclosure(letter)

    assert violations != []


def test_worked_closely_with_construction_also_fails():
    # A different inserted adverb -- proves the pattern is adverb-
    # tolerant, not a one-off fix for "directly" specifically.
    letter = "I haven't worked closely with Kubernetes before this role."

    assert check_hedge_disclosure(letter) != []


# --- write_cover_letter: structural retry (Phase H) -----------------------


def _jd() -> ParsedJD:
    return ParsedJD(company_name="Test Co")


def _match() -> MatchAnalysis:
    return MatchAnalysis(match_summary="Strong match.")


def _draft(*paragraphs: CoverLetterParagraph) -> CoverLetterDraft:
    return CoverLetterDraft(paragraphs=list(paragraphs))


def test_write_cover_letter_retries_once_after_a_hedge_phrase(facts):
    bad = _draft(
        CoverLetterParagraph(kind="connective", fact_ids=[], text="Dear Hiring Team,"),
        CoverLetterParagraph(
            kind="factual",
            fact_ids=["exp.acme.b1"],
            text="I am eager to expand my expertise in Azure AI, aligning with your environment.",
        ),
    )
    good = _draft(
        CoverLetterParagraph(kind="connective", fact_ids=[], text="Dear Hiring Team,"),
        CoverLetterParagraph(
            kind="factual",
            fact_ids=["exp.acme.b1"],
            text="I handled 42 widgets, and that Python and cloud experience aligns well with your technical environment.",
        ),
    )

    responses = [bad, good]

    def fake_call(**kwargs):
        return responses.pop(0)

    with patch("agents.cover_letter_writer._call_writer", side_effect=fake_call) as mock_call:
        result = write_cover_letter(facts, _jd(), _match(), applied_for_role="Data Engineer")

    assert good.paragraphs[1].text in result
    assert result.endswith(f"Best regards,\n{facts.personal.full_name}")
    assert mock_call.call_count == 2
    second_call_grounding_feedback = mock_call.call_args_list[1].kwargs["grounding_feedback"]
    assert "eager to expand my expertise in" in second_call_grounding_feedback


def test_hedge_check_always_runs_alongside_the_employer_check(facts):
    """
    Unlike the (now internally-computed) known_organisations, the hedge
    check has no fact-base dependency of its own -- it must run on every
    call, with no way to opt out.
    """

    bad = _draft(
        CoverLetterParagraph(kind="connective", fact_ids=[], text="Dear Hiring Team,"),
        CoverLetterParagraph(
            kind="factual",
            fact_ids=["exp.acme.b1"],
            text="I am eager to expand my expertise in Azure AI for this role.",
        ),
    )
    good = _draft(
        CoverLetterParagraph(kind="connective", fact_ids=[], text="Dear Hiring Team,"),
        CoverLetterParagraph(
            kind="factual",
            fact_ids=["exp.acme.b1"],
            text="I handled 42 widgets, and that Python and cloud experience aligns well with your technical environment.",
        ),
    )

    responses = [bad, good]

    def fake_call(**kwargs):
        return responses.pop(0)

    with patch("agents.cover_letter_writer._call_writer", side_effect=fake_call) as mock_call:
        result = write_cover_letter(facts, _jd(), _match(), applied_for_role="Data Engineer")

    assert good.paragraphs[1].text in result
    assert mock_call.call_count == 2
