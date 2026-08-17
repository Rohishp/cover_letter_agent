import sys
from pathlib import Path

import pyperclip

from pipeline import run_pipeline
from control_plane.reporting import (
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

    if state.cover_letter:
        out_path = Path("output") / f"{state.run_id}.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(state.cover_letter, encoding="utf-8")

        print()
        print(f"Also written to: {out_path}")


if __name__ == "__main__":
    main()
