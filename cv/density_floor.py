from pathlib import Path

from pydantic import BaseModel

from cv.checks import convert_to_pdf, page1_bullet_digit_stats
from cv.facts import CVFacts
from cv.render import render_cv
from cv.schema import CVContent
from cv.selection_rules import (
    WORST_RANK,
    _fact_for_entry,
    _has_digit,
    _rank_map,
    materialize,
    resolve_section_order,
    sort_bullets_by_priority,
)
from cv.selector import CVSelection
from models.jd_schema import ParsedJD


FIGURE_DENSITY_FLOOR = 0.5

# Safety valve; real content never needs this many single-swap iterations.
MAX_SWAP_ITERATIONS = 30


class DensityFloorResult(BaseModel):
    content: CVContent
    docx_path: str
    pdf_path: str
    density_before: float
    density_after: float
    swap_count: int


def _normalize(text: str) -> str:
    import re

    return re.sub(r"\s+", " ", text).strip().lower()


def _try_one_swap(
    facts: CVFacts,
    selection: CVSelection,
    state,
    page1_text_normalized: str,
) -> bool:
    """
    Find the worst-ranked kept non-figure bullet that is on page 1 and
    has a same-entry dropped figure bullet available, and swap them.
    Returns False if no valid swap exists anywhere.
    """

    rank_map = _rank_map(selection.bullet_ranks)
    candidates = []  # (rank, entry_id, bad_id, kept_ids, good_id, all_items)

    for entry_id, cap in state.bullet_caps.items():
        ref = facts.by_id(entry_id)

        if ref is None or ref.kind not in ("experience", "education", "project"):
            continue

        fact = _fact_for_entry(facts, entry_id, ref.kind)
        all_items = [
            (f"{entry_id}.b{index}", bullet)
            for index, bullet in enumerate(fact.bullets, start=1)
        ]
        all_items_map = dict(all_items)

        if entry_id in state.bullet_overrides:
            kept_texts = set(state.bullet_overrides[entry_id])
            kept_ids = [bid for bid, text in all_items if text in kept_texts]
        else:
            ordered = sort_bullets_by_priority(all_items, rank_map)
            kept_ids = [bid for bid, _text in ordered[:cap]]

        kept_id_set = set(kept_ids)
        dropped_items = [(bid, text) for bid, text in all_items if bid not in kept_id_set]
        figure_dropped = [(bid, text) for bid, text in dropped_items if _has_digit(text)]

        if not figure_dropped:
            continue

        figure_dropped.sort(key=lambda pair: rank_map[pair[0]].rank if pair[0] in rank_map else WORST_RANK)
        good_id, _good_text = figure_dropped[0]

        for bullet_id in kept_ids:
            text = all_items_map[bullet_id]

            if _has_digit(text):
                continue

            if _normalize(text) not in page1_text_normalized:
                continue

            rank = rank_map[bullet_id].rank if bullet_id in rank_map else WORST_RANK
            candidates.append((rank, entry_id, bullet_id, kept_ids, good_id, all_items))

    if not candidates:
        return False

    candidates.sort(key=lambda candidate: candidate[0], reverse=True)
    _rank, entry_id, bad_id, kept_ids, good_id, all_items = candidates[0]

    new_kept_ids = {good_id if bid == bad_id else bid for bid in kept_ids}
    all_items_map = dict(all_items)
    ordered_ids = [bid for bid, _text in all_items if bid in new_kept_ids]
    state.bullet_overrides[entry_id] = [all_items_map[bid] for bid in ordered_ids]

    return True


def enforce_figure_density_floor(
    facts: CVFacts,
    parsed_jd: ParsedJD,
    selection: CVSelection,
    state,
    profile: str,
    out_path: Path,
) -> DensityFloorResult:
    """
    After page-fit, check page-1 figure density. If below
    FIGURE_DENSITY_FLOOR, swap kept non-figure bullets for same-entry
    dropped figure bullets, worst-ranked kept bullet first, re-rendering
    after each swap, until the floor is met or no swaps remain.
    """

    out_path = Path(out_path)
    section_order = resolve_section_order(selection)

    content = materialize(facts, parsed_jd, selection, state, profile)
    docx_path = render_cv(content, out_path, section_order=section_order)
    pdf_path, converter_detail = convert_to_pdf(docx_path)

    if pdf_path is None:
        raise RuntimeError(f"Cannot measure figure density -- no PDF converter available: {converter_detail}")

    digit_count, page1_count = page1_bullet_digit_stats(content, pdf_path)
    density_before = digit_count / page1_count if page1_count else 1.0
    density = density_before
    swap_count = 0

    for _iteration in range(MAX_SWAP_ITERATIONS):
        if density >= FIGURE_DENSITY_FLOOR:
            break

        import pymupdf

        pdf = pymupdf.open(str(pdf_path))
        page1_text_normalized = _normalize(pdf[0].get_text()) if pdf.page_count else ""
        pdf.close()

        if not _try_one_swap(facts, selection, state, page1_text_normalized):
            break

        swap_count += 1

        content = materialize(facts, parsed_jd, selection, state, profile)
        docx_path = render_cv(content, out_path, section_order=section_order)
        pdf_path, converter_detail = convert_to_pdf(docx_path)

        if pdf_path is None:
            raise RuntimeError(f"Cannot measure figure density -- no PDF converter available: {converter_detail}")

        digit_count, page1_count = page1_bullet_digit_stats(content, pdf_path)
        density = digit_count / page1_count if page1_count else 1.0

    return DensityFloorResult(
        content=content,
        docx_path=str(docx_path),
        pdf_path=str(pdf_path),
        density_before=density_before,
        density_after=density,
        swap_count=swap_count,
    )
