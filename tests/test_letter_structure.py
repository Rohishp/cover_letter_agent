# Phase J item 1: the letter has no closing and no signature unless
# Python appends them unconditionally during assembly, and a
# deterministic check backstops that invariant on the assembled text.

from unittest.mock import patch

from agents.cover_letter_writer import assemble_cover_letter, write_cover_letter
from control_plane.cover_letter_containment import CLOSING_LINE, check_letter_structure
from models.cover_letter_schema import CoverLetterDraft, CoverLetterParagraph
from models.jd_schema import ParsedJD
from models.match_schema import MatchAnalysis


def _draft(*paragraphs: CoverLetterParagraph) -> CoverLetterDraft:
    return CoverLetterDraft(paragraphs=list(paragraphs))


def test_assembly_always_appends_closing_and_name_regardless_of_draft_content(facts):
    # The draft's own paragraphs contain nothing closing-like -- assembly
    # must still produce a signed letter, not silently omit the sign-off.
    draft = _draft(
        CoverLetterParagraph(kind="connective", fact_ids=[], text="Dear Hiring Team,"),
        CoverLetterParagraph(
            kind="factual", fact_ids=["exp.acme.b1"], text="I did thing one with 42 widgets."
        ),
    )

    result = assemble_cover_letter(draft, facts)

    assert result.endswith(f"{CLOSING_LINE}\n{facts.personal.full_name}")


def test_check_letter_structure_fails_without_a_greeting(facts):
    draft = _draft(
        CoverLetterParagraph(
            kind="factual", fact_ids=["exp.acme.b1"], text="I did thing one with 42 widgets."
        ),
    )
    content = assemble_cover_letter(draft, facts)

    violations = check_letter_structure(content, draft, facts)

    assert any("greeting" in v for v in violations)


def test_check_letter_structure_fails_without_any_factual_paragraph(facts):
    draft = _draft(
        CoverLetterParagraph(kind="connective", fact_ids=[], text="Dear Hiring Team,"),
        CoverLetterParagraph(kind="connective", fact_ids=[], text="I look forward to hearing from you."),
    )
    content = assemble_cover_letter(draft, facts)

    violations = check_letter_structure(content, draft, facts)

    assert any("factual" in v for v in violations)


def test_check_letter_structure_passes_a_well_formed_letter(facts):
    draft = _draft(
        CoverLetterParagraph(kind="connective", fact_ids=[], text="Dear Hiring Team,"),
        CoverLetterParagraph(
            kind="factual", fact_ids=["exp.acme.b1"], text="I did thing one with 42 widgets."
        ),
    )
    content = assemble_cover_letter(draft, facts)

    assert check_letter_structure(content, draft, facts) == []


def test_write_cover_letter_retries_when_greeting_is_missing(facts):
    missing_greeting = _draft(
        CoverLetterParagraph(
            kind="factual", fact_ids=["exp.acme.b1"], text="I did thing one with 42 widgets."
        ),
    )
    good = _draft(
        CoverLetterParagraph(kind="connective", fact_ids=[], text="Dear Hiring Team,"),
        CoverLetterParagraph(
            kind="factual", fact_ids=["exp.acme.b1"], text="I did thing one with 42 widgets."
        ),
    )

    responses = [missing_greeting, good]

    def fake_call(**kwargs):
        return responses.pop(0)

    with patch("agents.cover_letter_writer._call_writer", side_effect=fake_call) as mock_call:
        result = write_cover_letter(
            facts,
            ParsedJD(company_name="Test Co"),
            MatchAnalysis(match_summary="Strong match."),
            applied_for_role="Data Engineer",
        )

    assert result.startswith("Dear Hiring Team,")
    assert result.endswith(f"{CLOSING_LINE}\n{facts.personal.full_name}")
    assert mock_call.call_count == 2
