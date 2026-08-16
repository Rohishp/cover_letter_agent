from pipeline import run_pipeline
from control_plane.reporting import (
    print_jd_cache_status,
    print_match_breakdown,
    print_rejection_report,
    print_retry_notices,
    print_final_result,
)

DEFAULT_CV_PATH = "resume/Rohish_Resume.pdf"

def handler(event, context):

    jd_text = event["jd_text"]

    cv_path = event.get(
        "cv_path",
        DEFAULT_CV_PATH,
    )

    state = run_pipeline(
        cv_path=cv_path,
        jd_text=jd_text,
    )

    if state.parsed_jd is not None:
        print_jd_cache_status(state)

    if state.match_analysis is not None:
        if state.status == "rejected":
            print_rejection_report(state)
        else:
            print_match_breakdown(state)
            print_retry_notices(state)

    print_final_result(state)

    return {
        "run_id": state.run_id,
        "status": state.status,
        "summary": state.summary,
        "cover_letter": state.cover_letter,
    }