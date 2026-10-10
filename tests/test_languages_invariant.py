from datetime import date

import pytest

from cv.facts import (
    CVFacts,
    Certifications,
    Coursework,
    Education,
    Extras,
    Languages,
    Meta,
    Personal,
    Projects,
    Skills,
    WorkExperience,
)
from cv.selection_rules import _tier1_languages, initial_state, materialize
from cv.selector import CVSelection
from models.jd_schema import ParsedJD


def _facts_with_no_languages() -> CVFacts:
    return CVFacts(
        meta=Meta(updated=date(2026, 1, 1), owner="Test Person"),
        personal=Personal(
            full_name="Test Person",
            location="Testville, Testland",
            email="test@example.com",
            phone="+1 555 0000",
            linkedin="https://www.linkedin.com/in/testperson",
            github="https://github.com/testperson",
            photo="exclude",
        ),
        languages=Languages(tier=1, entries=[]),
        education=Education(tier=1, entries=[]),
        work_experience=WorkExperience(tier=1, entries=[]),
        projects=Projects(tier=2, entries=[]),
        certifications=Certifications(tier=1, entries=[]),
        skills=Skills(groups=[]),
        coursework=Coursework(
            tier=3, include_when="", exclude_when="", render_as="bullet_list", items=[]
        ),
        extras=Extras(awards=[], volunteering=[]),
    )


def _empty_selection() -> CVSelection:
    return CVSelection(
        section_order_reason="test",
        section_order=["skills", "experience", "projects", "education"],
        bullet_ranks=[],
        project_ranks=[],
        skill_group_ranks=[],
        target_title="Test Title",
    )


def test_tier1_languages_raises_on_empty():
    facts = _facts_with_no_languages()

    with pytest.raises(ValueError, match="languages is empty"):
        _tier1_languages(facts)


def test_materialize_raises_on_empty_languages():
    facts = _facts_with_no_languages()
    selection = _empty_selection()
    jd = ParsedJD()

    state, _report = initial_state(facts, selection, jd)

    with pytest.raises(ValueError, match="languages is empty"):
        materialize(facts, jd, selection, state, "A short profile.")


def test_tier1_languages_passes_through_when_present(facts):
    languages = _tier1_languages(facts)

    assert len(languages) == len(facts.languages.entries)
    assert languages[0].language == facts.languages.entries[0].language
