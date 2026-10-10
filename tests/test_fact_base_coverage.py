# Phase H item 2: a JD-named term that IS true of the candidate (present
# as a tool/skill-group entry anywhere in the fact base) but demonstrated
# in ZERO of the bullets actually rendered on this application's CV must
# be flagged; a term demonstrated in a rendered bullet must not be.
# Report-only -- never auto-fixes, never gates.

from datetime import date

import pytest

from control_plane.fact_base_coverage import underdescribed_requirements
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
    Projects,
    Skills,
    SkillGroupFact,
    WorkExperience,
    WorkExperienceFact,
)
from cv.schema import CVContent, ExperienceEntry, SkillGroup
from models.jd_schema import ParsedJD


@pytest.fixture
def sql_facts() -> CVFacts:
    return CVFacts(
        meta=Meta(updated=date(2026, 1, 1), owner="Test Person"),
        personal=Personal(
            full_name="Test Person", location="Testville", email="test@example.com",
            phone="+1 555 0000", linkedin="https://www.linkedin.com/in/testperson",
            github="https://github.com/testperson", photo="exclude",
        ),
        languages=Languages(tier=1, entries=[LanguageFact(language="English", level="C1")]),
        education=Education(tier=1, entries=[]),
        work_experience=WorkExperience(
            tier=1,
            entries=[
                WorkExperienceFact(
                    position="Data Science Intern", organisation="Test Co",
                    city="Testville", dates="2022 - 2023", tools="Python, SQL, Hadoop",
                    bullets=["Built data-processing workflows on Hadoop."],
                ),
            ],
        ),
        projects=Projects(tier=2, entries=[]),
        certifications=Certifications(tier=1, entries=[]),
        skills=Skills(groups=[SkillGroupFact(name="Engineering", items=["Python", "SQL"])]),
        coursework=Coursework(tier=3, include_when="", exclude_when="", render_as="bullet_list", items=[]),
        extras=Extras(awards=[], volunteering=[]),
    )


def _content(bullets: list[str], skill_group_items: list[str], tools: str | None) -> CVContent:
    return CVContent(
        full_name="Test Person",
        target_title="Test Title",
        location="Testville",
        contact_details=["test@example.com"],
        contact_links=[],
        profile="A short profile.",
        skill_groups=[SkillGroup(name="Engineering", items=skill_group_items)],
        experience=[
            ExperienceEntry(
                position="Data Science Intern", organisation="Test Co", city="City",
                dates="2022 - 2023", tools=tools, bullets=bullets,
            )
        ],
        education=[],
        projects=[],
        certifications=[],
        languages=[],
        coursework=[],
    )


def test_term_true_of_candidate_but_no_rendered_bullet_is_flagged(sql_facts):
    jd = ParsedJD(technical_skills=["SQL"])
    content = _content(
        bullets=[
            "Built data-processing workflows on Hadoop.",
            "Applied machine-learning algorithms to analyse production data.",
            "Produced data visualisations for KPI reporting.",
        ],
        skill_group_items=["Python", "SQL"],
        tools="Python, SQL, Hadoop",
    )

    findings = underdescribed_requirements(jd, sql_facts, content)

    assert len(findings) == 1
    assert findings[0]["requirement"] == "SQL"
    assert "tools line: Data Science Intern" in findings[0]["found_in"]
    assert "skill group: Engineering" in findings[0]["found_in"]
    assert "Data Science Intern" in findings[0]["suggestion"]


def test_term_demonstrated_in_a_rendered_bullet_is_not_flagged(sql_facts):
    jd = ParsedJD(technical_skills=["SQL"])
    content = _content(
        bullets=[
            "Wrote complex SQL queries to clean manufacturing data.",
            "Applied machine-learning algorithms to analyse production data.",
            "Produced data visualisations for KPI reporting.",
        ],
        skill_group_items=["Python", "SQL"],
        tools="Python, SQL, Hadoop",
    )

    findings = underdescribed_requirements(jd, sql_facts, content)

    assert findings == []


def test_term_absent_from_the_fact_base_entirely_is_not_flagged(sql_facts):
    """
    Not true of the candidate anywhere is a different problem
    (weak_requirements / underrepresented_requirements), not this
    diagnostic's concern.
    """

    jd = ParsedJD(technical_skills=["Kubernetes"])
    content = _content(
        bullets=[
            "Built data-processing workflows on Hadoop.",
            "Applied machine-learning algorithms to analyse production data.",
            "Produced data visualisations for KPI reporting.",
        ],
        skill_group_items=["Python", "SQL"],
        tools="Python, SQL, Hadoop",
    )

    findings = underdescribed_requirements(jd, sql_facts, content)

    assert findings == []
