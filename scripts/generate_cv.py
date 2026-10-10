import json
import sys
from datetime import date, datetime
from pathlib import Path

from agents.jd_parser import parse_jd
from control_plane.application_paths import resolve_application_dir
from cv.facts import load_facts
from cv.generate import build_cv_run_summary, generate_cv
from cv.page_fit import MAX_PAGES


FACTS_PATH = "input/cv_facts.yaml"


def _rank_label(rank: float | None) -> str:
    if rank is None:
        return "unranked"

    return f"rank {int(rank)}"


def print_selection_report(facts, selection_section_order, result) -> None:
    report = result.report

    print(f"Section order: {', '.join(selection_section_order)}")
    print(f"Reason: {report.section_order_reason}")
    print()

    exclusion_lines = []

    for note in report.excluded_projects:
        exclusion_lines.append(
            f'- project "{note.label}" ({_rank_label(note.rank)} of '
            f"{len(facts.projects.entries)}, {note.reason})"
        )

    if report.excluded_skill_groups:
        labels = ", ".join(note.label for note in report.excluded_skill_groups)
        exclusion_lines.append(f"- skill groups: {labels}")

    for note in report.excluded_bullets:
        exclusion_lines.append(f"- {note.id} ({_rank_label(note.rank)}, {note.reason})")

    if exclusion_lines:
        print(f"Excluded to fit {MAX_PAGES} pages:")
        for line in exclusion_lines:
            print(line)
        print()

    print(
        f"Page 1 figure density before swaps: {result.density_before:.0%}  "
        f"after swaps: {result.density_after:.0%}  (floor 50%, {result.swap_count} swap(s))"
    )


def run(jd_text: str, out_dir: Path | None = None) -> tuple[dict, Path]:
    """
    Runs the full CV generation flow and writes cv.docx/cv.pdf into
    out_dir (creating it if needed). Returns (result-as-dict-ish, out_dir)
    for callers (e.g. apply.py) that need the pieces without re-parsing
    stdout.
    """

    facts = load_facts(FACTS_PATH)
    parsed_jd = parse_jd(jd_text)

    if out_dir is None:
        out_dir = resolve_application_dir(parsed_jd.company_name, parsed_jd.job_title, date.today())

    out_dir.mkdir(parents=True, exist_ok=True)

    result = generate_cv(facts, parsed_jd, out_dir / "cv.docx")

    (out_dir / "jd.txt").write_text(jd_text, encoding="utf-8")

    summary = {
        "generated_at": datetime.now().isoformat(),
        "company_name": parsed_jd.company_name,
        "job_title": parsed_jd.job_title,
        "cv": build_cv_run_summary(result),
    }
    (out_dir / "run.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return facts, parsed_jd, result, out_dir


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/generate_cv.py <jd_text_file>")

    jd_text = Path(sys.argv[1]).read_text(encoding="utf-8").strip()

    if not jd_text:
        raise SystemExit(f"JD file is empty: {sys.argv[1]}")

    facts, parsed_jd, result, out_dir = run(jd_text)

    print(f"Application folder: {out_dir}")
    print(f"Rendered: {out_dir / 'cv.docx'}")
    print(f"PDF: {out_dir / 'cv.pdf'}")
    print(f"Page count: {result.page_count}")
    print()

    print_selection_report(facts, result.report.section_order[1:-3], result)
    print()

    print("Check results:")
    for check_id, passed, detail in result.check_results:
        status = "SKIP" if passed is None else ("PASS" if passed else "FAIL")
        print(f"[{status}] {check_id}: {detail}")

    failed = [r for r in result.check_results if r[1] is False]

    print()
    print(f"{len(result.check_results) - len(failed)}/{len(result.check_results)} checks passed.")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
