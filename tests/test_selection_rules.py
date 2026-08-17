# The LLM is mocked throughout: CVSelection objects are built by hand,
# so cv.selector's OpenAI calls are never invoked by any test here.

import pytest

from cv.selection_rules import (
    EDUCATION_BULLET_MAX,
    EXPERIENCE_BULLET_MAX,
    FIGURE_RANK_BONUS,
    MAX_PROJECTS,
    MAX_SKILL_GROUPS,
    MIN_PROJECTS,
    initial_state,
    materialize,
    most_recent_completed_education_id,
    resolve_section_order,
    select_coursework,
    select_top_bullets,
)
from cv.selector import CVSelection, ItemRank
from models.jd_schema import ParsedJD


PLACEHOLDER_PROFILE = "A short, grounded profile."


def _empty_selection(**overrides) -> CVSelection:
    base = dict(
        section_order_reason="test",
        section_order=["skills", "experience", "projects", "education"],
        bullet_ranks=[],
        project_ranks=[],
        skill_group_ranks=[],
        target_title="Test Title",
    )
    base.update(overrides)
    return CVSelection(**base)


def _build(facts, parsed_jd, selection):
    state, report = initial_state(facts, selection, parsed_jd)
    content = materialize(facts, parsed_jd, selection, state, PLACEHOLDER_PROFILE)
    return content, report, state


# --- section order -----------------------------------------------------


def test_resolve_section_order_enforces_fixed_head_and_tail():
    selection = _empty_selection(
        section_order=["experience", "skills", "education", "projects"]
    )

    order = resolve_section_order(selection)

    assert order[0] == "profile"
    assert order[-3:] == ["certifications", "languages", "coursework"]
    assert order[1:-3] == ["experience", "skills", "education", "projects"]


def test_resolve_section_order_rejects_incomplete_middle():
    selection = _empty_selection(section_order=["skills", "experience"])

    with pytest.raises(ValueError):
        resolve_section_order(selection)


def test_resolve_section_order_rejects_unknown_section():
    selection = _empty_selection(
        section_order=["skills", "experience", "projects", "hobbies"]
    )

    with pytest.raises(ValueError):
        resolve_section_order(selection)


# --- tier-1 entries always render ---------------------------------------


def test_all_education_and_experience_entries_always_render(facts):
    selection = _empty_selection()  # nothing ranked at all
    jd = ParsedJD()

    content, _report, _state = _build(facts, jd, selection)

    assert len(content.experience) == len(facts.work_experience.entries)
    assert len(content.education) == len(facts.education.entries)


def test_certifications_and_languages_always_render_unranked(facts):
    selection = _empty_selection()
    jd = ParsedJD()

    content, _report, _state = _build(facts, jd, selection)

    assert len(content.certifications) == len(facts.certifications.entries)
    assert len(content.languages) == len(facts.languages.entries)


# --- bullet selection: rank + figure bonus -------------------------------


def test_select_top_bullets_keeps_highest_ranked():
    items = [("b1", "first"), ("b2", "second"), ("b3", "third")]
    rank_map = {
        "b1": ItemRank(id="b1", rank=3),
        "b2": ItemRank(id="b2", rank=1),
        "b3": ItemRank(id="b3", rank=2),
    }

    kept = select_top_bullets(items, rank_map, max_count=2)

    # original order preserved among the kept set (b2, b3 -- ranks 1 and 2)
    assert kept == ["second", "third"]


def test_figure_bonus_can_overtake_a_nearby_better_rank():
    # b1 (no digit) ranked 1 (better); b2 (has a digit) ranked 2 (one
    # step worse), well within FIGURE_RANK_BONUS -- the bonus flips it.
    assert FIGURE_RANK_BONUS > 1

    items = [("b1", "no digits here"), ("b2", "has a 42 in it")]
    rank_map = {
        "b1": ItemRank(id="b1", rank=1),
        "b2": ItemRank(id="b2", rank=2),
    }

    kept = select_top_bullets(items, rank_map, max_count=1)

    assert kept == ["has a 42 in it"]


def test_figure_bonus_does_not_override_a_much_better_rank():
    items = [("b1", "no digits here"), ("b2", "has a 42 in it")]
    rank_map = {
        "b1": ItemRank(id="b1", rank=1),
        "b2": ItemRank(id="b2", rank=1 + int(FIGURE_RANK_BONUS) + 5),
    }

    kept = select_top_bullets(items, rank_map, max_count=1)

    assert kept == ["no digits here"]


def test_unranked_figure_bullet_beats_unranked_non_figure_bullet():
    items = [("b1", "no digits here"), ("b2", "has a 42 in it")]
    rank_map = {}  # both unranked

    kept = select_top_bullets(items, rank_map, max_count=1)

    assert kept == ["has a 42 in it"]


