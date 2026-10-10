# Phase J item 4: unblocks the BCG Platinion failure -- the writer cited
# fact_id "languages", a section-level ID this scheme never provides
# (only per-language IDs like "lang.english" exist). Root cause was two
# things: _render_facts_with_ids omitted bracketed IDs for certifications
# and languages entirely (fixed directly), and the retry feedback never
# told the model what the valid IDs actually were (fixed by threading
# facts.all_ids() through and appending it explicitly on citation
# failures).

from unittest.mock import patch

from agents.cover_letter_writer import write_cover_letter
from models.cover_letter_schema import CoverLetterDraft, CoverLetterParagraph
from models.jd_schema import ParsedJD
from models.match_schema import MatchAnalysis


def _draft(*paragraphs: CoverLetterParagraph) -> CoverLetterDraft:
    return CoverLetterDraft(paragraphs=list(paragraphs))


def test_draft_citing_languages_fails_and_retry_context_lists_valid_language_ids(facts):
    invalid = _draft(
        CoverLetterParagraph(kind="connective", fact_ids=[], text="Dear Hiring Team,"),
        CoverLetterParagraph(
            kind="factual", fact_ids=["languages"], text="I am fluent in English."
        ),
    )
    good = _draft(
        CoverLetterParagraph(kind="connective", fact_ids=[], text="Dear Hiring Team,"),
        CoverLetterParagraph(
            kind="factual", fact_ids=["lang.english"], text="I am fluent in English."
        ),
    )

    responses = [invalid, good]

    def fake_call(**kwargs):
        return responses.pop(0)

    with patch("agents.cover_letter_writer._call_writer", side_effect=fake_call) as mock_call:
        result = write_cover_letter(
            facts,
            ParsedJD(company_name="Test Co"),
            MatchAnalysis(match_summary="Strong match."),
            applied_for_role="Data Engineer",
        )

    assert "I am fluent in English." in result
    assert mock_call.call_count == 2

    second_call_grounding_feedback = mock_call.call_args_list[1].kwargs["grounding_feedback"]
    assert "languages" in second_call_grounding_feedback
    assert "lang.english" in second_call_grounding_feedback


def test_system_prompt_states_the_full_valid_id_list_and_warns_off_section_level_ids(facts):
    from agents.cover_letter_writer import _system_prompt

    valid_ids = facts.all_ids()
    prompt = _system_prompt(
        facts_block="irrelevant", known_organisations=[], real_held_titles=[], valid_ids=valid_ids
    )

    assert "lang.english" in prompt
    # The explicit warning that a bare section name is never a valid ID --
    # this is what the model needs to not invent "languages" again.
    assert '"languages"' in prompt


def test_render_facts_with_ids_shows_bracketed_ids_for_certifications_and_languages(facts):
    from cv.selector import _render_facts_with_ids

    block = _render_facts_with_ids(facts)

    assert "[lang.english]" in block
