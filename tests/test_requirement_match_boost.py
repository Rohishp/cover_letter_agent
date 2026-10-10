# Phase G item 1: any project whose tools/intro/bullets textually match
# the JD's own structured requirement fields should get a rank boost, and
# the quality floor should apply AFTER that boost -- a thin project that's
# the sole evidence for a named requirement must not be cut for it.

from datetime import date

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
from cv.selection_rules import MAX_PROJECTS, MIN_PROJECTS, _ranked_projects
from cv.selector import CVSelection, ItemRank
from models.jd_schema import ParsedJD


def _base_facts(projects: list[ProjectFact]) -> CVFacts:
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
        projects=Projects(tier=2, entries=projects),
        certifications=Certifications(tier=1, entries=[]),
        skills=Skills(groups=[]),
        coursework=Coursework(tier=3, include_when="", exclude_when="", render_as="bullet_list", items=[]),
        extras=Extras(awards=[], volunteering=[]),
    )


def _rag_project() -> ProjectFact:
    # Real case: thin (one bullet, no digit -- fails the raw quality
    # floor on its own) but is the sole evidence for a named requirement.
    return ProjectFact(
        name="YouTube Knowledge Agent (RAG)", dates="2026", status="complete",
        tools="Python, RAG, ChromaDB",
        intro="RAG agent that answers questions from a persistent vector store of YouTube transcripts.",
        bullets=["Built source-cited, confidence-scored answers using semantic chunking and a persistent ChromaDB vector store."],
    )


def _richer_unrelated_project(name: str) -> ProjectFact:
    return ProjectFact(
        name=name, dates="2026", status="complete", tools="Python, FastAPI",
        intro="An unrelated but well-documented project.",
        bullets=[
            "Shipped a production feature that cut latency by 30 percent.",
            "Wrote extensive tests achieving 95 percent coverage.",
        ],
    )


@pytest.fixture
def rag_jd() -> ParsedJD:
    # Deliberately no "Python" here -- every fixture project below tags
    # "Python" as a tool, so including it would make the boost match
    # everything equally and defeat the point of these tests.
    return ParsedJD(
        core_must_have_skills=["Design, build, test and deploy AI and Generative AI solutions"],
        technical_skills=["RAG architectures", "vector databases"],
    )


def _selection(rag_rank: int) -> CVSelection:
    return CVSelection(
        section_order_reason="test",
        section_order=["skills", "experience", "projects", "education"],
        bullet_ranks=[],
        project_ranks=[
            ItemRank(id="proj.first", rank=1),
            ItemRank(id="proj.second", rank=2),
            ItemRank(id="proj.youtube-knowledge-agent-rag", rank=rag_rank),
        ],
        skill_group_ranks=[],
        target_title="Test Title",
    )


def test_thin_rag_project_survives_the_quality_floor_via_requirement_match(rag_jd):
    facts = _base_facts(
        [
            _richer_unrelated_project("First"),
            _richer_unrelated_project("Second"),
            _rag_project(),
        ]
    )
    # Ranked last (worst) by the LLM -- without the boost, it would be
    # both last in cap order and fail the raw quality floor (one bullet,
    # no digit).
    selection = _selection(rag_rank=3)

    kept, excluded = _ranked_projects(facts, selection, rag_jd, forced=False)

    assert "proj.youtube-knowledge-agent-rag" in kept
    assert not any(note.id == "proj.youtube-knowledge-agent-rag" for note in excluded)


def test_same_thin_project_is_cut_without_a_requirement_match():
    facts = _base_facts(
        [
            _richer_unrelated_project("First"),
            _richer_unrelated_project("Second"),
            _rag_project(),
        ]
    )
    selection = _selection(rag_rank=3)
    no_signal_jd = ParsedJD()  # no RAG/vector-database mention anywhere

    kept, excluded = _ranked_projects(facts, selection, no_signal_jd, forced=False)

    assert "proj.youtube-knowledge-agent-rag" not in kept
    assert any(
        note.id == "proj.youtube-knowledge-agent-rag" and note.reason == "rank 3, cut by quality floor"
        for note in excluded
    )


def test_requirement_match_promotes_a_project_ranked_beyond_the_count_cap(rag_jd):
    # 4 projects, MAX_PROJECTS=3 (non-forced) -- the RAG project is
    # ranked 4th (dead last), beyond the count cap entirely, not just
    # failing the quality floor within it.
    facts = _base_facts(
        [
            _richer_unrelated_project("First"),
            _richer_unrelated_project("Second"),
            _richer_unrelated_project("Third"),
            _rag_project(),
        ]
    )
    selection = CVSelection(
        section_order_reason="test",
        section_order=["skills", "experience", "projects", "education"],
        bullet_ranks=[],
        project_ranks=[
            ItemRank(id="proj.first", rank=1),
            ItemRank(id="proj.second", rank=2),
            ItemRank(id="proj.third", rank=3),
            ItemRank(id="proj.youtube-knowledge-agent-rag", rank=4),
        ],
        skill_group_ranks=[],
        target_title="Test Title",
    )

    kept, _excluded = _ranked_projects(facts, selection, rag_jd, forced=False)

    assert "proj.youtube-knowledge-agent-rag" in kept
    assert len(kept) == MAX_PROJECTS