def test_experience_entry_over_max_is_trimmed_to_schema_max(facts):
    selection = _empty_selection()
    jd = ParsedJD()

    content, _report, _state = _build(facts, jd, selection)

    acme_entry = next(e for e in content.experience if e.position == "Senior Thing Doer")
    assert len(acme_entry.bullets) == EXPERIENCE_BULLET_MAX


# --- "in progress" education entry --------------------------------------


def test_in_progress_education_entry_becomes_status_not_bullet(facts):
    selection = _empty_selection()
    jd = ParsedJD()

    content, _report, _state = _build(facts, jd, selection)

    entry = next(e for e in content.education if e.organisation == "Test University")

    assert entry.bullets == []
    assert entry.dates == "01.2026 - present, ongoing"


# --- only the most recent completed degree carries bullets --------------


def test_most_recent_completed_education_excludes_ongoing_entry(facts):
    # facts fixture: "Test University" (01.2026 - present, ongoing) and
    # "Old University" (2015 - 2018, completed) -- the ongoing one must
    # not be picked as "most recent completed".
    most_recent_id = most_recent_completed_education_id(facts)

    assert most_recent_id is not None
    ref = facts.by_id(most_recent_id)
    assert ref.text == "B.Sc. Computer Science"


def test_older_completed_degree_renders_heading_only(facts):
    selection = _empty_selection()
    jd = ParsedJD()

    content, _report, _state = _build(facts, jd, selection)

    # Only one non-ongoing education entry exists in the shared fixture,
    # so it must be the one that keeps its bullets.
    bsc_entry = next(e for e in content.education if e.organisation == "Old University")
    assert len(bsc_entry.bullets) == 3
    assert len(bsc_entry.bullets) <= EDUCATION_BULLET_MAX


# --- projects: rank + min/max, no "uncovered requirement" rule ----------


def test_projects_kept_between_min_and_max(facts):
    selection = _empty_selection(
        project_ranks=[
            ItemRank(id="proj.widget-analyzer", rank=1),
            ItemRank(id="proj.gadget-tracker", rank=2),
            ItemRank(id="proj.doohickey-portal", rank=3),
            ItemRank(id="proj.thingamajig-app", rank=4),
        ]
    )
    jd = ParsedJD()

    content, report, _state = _build(facts, jd, selection)

    assert MIN_PROJECTS <= len(content.projects) <= MAX_PROJECTS
    assert len(content.projects) == MAX_PROJECTS

    kept_names = {p.position for p in content.projects}
    assert kept_names == {"Widget Analyzer", "Gadget Tracker", "Doohickey Portal"}

    excluded_names = {note.label for note in report.excluded_projects}
    assert excluded_names == {"Thingamajig App"}


def test_project_not_excluded_merely_for_lacking_a_unique_requirement(facts):
    # No evidences_requirement anywhere -- the old rule would have cut
    # every project. The new rule only ranks and caps.
    selection = _empty_selection(
        project_ranks=[
            ItemRank(id="proj.widget-analyzer", rank=1, evidences_requirement=None),
        ]
    )
    jd = ParsedJD(core_must_have_skills=["Widget processing"])

    content, _report, _state = _build(facts, jd, selection)

    assert any(p.position == "Widget Analyzer" for p in content.projects)


def test_project_bullets_include_intro_first(facts):
    selection = _empty_selection(
        project_ranks=[ItemRank(id="proj.widget-analyzer", rank=1)]
    )
    jd = ParsedJD()

    content, _report, _state = _build(facts, jd, selection)

    widget_project = next(p for p in content.projects if p.position == "Widget Analyzer")
    assert widget_project.bullets[0] == "Analyzes widgets."


# --- coursework -----------------------------------------------------------


def test_coursework_included_when_jd_names_a_coursework_item(facts):
    jd = ParsedJD(technical_skills=["RTOS"])

    result = select_coursework(facts, jd)

    assert result == facts.coursework.items


def test_coursework_excluded_when_jd_does_not_name_a_coursework_item(facts):
    jd = ParsedJD(technical_skills=["React", "Node.js"])

    result = select_coursework(facts, jd)

    assert result == []


# --- skill groups: top 4 kept ---------------------------------------------


def test_skill_groups_top_four_kept_by_rank(facts):
    selection = _empty_selection(
        skill_group_ranks=[
            ItemRank(id="skill.group-e", rank=1),
            ItemRank(id="skill.group-d", rank=2),
            ItemRank(id="skill.group-c", rank=3),
            ItemRank(id="skill.group-b", rank=4),
            ItemRank(id="skill.group-a", rank=5),
        ]
    )
    jd = ParsedJD()

    content, report, _state = _build(facts, jd, selection)

    assert len(content.skill_groups) == MAX_SKILL_GROUPS
    kept_names = {g.name for g in content.skill_groups}
    assert kept_names == {"Group E", "Group D", "Group C", "Group B"}

    excluded = {n.label for n in report.excluded_skill_groups}
    assert excluded == {"Group A"}
