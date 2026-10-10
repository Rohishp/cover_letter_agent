# Rendering/PDF-conversion tests are skipped if no converter (MS Word or
# LibreOffice) is available, matching the pattern already used by
# tests/test_page_fit.py and tests/test_density_floor.py. The probe runs
# lazily, inside the test, not at import time.

import pytest

from cv.checks import FIGURE_DENSITY_FLOOR, check_metric_density, convert_to_pdf
from cv.render import DEFAULT_SECTION_ORDER, render_cv
from cv.schema import CVContent, EducationEntry, ExperienceEntry


def _skip_without_pdf_converter():
    import tempfile
    from pathlib import Path

    from docx import Document

    with tempfile.TemporaryDirectory() as tmp:
        docx_path = Path(tmp) / "probe.docx"
        Document().save(str(docx_path))
        pdf_path, _detail = convert_to_pdf(docx_path)

        if pdf_path is None:
            pytest.skip("no PDF converter (MS Word/LibreOffice) available")


def _content(bullets: list[str]) -> CVContent:
    return CVContent(
        full_name="Test Person",
        target_title="Test Title",
        location="Testville",
        contact_details=["test@example.com"],
        contact_links=[],
        profile="A short profile.",
        skill_groups=[],
        experience=[
            ExperienceEntry(
                position="Role",
                organisation="Company",
                city="City",
                dates="2020 - 2022",
                bullets=bullets,
            )
        ],
        education=[
            EducationEntry(
                position="Degree", organisation="University", city="City",
                dates="2015 - 2018", bullets=[],
            )
        ],
        projects=[],
        certifications=[],
        languages=[],
        coursework=[],
    )


def test_metric_density_fails_below_floor(tmp_path):
    _skip_without_pdf_converter()

    # 5 bullets, only 1 with a digit -> 20%, well under the 50% floor.
    content = _content(
        [
            "Did a thing with no numbers at all in it whatsoever really.",
            "Did another thing with no numbers in it either, at all.",
            "Did a third thing, still no numbers here, nothing quantified.",
            "Did a fourth thing, plain prose, no figures present anywhere.",
            "Did a fifth thing worth 42 points on some scale somewhere.",
        ]
    )

    docx_path = render_cv(content, tmp_path / "cv.docx", section_order=DEFAULT_SECTION_ORDER)
    pdf_path, _detail = convert_to_pdf(docx_path)

    check_id, passed, detail = check_metric_density(docx_path, content=content, pdf_path=pdf_path)

    assert check_id == "metric_density"
    assert passed is False
    assert "20%" in detail or "1/5" in detail


def test_metric_density_passes_at_or_above_floor(tmp_path):
    _skip_without_pdf_converter()

    # 4 bullets, 3 with a digit -> 75%, above the 50% floor.
    content = _content(
        [
            "Shipped a feature that cut latency by 42 percent overall.",
            "Reduced error rates from 12 percent down to 3 percent total.",
            "Delivered a report covering 1000 records processed daily.",
            "Wrote documentation for the new onboarding process quickly.",
        ]
    )

    docx_path = render_cv(content, tmp_path / "cv2.docx", section_order=DEFAULT_SECTION_ORDER)
    pdf_path, _detail = convert_to_pdf(docx_path)

    check_id, passed, detail = check_metric_density(docx_path, content=content, pdf_path=pdf_path)

    assert check_id == "metric_density"
    assert passed is True
    assert f"floor {FIGURE_DENSITY_FLOOR:.0%}" in detail
