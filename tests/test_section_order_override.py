# Phase F item 2: a deterministic override of Projects-vs-Experience
# order -- either signal (project ranks beating experience-bullet ranks,
# or the JD's own text signaling builder-first hiring) promotes Projects
# ahead of Experience; neither signal leaves the LLM's order untouched.

from cv.selection_rules import (
    DETERMINISTIC_BUILDER_FIRST_ORDER,
    initial_state,
    projects_outrank_experience,
    resolve_section_order,
)
from cv.selector import CVSelection, ItemRank
from models.jd_schema import ParsedJD


def _selection(**overrides) -> CVSelection:
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


def test_projects_outrank_experience_when_project_ranks_beat_experience_bullets(facts):
    selection = _selection(
        project_ranks=[ItemRank(id="proj.widget-analyzer", rank=1)],
        bullet_ranks=[ItemRank(id="exp.acme.b1", rank=10)],
    )

    assert projects_outrank_experience(facts, selection) is True


def test_projects_do_not_outrank_when_experience_bullets_rank_better(facts):
    selection = _selection(
        project_ranks=[ItemRank(id="proj.widget-analyzer", rank=10)],
        bullet_ranks=[ItemRank(id="exp.acme.b1", rank=1)],
    )

    assert projects_outrank_experience(facts, selection) is False


def test_no_ranks_at_all_does_not_outrank(facts):
    selection = _selection()

    assert projects_outrank_experience(facts, selection) is False


def test_relevance_signal_alone_promotes_projects(facts):
    jd = ParsedJD()  # no builder-first text at all
    selection = _selection(
        project_ranks=[ItemRank(id="proj.widget-analyzer", rank=1)],
        bullet_ranks=[ItemRank(id="exp.acme.b1", rank=10)],
    )

    order = resolve_section_order(selection, facts, jd)

    assert order[1:5] == DETERMINISTIC_BUILDER_FIRST_ORDER
    assert order.index("projects") < order.index("experience")


def test_culture_signal_alone_promotes_projects(facts):
    jd = ParsedJD(supporting_skills=["Comfortable shipping visible building and side projects"])
    # Experience deliberately ranked ahead here -- the culture signal alone must still fire.
    selection = _selection(
        project_ranks=[ItemRank(id="proj.widget-analyzer", rank=10)],
        bullet_ranks=[ItemRank(id="exp.acme.b1", rank=1)],
    )

    order = resolve_section_order(selection, facts, jd)

    assert order.index("projects") < order.index("experience")


def test_no_signal_keeps_llm_order_unchanged(facts):
    jd = ParsedJD()
    selection = _selection(
        section_order=["experience", "skills", "education", "projects"],
        project_ranks=[ItemRank(id="proj.widget-analyzer", rank=10)],
        bullet_ranks=[ItemRank(id="exp.acme.b1", rank=1)],
    )

    order = resolve_section_order(selection, facts, jd)

    assert order[1:5] == ["experience", "skills", "education", "projects"]


def test_no_facts_or_jd_leaves_order_unchanged_backward_compatible(facts):
    selection = _selection(section_order=["experience", "skills", "education", "projects"])

    order = resolve_section_order(selection)

    assert order[1:5] == ["experience", "skills", "education", "projects"]


def test_initial_state_report_reflects_the_override(facts):
    jd = ParsedJD()
    selection = _selection(
        project_ranks=[ItemRank(id="proj.widget-analyzer", rank=1)],
        bullet_ranks=[ItemRank(id="exp.acme.b1", rank=10)],
    )

    _state, report = initial_state(facts, selection, jd)

    assert report.section_order[1:5] == DETERMINISTIC_BUILDER_FIRST_ORDER
    assert "Deterministic override" in report.section_order_reason
