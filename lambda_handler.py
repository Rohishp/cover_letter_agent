from pipeline import run_pipeline

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

    return {
        "run_id": state.run_id,
        "status": state.status,
        "summary": state.summary,
        "cover_letter": state.cover_letter,
    }