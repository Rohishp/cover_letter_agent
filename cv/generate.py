from pathlib import Path

from pydantic import BaseModel

from cv.checks import CheckResult, convert_to_pdf, run_checks
from cv.density_floor import enforce_figure_density_floor
from cv.facts import CVFacts
from cv.page_fit import fit_to_pages
from cv.render import render_cv
from cv.schema import CVContent
from cv.selection_rules import (
    PROFILE_PLACEHOLDER,
    SelectionReport,
    materialize,
    render_final_content_with_ids,
    resolve_section_order,
    surviving_ids,
)
from cv.selector import select_cv_content, write_profile
from models.jd_schema import ParsedJD


CV_MODEL_SETTINGS = {
    "selector_model": "gpt-4o",
    "selector_temperature": 0,
    "selector_seed": 42,
    "profile_writer_model": "gpt-4o",
    "profile_writer_temperature": 0,
    "profile_writer_seed": 42,
}


class GenerateCVResult(BaseModel):
    content: CVContent
    report: SelectionReport
    docx_path: str
    pdf_path: str
    page_count: int
    density_before: float
    density_after: float
    swap_count: int
    check_results: list[CheckResult]


def generate_cv(
    facts: CVFacts,
    parsed_jd: ParsedJD,
    out_path: Path,
) -> GenerateCVResult:
    """
    The full CV generation flow, shared by scripts/generate_cv.py and
    apply.py so neither duplicates it. Two LLM calls:

    1. select_cv_content -- rankings, section order, target title.
    2. write_profile -- profile, written last, from only the final
       selected content (after page-fit and the figure-density floor),
       so it can never cite something that got cut.
    """

    out_path = Path(out_path)

    selection = select_cv_content(facts, parsed_jd)

    fit_result = fit_to_pages(facts, parsed_jd, selection, out_path)

    density_result = enforce_figure_density_floor(
        facts, parsed_jd, selection, fit_result.state, PROFILE_PLACEHOLDER, out_path
    )

    valid_ids = surviving_ids(facts, parsed_jd, selection, fit_result.state)
    final_content_block = render_final_content_with_ids(facts, parsed_jd, selection, fit_result.state)

    profile_selection = write_profile(facts, parsed_jd, final_content_block, valid_ids)

    final_content = materialize(
        facts, parsed_jd, selection, fit_result.state, profile_selection.profile
    )
    section_order = resolve_section_order(selection)
    docx_path = render_cv(final_content, out_path, section_order=section_order)

    pdf_path, converter_detail = convert_to_pdf(docx_path)

    if pdf_path is None:
        raise RuntimeError(f"Cannot finalize CV -- no PDF converter available: {converter_detail}")

    import pymupdf

    pdf = pymupdf.open(str(pdf_path))
    page_count = pdf.page_count
    pdf.close()

    check_results = run_checks(docx_path, final_content, facts, pdf_path=pdf_path)

    return GenerateCVResult(
        content=final_content,
        report=fit_result.report,
        docx_path=str(docx_path),
        pdf_path=str(pdf_path),
        page_count=page_count,
        density_before=density_result.density_before,
        density_after=density_result.density_after,
        swap_count=density_result.swap_count,
        check_results=check_results,
    )


def build_cv_run_summary(result: GenerateCVResult) -> dict:
    """
    JSON-able summary of one CV generation: section order, what was cut,
    scores/checks, and the model settings used. Shared by
    scripts/generate_cv.py and apply.py so run.json's shape is
    consistent regardless of entry point.
    """

    return {
        "section_order": result.report.section_order,
        "section_order_reason": result.report.section_order_reason,
        "excluded_projects": [note.model_dump() for note in result.report.excluded_projects],
        "excluded_skill_groups": [note.model_dump() for note in result.report.excluded_skill_groups],
        "excluded_bullets": [note.model_dump() for note in result.report.excluded_bullets],
        "page_count": result.page_count,
        "figure_density_before": result.density_before,
        "figure_density_after": result.density_after,
        "figure_density_swaps": result.swap_count,
        "check_results": [
            {"check_id": check_id, "passed": passed, "detail": detail}
            for check_id, passed, detail in result.check_results
        ],
        "model_settings": CV_MODEL_SETTINGS,
    }
