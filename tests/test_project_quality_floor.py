# Phase F addendum 2: a project inside the count cap's window still needs
# real content to earn its slot. Real case: forced mode's 4th project slot
# (YouTube Knowledge Agent -- one bullet, no digit) got filled just
# because MAX_PROJECTS_FORCED had room, not because it earned it.

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
from cv.selection_rules import MAX_PROJECTS_FORCED, MIN_PROJECTS, _ranked_projects
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


def _strong_project(name: str) -> ProjectFact:
    return ProjectFact(
        name=name, dates="2026", status="complete", tools="Python",
        intro="A real project.",
        bullets=["Ran a controlled experiment and shipped the simpler option.", "Reduced errors by 20%."],
    )


def _thin_project(name: str) -> ProjectFact:
    return ProjectFact(
        name=name, dates="2026", status="complete", tools="Python",
        intro="A minimal project.",
        bullets=["Built a small thing."],
    )


def _selection_ranked_1_to_4() -> CVSelection:
    return CVSelection(
        section_order_reason="test",
        section_order=["skills", "experience", "projects", "education"],
        bullet_ranks=[],
        project_ranks=[
            ItemRank(id="proj.first", rank=1),
            ItemRank(id="proj.second", rank=2),
            ItemRank(id="proj.third", rank=3),
            ItemRank(id="proj.fourth", rank=4),
        ],
        skill_group_ranks=[],
        target_title="Test Title",
    )


def test_thin_fourth_project_is_excluded_by_quality_floor_not_the_cap():
    facts = _base_facts(
        [
            _strong_project("First"),
            _strong_project("Second"),
            _strong_project("Third"),
            _thin_project("Fourth"),
        ]
    )
    selection = _selection_ranked_1_to_4()

    kept, excluded = _ranked_projects(facts, selection, ParsedJD(), forced=True)

    assert kept == ["proj.first", "proj.second", "proj.third"]
    assert len(excluded) == 1
    assert excluded[0].id == "proj.fourth"
    assert excluded[0].reason == "rank 4, cut by quality floor"


def test_four_comparably_strong_projects_all_survive():
    facts = _base_facts(
        [
            _strong_project("First"),
            _strong_project("Second"),
            _strong_project("Third"),
            _strong_project("Fourth"),
        ]
    )
    selection = _selection_ranked_1_to_4()

    kept, excluded = _ranked_projects(facts, selection, ParsedJD(), forced=True)

    assert kept == ["proj.first", "proj.second", "proj.third", "proj.fourth"]
    assert excluded == []


def test_quality_floor_never_cuts_below_min_projects():
    # Only the top-ranked project is genuinely strong; the rest are thin.
    # MIN_PROJECTS (2) must still be met by backfilling the best-ranked
    # thin ones, not by leaving the CV with a single project.
    facts = _base_facts(
        [
            _strong_project("First"),
            _thin_project("Second"),
            _thin_project("Third"),
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
        ],
        skill_group_ranks=[],
        target_title="Test Title",
    )

    kept, excluded = _ranked_projects(facts, selection, ParsedJD(), forced=False)

    assert len(kept) == MIN_PROJECTS
    assert kept == ["proj.first", "proj.second"]
    assert not any(note.id == "proj.second" for note in excluded)


def test_max_projects_forced_widens_eligibility_not_a_guarantee():
    # Exactly the real-world regression: forced mode's wider cap must not
    # by itself guarantee a thin project a slot.
    facts = _base_facts(
        [
            _strong_project("First"),
            _strong_project("Second"),
            _strong_project("Third"),
            _thin_project("Fourth"),
        ]
    )
    selection = _selection_ranked_1_to_4()

    kept, _excluded = _ranked_projects(facts, selection, ParsedJD(), forced=True)

    assert len(kept) < MAX_PROJECTS_FORCED
