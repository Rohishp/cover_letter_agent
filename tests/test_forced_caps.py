from cv.selection_rules import (
    MAX_PROJECTS,
    MAX_PROJECTS_FORCED,
    MAX_SKILL_GROUPS,
    MAX_SKILL_GROUPS_FORCED,
    MIN_PROJECTS,
    initial_state,
)
from cv.selector import CVSelection, ItemRank
from models.jd_schema import ParsedJD


def _ensure_all_projects_clear_the_quality_floor(facts):
    """
    This test exists to isolate the count-cap mechanism (item 7/8), not
    the separate quality floor (Phase F addendum 2) -- three of the
    shared fixture's four projects have only one bullet each, which the
    quality floor alone would now exclude regardless of the cap. Give
    every project a second bullet so only the cap under test is at play.
    """

    for project in facts.projects.entries:
        if len(project.bullets) < 2:
            project.bullets.append("A second real bullet with substance.")


def _selection_with_all_ranked() -> CVSelection:
    # The shared `facts` fixture has 4 projects and 5 skill groups --
    # enough to distinguish the default caps (3, 4) from the forced caps
    # (4, 5) on the same fixture.
    return CVSelection(
        section_order_reason="test",
        section_order=["skills", "experience", "projects", "education"],
        bullet_ranks=[],
        project_ranks=[
            ItemRank(id="proj.widget-analyzer", rank=1),
            ItemRank(id="proj.gadget-tracker", rank=2),
            ItemRank(id="proj.doohickey-portal", rank=3),
            ItemRank(id="proj.thingamajig-app", rank=4),
        ],
        skill_group_ranks=[
            ItemRank(id="skill.group-a", rank=1),
            ItemRank(id="skill.group-b", rank=2),
            ItemRank(id="skill.group-c", rank=3),
            ItemRank(id="skill.group-d", rank=4),
            ItemRank(id="skill.group-e", rank=5),
        ],
        target_title="Test Title",
    )


def test_non_forced_uses_default_caps(facts):
    _ensure_all_projects_clear_the_quality_floor(facts)
    selection = _selection_with_all_ranked()
    jd = ParsedJD()

    state, report = initial_state(facts, selection, jd, forced=False)

    assert MIN_PROJECTS <= len(state.project_ids) <= MAX_PROJECTS
    assert len(state.project_ids) == MAX_PROJECTS
    assert len(state.skill_group_ids) == MAX_SKILL_GROUPS
    assert len(report.excluded_projects) == 4 - MAX_PROJECTS
    assert len(report.excluded_skill_groups) == 5 - MAX_SKILL_GROUPS


def test_forced_uses_wider_caps_on_the_same_fixture(facts):
    _ensure_all_projects_clear_the_quality_floor(facts)
    selection = _selection_with_all_ranked()
    jd = ParsedJD()

    state, report = initial_state(facts, selection, jd, forced=True)

    assert len(state.project_ids) == MAX_PROJECTS_FORCED
    assert len(state.skill_group_ids) == MAX_SKILL_GROUPS_FORCED
    # All 4 projects and all 5 skill groups fit under the forced caps.
    assert report.excluded_projects == []
    assert report.excluded_skill_groups == []


def test_forced_and_non_forced_differ_on_the_same_fixture(facts):
    _ensure_all_projects_clear_the_quality_floor(facts)
    selection = _selection_with_all_ranked()
    jd = ParsedJD()

    non_forced_state, _ = initial_state(facts, selection, jd, forced=False)
    forced_state, _ = initial_state(facts, selection, jd, forced=True)

    assert len(forced_state.project_ids) > len(non_forced_state.project_ids)
    assert len(forced_state.skill_group_ids) > len(non_forced_state.skill_group_ids)
