import json
import sys
from datetime import date, datetime
from pathlib import Path

import pyperclip

from pipeline import run_pipeline
from control_plane.application_paths import resolve_application_dir
from control_plane.reporting import (
    build_cover_letter_run_summary,
    print_jd_cache_status,
    print_match_breakdown,
    print_rejection_report,
    print_retry_notices,
    print_final_result,
)


DEFAULT_CV_PATH = "resume/Rohish_Resume.pdf"


def read_jd_from_file(path: str) -> str:
    text = Path(path).read_text(encoding="utf-8")

    if not text.strip():
        raise ValueError(f"JD file is empty: {path}")

    return text.strip()


def read_jd_from_clipboard() -> str:
    text = pyperclip.paste()

    if not text or not text.strip():
        raise ValueError(
            "Clipboard is empty. Copy the complete job description first."
        )

    return text.strip()


def report(state) -> None:
    if state.parsed_jd is not None:
        print_jd_cache_status(state)

    if state.match_analysis is not None:
        if state.status == "rejected":
            print_rejection_report(state)
        else:
            print_match_breakdown(state)
            print_retry_notices(state)

    print_final_result(state)


def main() -> None:
    jd_text = (
        read_jd_from_file(sys.argv[1])
        if len(sys.argv) > 1
        else read_jd_from_clipboard()
    )

    state = run_pipeline(
        cv_path=DEFAULT_CV_PATH,
        jd_text=jd_text,
    )

    report(state)

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
    (out_dir / "run.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    if state.cover_letter:
        (out_dir / "cover_letter.txt").write_text(state.cover_letter, encoding="utf-8")

        print()
        print(f"Also written to: {out_dir / 'cover_letter.txt'}")


if __name__ == "__main__":
    main()
