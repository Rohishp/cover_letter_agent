# Item 5: a skill group naming the employer's own product, or a tool the
# JD names explicitly among its must-have/supporting skills, should rank
# above an equally-ranked group with no such overlap -- the real n8n case
# that motivated this: an "Automation" group containing "n8n" was cut by
# the top-N cap for an n8n JD.

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
    Projects,
    SkillGroupFact,
    Skills,
    WorkExperience,
)
from cv.selection_rules import MAX_SKILL_GROUPS, _top_skill_groups
from cv.selector import CVSelection, ItemRank
from models.jd_schema import ParsedJD


@pytest.fixture
def n8n_facts() -> CVFacts:
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
        projects=Projects(tier=2, entries=[]),
        certifications=Certifications(tier=1, entries=[]),
        skills=Skills(
            groups=[
                SkillGroupFact(name="Automation", items=["n8n"]),
                SkillGroupFact(name="Unrelated Skills A", items=["Foo"]),
                SkillGroupFact(name="Unrelated Skills B", items=["Bar"]),
                SkillGroupFact(name="Unrelated Skills C", items=["Baz"]),
                SkillGroupFact(name="Unrelated Skills D", items=["Qux"]),
            ]
        ),
        coursework=Coursework(tier=3, include_when="", exclude_when="", render_as="bullet_list", items=[]),
        extras=Extras(awards=[], volunteering=[]),
    )


def _selection_with_automation_ranked_last() -> CVSelection:
    return CVSelection(
        section_order_reason="test",
        section_order=["skills", "experience", "projects", "education"],
        bullet_ranks=[],
        project_ranks=[],
        skill_group_ranks=[
            ItemRank(id="skill.unrelated-skills-a", rank=1),
            ItemRank(id="skill.unrelated-skills-b", rank=2),
            ItemRank(id="skill.unrelated-skills-c", rank=3),
            ItemRank(id="skill.unrelated-skills-d", rank=4),
            ItemRank(id="skill.automation", rank=5),
        ],
        target_title="Test Title",
    )


def test_company_name_match_promotes_a_bottom_ranked_group(n8n_facts):
    jd = ParsedJD(company_name="n8n")
    selection = _selection_with_automation_ranked_last()

    kept, excluded = _top_skill_groups(n8n_facts, selection, jd)

    assert "skill.automation" in kept
    assert not any(note.id == "skill.automation" for note in excluded)
    assert len(kept) == MAX_SKILL_GROUPS


def test_explicitly_named_tool_in_requirements_promotes_a_bottom_ranked_group(n8n_facts):
    jd = ParsedJD(core_must_have_skills=["Experience building automations with n8n"])
    selection = _selection_with_automation_ranked_last()

    kept, _excluded = _top_skill_groups(n8n_facts, selection, jd)

    assert "skill.automation" in kept


def test_no_jd_signal_leaves_rank_order_untouched(n8n_facts):
    jd = ParsedJD(company_name="Some Other Company")
    selection = _selection_with_automation_ranked_last()

    kept, excluded = _top_skill_groups(n8n_facts, selection, jd)

    assert "skill.automation" not in kept
    assert any(note.id == "skill.automation" for note in excluded)
