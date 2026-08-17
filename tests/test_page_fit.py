# The LLM is mocked throughout: CVSelection objects are built by hand.
# Rendering/PDF-conversion tests are skipped if no converter (MS Word or
# LibreOffice) is available on the machine running them, matching how
# cv/checks.py's own PDF-dependent checks degrade. The probe runs lazily,
# inside each test that needs it -- not at module import time -- so a
# missing/flaky converter can't break test collection itself.

from datetime import date

import pytest

from cv.checks import convert_to_pdf
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
    WorkExperienceFact,
)
from cv.page_fit import MAX_PAGES, _drop_one_item, fit_to_pages
from cv.selection_rules import ExclusionNote, SelectionReport, SelectionState
from cv.selector import CVSelection, ItemRank
from models.jd_schema import ParsedJD


def _pdf_available() -> bool:
    import tempfile
    from pathlib import Path

    from docx import Document

    with tempfile.TemporaryDirectory() as tmp:
        docx_path = Path(tmp) / "probe.docx"
        Document().save(str(docx_path))
        pdf_path, _detail = convert_to_pdf(docx_path)
        return pdf_path is not None


def _skip_without_pdf_converter():
    if not _pdf_available():
        pytest.skip("no PDF converter (MS Word/LibreOffice) available")


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


def test_drop_order_project_then_skill_group_then_bullet(facts):
    selection = _empty_selection(
        project_ranks=[ItemRank(id="proj.widget-analyzer", rank=1)],
        skill_group_ranks=[ItemRank(id="skill.group-a", rank=1)],
    )

    state = SelectionState(
        project_ids=["proj.widget-analyzer"],
        skill_group_ids=["skill.group-a", "skill.group-b"],
        bullet_caps={"exp.acme": 5, "exp.beta": 3},
    )
    report = SelectionReport(
        section_order=["profile", "skills", "experience", "projects", "education",
                        "certifications", "languages", "coursework"],
        section_order_reason="test",
    )

    # 1st drop: the only project.
    assert _drop_one_item(facts, selection, state, report) is True
    assert state.project_ids == []
    assert len(report.excluded_projects) == 1
    assert report.excluded_projects[0].reason == "dropped to fit 2 pages"

    # 2nd + 3rd drops: skill groups, before any bullet is touched.
    assert _drop_one_item(facts, selection, state, report) is True
    assert _drop_one_item(facts, selection, state, report) is True
    assert state.skill_group_ids == []
    assert len(report.excluded_skill_groups) == 2
    assert state.bullet_caps["exp.acme"] == 5  # untouched so far

    # 4th drop: now bullets start getting trimmed.
    assert _drop_one_item(facts, selection, state, report) is True
    assert len(report.excluded_bullets) == 1
    assert sum(state.bullet_caps.values()) == 5 + 3 - 1


def test_never_drops_a_tier1_entry_below_its_minimum(facts):
    selection = _empty_selection()

    state = SelectionState(
        project_ids=[],
        skill_group_ids=[],
        bullet_caps={"exp.acme": 3, "exp.beta": 3},  # both already at experience minimum
    )
    report = SelectionReport(
        section_order=["profile", "skills", "experience", "projects", "education",
                        "certifications", "languages", "coursework"],
        section_order_reason="test",
    )

    assert _drop_one_item(facts, selection, state, report) is False
    assert state.bullet_caps == {"exp.acme": 3, "exp.beta": 3}


def test_fit_to_pages_fails_loudly_when_budget_cannot_be_met(tmp_path):
    _skip_without_pdf_converter()

    bullets = [
        f"Did substantial thing number {i} with measurable impact across a wide "
        "range of stakeholders, systems, and long-running production workloads."
        for i in range(1, 4)
    ]

    entries = [
        WorkExperienceFact(
            position=f"Senior Role Number {i} At A Long Winded Organisation",
            organisation=f"Company Number {i} International Holdings",
            city="Somewhere Far Away",
            dates="2015 - 2020",
            bullets=bullets,
        )
        for i in range(1, 31)
    ]

    huge_facts = CVFacts(
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
        work_experience=WorkExperience(tier=1, entries=entries),
        projects=Projects(tier=2, entries=[]),
        certifications=Certifications(tier=1, entries=[]),
        skills=Skills(groups=[]),
        coursework=Coursework(
            tier=3, include_when="", exclude_when="", render_as="bullet_list", items=[]
        ),
        extras=Extras(awards=[], volunteering=[]),
    )

    selection = _empty_selection()

    with pytest.raises(RuntimeError, match="does not fit"):
        fit_to_pages(huge_facts, ParsedJD(), selection, tmp_path / "impossible.docx")


def test_fit_to_pages_succeeds_within_budget(facts, tmp_path):
    _skip_without_pdf_converter()

    selection = _empty_selection(
        project_ranks=[ItemRank(id="proj.widget-analyzer", rank=1)],
    )

    result = fit_to_pages(facts, ParsedJD(), selection, tmp_path / "fits.docx")

    assert result.page_count <= MAX_PAGES
