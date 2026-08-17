from pathlib import Path

from pydantic import BaseModel

from cv.checks import convert_to_pdf
from cv.facts import CVFacts
from cv.render import render_cv
from cv.schema import CVContent
from cv.selection_rules import (
    EDUCATION_BULLET_MIN,
    EXPERIENCE_BULLET_MIN,
    PROFILE_PLACEHOLDER,
    ExclusionNote,
    SelectionReport,
    SelectionState,
    WORST_RANK,
    _fact_for_entry,
    _rank_map,
    initial_state,
    materialize,
    sort_bullets_by_priority,
)
from cv.selector import CVSelection
from models.jd_schema import ParsedJD


MAX_PAGES = 2

# Safety valve against an infinite loop; real content never needs this
# many single-item drops to fit two pages.
MAX_DROP_ITERATIONS = 50


class PageFitResult(BaseModel):
    content: CVContent
    report: SelectionReport
    state: SelectionState
    page_count: int
    docx_path: str
    pdf_path: str


def _page_count(pdf_path: Path) -> int:
    import pymupdf

    pdf = pymupdf.open(str(pdf_path))
    count = pdf.page_count
    pdf.close()
    return count


def _drop_one_item(
    facts: CVFacts,
    selection: CVSelection,
    state: SelectionState,
    report: SelectionReport,
) -> bool:
    """
    Drop exactly one item, in priority order: lowest-ranked project, then
    lowest-ranked skill group, then the lowest-ranked bullet in the
    lowest-ranked (experience/education) entry. Never drops a tier-1
    entry itself, only trims its bullets toward the schema minimum.

    Returns False when nothing is left to drop.
    """

    if state.project_ids:
        rank_map = _rank_map(selection.project_ranks)
        worst = max(
            state.project_ids,
            key=lambda project_id: rank_map[project_id].rank
            if project_id in rank_map
            else WORST_RANK,
        )
        rank = rank_map[worst].rank if worst in rank_map else None

        state.project_ids.remove(worst)
        state.bullet_caps.pop(worst, None)

        report.excluded_projects.append(
            ExclusionNote(
                kind="project",
                id=worst,
                label=facts.by_id(worst).text,
                reason="dropped to fit 2 pages",
                rank=rank,
            )
        )
        return True

    if state.skill_group_ids:
        rank_map = _rank_map(selection.skill_group_ranks)
        worst = max(
            state.skill_group_ids,
            key=lambda group_id: rank_map[group_id].rank
            if group_id in rank_map
            else WORST_RANK,
        )
        rank = rank_map[worst].rank if worst in rank_map else None

        state.skill_group_ids.remove(worst)

        report.excluded_skill_groups.append(
            ExclusionNote(
                kind="skill_group",
                id=worst,
                label=facts.by_id(worst).text,
                reason="dropped to fit 2 pages",
                rank=rank,
            )
        )
        return True

    bullet_rank_map = _rank_map(selection.bullet_ranks)
    candidates = []

    for entry_id, cap in state.bullet_caps.items():
        ref = facts.by_id(entry_id)

        if ref.kind not in ("experience", "education"):
            continue

        min_allowed = EXPERIENCE_BULLET_MIN if ref.kind == "experience" else EDUCATION_BULLET_MIN

        if cap <= min_allowed:
            continue

        fact = _fact_for_entry(facts, entry_id, ref.kind)
        bullet_items = [
            (f"{entry_id}.b{index}", bullet)
            for index, bullet in enumerate(fact.bullets, start=1)
        ]
        ordered = sort_bullets_by_priority(bullet_items, bullet_rank_map)
        worst_bullet_id, worst_bullet_text = ordered[cap - 1]
        worst_rank = (
            bullet_rank_map[worst_bullet_id].rank
            if worst_bullet_id in bullet_rank_map
            else WORST_RANK
        )

        candidates.append((worst_rank, entry_id, worst_bullet_id, worst_bullet_text))

    if not candidates:
        return False

    candidates.sort(key=lambda candidate: candidate[0], reverse=True)
    worst_rank, entry_id, bullet_id, bullet_text = candidates[0]

    state.bullet_caps[entry_id] -= 1

    report.excluded_bullets.append(
        ExclusionNote(
            kind="bullet",
            id=bullet_id,
            label=bullet_text,
            reason="dropped to fit 2 pages",
            rank=None if worst_rank == WORST_RANK else worst_rank,
        )
    )
    return True


def fit_to_pages(
    facts: CVFacts,
    parsed_jd: ParsedJD,
    selection: CVSelection,
    out_path: Path,
) -> PageFitResult:
    """
    Render, convert, measure. Drop the weakest optional item and
    re-render until the document fits MAX_PAGES. Fails loudly, with what
    is still over budget, if it can't fit even at minimum content.
    """

    out_path = Path(out_path)
    state, report = initial_state(facts, selection, parsed_jd)

    for _iteration in range(MAX_DROP_ITERATIONS):
        content = materialize(facts, parsed_jd, selection, state, PROFILE_PLACEHOLDER)
        docx_path = render_cv(content, out_path, section_order=report.section_order)
        pdf_path, converter_detail = convert_to_pdf(docx_path)

        if pdf_path is None:
            raise RuntimeError(
                f"Cannot measure page count -- no PDF converter available: {converter_detail}"
            )

        page_count = _page_count(pdf_path)

        if page_count <= MAX_PAGES:
            return PageFitResult(
                content=content,
                report=report,
                state=state,
                page_count=page_count,
                docx_path=str(docx_path),
                pdf_path=str(pdf_path),
            )

        if not _drop_one_item(facts, selection, state, report):
            raise RuntimeError(
                f"CV does not fit {MAX_PAGES} pages ({page_count} pages) even with "
                "every optional project and skill group dropped and every entry at "
                "its minimum bullet count. Over budget by "
                f"{page_count - MAX_PAGES} page(s). Nothing left to cut."
            )

    raise RuntimeError(
        f"Gave up after {MAX_DROP_ITERATIONS} single-item drops without fitting "
        f"{MAX_PAGES} pages."
    )
