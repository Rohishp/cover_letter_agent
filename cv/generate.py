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
    build_headline_strip,
    materialize,
    render_final_content_with_ids,
    requirement_evidence_fact_ids,
    surviving_ids,
    top_ranked_evidence_block,
    top_ranked_project_name,
)
from cv.selector import CVSelection, select_cv_content, write_profile
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
    # Phase I item 1: the fact-base ID backing each term kept on the
    # headline strip, for run.json / verification -- not used by any
    # writer, render-only reporting.
    headline_term_fact_ids: dict[str, str] = {}


def generate_cv(
    facts: CVFacts,
    parsed_jd: ParsedJD,
    out_path: Path,
    forced: bool = False,
    selection: CVSelection | None = None,
    raw_jd_text: str = "",
) -> GenerateCVResult:
    """
    The full CV generation flow, shared by scripts/generate_cv.py and
    apply.py so neither duplicates it. Two LLM calls:

    1. select_cv_content -- rankings, section order, target title.
    2. write_profile -- profile, written last, from only the final
       selected content (after page-fit and the figure-density floor),
       so it can never cite something that got cut.

    forced (item 7/8): widens the project/skill-group caps before
    page-fit trims back to two pages, and asks the profile call for the
    single strongest honest through-line.

    selection: pass in an already-computed CVSelection (item 6 -- apply.py
    runs the selector early to feed the top-ranked project to the cover
    letter writer) to reuse it here instead of ranking a second time,
    which could otherwise disagree with the first call and quote a
    different "top" project than the letter engaged with. None runs the
    selector as before.

    raw_jd_text: the unparsed JD text (Phase F item 3) -- needed for
    skill-group JD-signal matching, since parsed_jd's structured fields
    don't retain literal tool names. Optional; "" disables that source.
    """

    out_path = Path(out_path)

    if selection is None:
        selection = select_cv_content(facts, parsed_jd)

    # Computed once, deterministically, before page-fit: a render-only
    # artifact (see build_headline_strip's docstring and
    # claude/cover-letter-path-root-cause.md) passed through as plain
    # data everywhere it's needed, never recomputed and never fed to any
    # LLM call.
    headline_strip, headline_terms_kept, _positioning = build_headline_strip(
        facts, selection, parsed_jd, raw_jd_text
    )

    fit_result = fit_to_pages(
        facts, parsed_jd, selection, out_path, forced=forced, raw_jd_text=raw_jd_text,
        headline_strip=headline_strip,
    )

    density_result = enforce_figure_density_floor(
        facts, parsed_jd, selection, fit_result.state, PROFILE_PLACEHOLDER, out_path,
        headline_strip=headline_strip,
    )

    valid_ids = surviving_ids(facts, parsed_jd, selection, fit_result.state)
    final_content_block = render_final_content_with_ids(facts, parsed_jd, selection, fit_result.state)

    top_ranked_evidence = top_ranked_evidence_block(facts, selection)
    top_ranked_opening_label = top_ranked_project_name(facts, selection)
    requirement_coverage = requirement_evidence_fact_ids(facts, parsed_jd, raw_jd_text=raw_jd_text)
    profile_selection = write_profile(
        facts, parsed_jd, final_content_block, valid_ids,
        forced=forced, top_ranked_evidence=top_ranked_evidence,
        top_ranked_opening_label=top_ranked_opening_label,
        requirement_coverage=requirement_coverage,
    )

    final_content = materialize(
        facts, parsed_jd, selection, fit_result.state, profile_selection.profile, headline_strip
    )
    # Reuses the report's already-resolved order (computed once, inside
    # initial_state, with the item-2 deterministic override applied) so
    # the final render can never disagree with what page-fit measured.
    docx_path = render_cv(final_content, out_path, section_order=fit_result.report.section_order)

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
        headline_term_fact_ids={item: fact_id for item, fact_id in headline_terms_kept},
    )


def build_cv_run_summary(result: GenerateCVResult) -> dict:
    """
    JSON-able summary of one CV generation: section order, what was cut,
    scores/checks, and the model settings used. Shared by
    scripts/generate_cv.py and apply.py so run.json's shape is
    consistent regardless of entry point.
    """

    return {
        "headline": result.content.headline_strip,
        "headline_term_fact_ids": result.headline_term_fact_ids,
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
