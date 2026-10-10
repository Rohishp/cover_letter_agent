# Phase H item 2: the CV path's own pattern (evidences_requirement,
# validated against real fields) applied to the letter -- every factual
# paragraph must cite a real fact_id; an unciteable claim is a hard fail.
# Mandatory regression: the literal fabricated sentence from three real
# runs must be structurally impossible to accept.

from agents.cover_letter_writer import validate_cover_letter_draft
from models.cover_letter_schema import CoverLetterDraft, CoverLetterParagraph


KNOWN_ORGANISATIONS = ["Acme Corp", "Beta Inc"]


def _draft(*paragraphs: CoverLetterParagraph) -> CoverLetterDraft:
    return CoverLetterDraft(paragraphs=list(paragraphs))


def test_factual_paragraph_with_a_real_fact_id_passes(facts):
    draft = _draft(
        CoverLetterParagraph(
            kind="factual", fact_ids=["exp.acme.b1"], text="I did thing one with 42 widgets.",
        ),
    )

    errors = validate_cover_letter_draft(draft, facts, KNOWN_ORGANISATIONS)

    assert errors == []


def test_factual_paragraph_with_no_fact_ids_fails(facts):
    draft = _draft(
        CoverLetterParagraph(kind="factual", fact_ids=[], text="I did great things."),
    )

    errors = validate_cover_letter_draft(draft, facts, KNOWN_ORGANISATIONS)

    assert any("cites no fact_ids" in error for error in errors)


def test_factual_paragraph_with_an_unknown_fact_id_fails(facts):
    draft = _draft(
        CoverLetterParagraph(
            kind="factual", fact_ids=["proj.does-not-exist"], text="I built something.",
        ),
    )

    errors = validate_cover_letter_draft(draft, facts, KNOWN_ORGANISATIONS)

    assert any("unknown fact_id" in error and "proj.does-not-exist" in error for error in errors)


def test_connective_paragraph_needs_no_fact_ids(facts):
    draft = _draft(
        CoverLetterParagraph(kind="connective", fact_ids=[], text="Dear Hiring Team,"),
    )

    errors = validate_cover_letter_draft(draft, facts, KNOWN_ORGANISATIONS)

    assert errors == []


def test_the_literal_regression_sentence_is_rejected(facts):
    """
    Mandatory regression (Phase H): the literal fabricated sentence from
    a real run must be impossible to accept. It names no organisation at
    all -- "my role as an AI Engineer" -- so the employer-pattern check
    alone can't catch it; this is a fabricated HELD ROLE claim, caught by
    check_fabricated_role_claim against the real closed list of titles.
    """

    literal_sentence = (
        "My role as an AI Engineer involved designing and deploying agentic AI "
        "systems using Python, OpenAI Agents SDK, and RAG architectures."
    )
    real_held_titles = ["Senior Thing Doer", "Junior Thing Doer"]

    # Even if the model cites a real, valid, but unrelated fact_id --
    # citation validation alone must not be fooled.
    draft = _draft(
        CoverLetterParagraph(kind="factual", fact_ids=["exp.acme.b1"], text=literal_sentence),
    )

    errors = validate_cover_letter_draft(draft, facts, KNOWN_ORGANISATIONS, real_held_titles)

    assert any("AI Engineer" in error and "held role" in error for error in errors)


def test_backstop_catches_a_fabricated_employer_even_in_a_connective_paragraph(facts):
    """
    A connective paragraph should never make a factual claim at all, but
    if one sneaks a role-at-organisation claim in anyway, the regex
    backstop still catches it regardless of kind.
    """

    draft = _draft(
        CoverLetterParagraph(
            kind="connective", fact_ids=[],
            text="At Agentic AI, I led the design of several agentic systems.",
        ),
    )

    errors = validate_cover_letter_draft(draft, facts, KNOWN_ORGANISATIONS)

    assert any("Agentic AI" in error for error in errors)
