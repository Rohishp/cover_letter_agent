# Item 6: the CV selection's top-ranked project should reach the cover
# letter writer as explicit guidance, so the two documents don't lead with
# different "strongest" evidence.

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from cv.facts import (
    CVFacts,
    Certifications,
    Coursework,
    Education,
    Extras,
    LanguageFact,
    Languages,
    Meta,
    Personal,
    ProjectFact,
    Projects,
    Skills,
    WorkExperience,
)
from cv.selection_rules import top_ranked_project_text
from cv.selector import CVSelection, ItemRank
from models.jd_schema import ParsedJD
from models.match_schema import MatchAnalysis


@pytest.fixture
def two_project_facts() -> CVFacts:
    return CVFacts(
        meta=Meta(updated=date(2026, 1, 1), owner="Test Person"),
        personal=Personal(
            full_name="Test Person", location="Testville", email="test@example.com",
            phone="+1 555 0000", linkedin="https://www.linkedin.com/in/testperson",
            github="https://github.com/testperson", photo="exclude",
        ),
        languages=Languages(tier=1, entries=[LanguageFact(language="English", level="C1")]),
        education=Education(tier=1, entries=[]),
        work_experience=WorkExperience(tier=1, entries=[]),
        projects=Projects(
            tier=2,
            entries=[
                ProjectFact(
                    name="PR Review Agent", dates="2026", status="complete", tools="Python",
                    intro="Reviews pull requests using repo history.",
                    bullets=["Ran a four-arm controlled experiment on a held-out set."],
                ),
                ProjectFact(
                    name="Minor Side Project", dates="2025", status="complete", tools="Python",
                    intro="A smaller project.",
                    bullets=["Did a small thing."],
                ),
            ],
        ),
        certifications=Certifications(tier=1, entries=[]),
        skills=Skills(groups=[]),
        coursework=Coursework(tier=3, include_when="", exclude_when="", render_as="bullet_list", items=[]),
        extras=Extras(awards=[], volunteering=[]),
    )


def _selection(top_project_id: str) -> CVSelection:
    return CVSelection(
        section_order_reason="test",
        section_order=["skills", "experience", "projects", "education"],
        bullet_ranks=[],
        project_ranks=[
            ItemRank(id=top_project_id, rank=1),
        ],
        skill_group_ranks=[],
        target_title="Test Title",
    )


def test_top_ranked_project_text_returns_the_rank_one_project(two_project_facts):
    selection = _selection("proj.pr-review-agent")

    text = top_ranked_project_text(two_project_facts, selection)

    assert text is not None
    assert "PR Review Agent" in text
    assert "controlled experiment" in text


def test_top_ranked_project_text_is_none_without_a_rank_one_project(two_project_facts):
    selection = CVSelection(
        section_order_reason="test",
        section_order=["skills", "experience", "projects", "education"],
        bullet_ranks=[],
        project_ranks=[],
        skill_group_ranks=[],
        target_title="Test Title",
    )

    assert top_ranked_project_text(two_project_facts, selection) is None


def test_write_cover_letter_includes_strongest_evidence_in_writer_context(facts):
    from agents.cover_letter_writer import write_cover_letter
    from models.cover_letter_schema import CoverLetterDraft, CoverLetterParagraph

    draft = CoverLetterDraft(
        paragraphs=[
            CoverLetterParagraph(kind="connective", fact_ids=[], text="Dear Hiring Team,"),
            CoverLetterParagraph(
                kind="factual", fact_ids=["exp.acme.b1"], text="I did thing one with 42 widgets."
            ),
        ]
    )

    with patch("agents.cover_letter_writer._call_writer", return_value=draft) as mock_call:
        write_cover_letter(
            facts,
            ParsedJD(),
            MatchAnalysis(match_summary="Strong match."),
            applied_for_role="Test Title",
            strongest_evidence="PR Review Agent: Ran a four-arm controlled experiment.",
        )

    mock_call.assert_called_once()
    assert (
        mock_call.call_args.kwargs["strongest_evidence"]
        == "PR Review Agent: Ran a four-arm controlled experiment."
    )
