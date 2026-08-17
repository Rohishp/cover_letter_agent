import json
import sys
from datetime import date, datetime
from pathlib import Path

from control_plane.application_paths import resolve_application_dir
from control_plane.reporting import (
    build_cover_letter_run_summary,
    print_final_result,
    print_jd_cache_status,
    print_match_breakdown,
    print_rejection_report,
    print_retry_notices,
)
from cv.facts import load_facts
from cv.generate import build_cv_run_summary, generate_cv
from pipeline import run_pipeline


CV_FACTS_PATH = "input/cv_facts.yaml"
DEFAULT_CV_PATH = "resume/Rohish_Resume.pdf"


def apply(jd_text: str) -> Path:
    """
    One JD parse (via run_pipeline's own cache-aware parsing), the
    existing cover-letter pipeline's match gate, and -- only on a pass --
    the existing CV generator, both writing into one application folder.
    Reuses run_pipeline() and generate_cv() as-is; no gate or generation
    logic is duplicated here.
    """

    state = run_pipeline(cv_path=DEFAULT_CV_PATH, jd_text=jd_text)

    if state.parsed_jd is not None:
        print_jd_cache_status(state)

    company_name = state.parsed_jd.company_name if state.parsed_jd else None
    job_title = state.parsed_jd.job_title if state.parsed_jd else None
    out_dir = resolve_application_dir(company_name, job_title, date.today())
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "jd.txt").write_text(jd_text, encoding="utf-8")

    summary = {
        "generated_at": datetime.now().isoformat(),
        "company_name": company_name,
        "job_title": job_title,
        "cover_letter": build_cover_letter_run_summary(state),
    }

    if state.status == "rejected":
        print_rejection_report(state)

        summary["rejection_reason"] = (
            state.error or "match gate rejected: deterministic scores below threshold"
        )

        (out_dir / "run.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        print()
        print("MATCH REJECTED -- no cover letter or CV generated.")
        print(f"Application folder: {out_dir}")

        return out_dir

    if state.match_analysis is not None:
        print_match_breakdown(state)
        print_retry_notices(state)

    print_final_result(state)

    if state.cover_letter:
        (out_dir / "cover_letter.txt").write_text(state.cover_letter, encoding="utf-8")

    facts = load_facts(CV_FACTS_PATH)
    cv_result = generate_cv(facts, state.parsed_jd, out_dir / "cv.docx")
    summary["cv"] = build_cv_run_summary(cv_result)

    (out_dir / "run.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print()
    print(f"Application folder: {out_dir}")
    print(f"CV page count: {cv_result.page_count}")

    return out_dir


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python apply.py <jd_text_file>")

    jd_text = Path(sys.argv[1]).read_text(encoding="utf-8").strip()

    if not jd_text:
        raise SystemExit(f"JD file is empty: {sys.argv[1]}")

    apply(jd_text)


if __name__ == "__main__":
    main()
