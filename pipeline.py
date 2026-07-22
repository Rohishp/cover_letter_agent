from pathlib import Path

from agents.cover_letter_writer import write_cover_letter
from agents.cv_parser import extract_pdf_text, parse_cv, load_cv_from_s3
from agents.evaluator import evaluate_cover_letter
from agents.jd_parser import parse_jd
from agents.matcher import compare_cv_to_jd

from control_plane.eval_validation import validate_eval_result
from control_plane.jd_cache import (
create_jd_cache_key,
load_cached_jd,
save_cached_jd,
)
from control_plane.match_validation import validate_match_coverage
from control_plane.quality_gates import validate_jd_input_quality
from control_plane.scoring import compute_deterministic_match_scores
from control_plane.state import (
CoverLetterState,
save_state,
)

from control_plane.cover_letter_storage import (
    save_cover_letter_to_s3,
)

from models.eval_schema import CoverLetterAttempt
from models.match_schema import MatchAnalysis


MATCH_BASE_THRESHOLD = 65
MATCH_CORE_THRESHOLD = 60

EVAL_PASS_THRESHOLD = 70
MAX_COVER_LETTER_RETRIES = 2



def should_generate_cover_letter(
    match: MatchAnalysis,
) -> bool:
    """
    Deterministic gate.

    The LLM recommendation is informational only.
    Generation is controlled entirely by deterministic scores.
    """

    if match.base_score is None:
        raise ValueError(
            "base_score is missing. "
            "Run deterministic scoring first."
        )

    if match.core_must_have_score is None:
        raise ValueError(
            "core_must_have_score is missing. "
            "Run deterministic scoring first."
        )

    return (
        match.base_score >= MATCH_BASE_THRESHOLD
        and match.core_must_have_score >= MATCH_CORE_THRESHOLD
    )



def print_match_breakdown(
match: MatchAnalysis,
) -> None:

    print("Deterministic score breakdown:")

    print(
        f"- core_must_have_score: "
        f"{match.core_must_have_score} "
        f"/ required {MATCH_CORE_THRESHOLD}"
    )

    print(
        f"- eligibility_score: "
        f"{match.eligibility_score}"
    )

    print(
        f"- supporting_score: "
        f"{match.supporting_score}"
    )

    print(
        f"- base_score: "
        f"{match.base_score} "
        f"/ required {MATCH_BASE_THRESHOLD}"
    )

    print(
        f"- nice_to_have_score: "
        f"{match.nice_to_have_score} "
        "(bonus only)"
    )

    print(
        f"- overall_score with bonus: "
        f"{match.overall_score}"
    )

    print()

    print("LLM recommendation (informational only):")

    print(
        f"- recommendation: "
        f"{match.recommendation}"
    )

    print()

def run_pipeline(
cv_path: str,
jd_text: str,
) -> CoverLetterState:
    """
    Run the complete CV → JD → Match → Cover Letter pipeline.

    This function contains all business logic.

    It is independent of:

    - CLI
    - AWS Lambda
    - FastAPI
    - clipboard
    - terminal

    Those interfaces simply call this function.
    """

    state = CoverLetterState(
        cv_path=f"s3://cover-letter-agent/{cv_path}"
    )

    save_state(state)

    try:

        ###########################################################
        # 1. LOAD CV
        ###########################################################

        state.raw_cv_text = load_cv_from_s3(
        bucket="cover-letter-agent",
        key=cv_path,
    )

        state.update_status("cv_loaded")

        save_state(state)

        ###########################################################
        # 2. PARSE CV
        ###########################################################

        state.parsed_cv = parse_cv(
            state.raw_cv_text
        )

        state.update_status("cv_parsed")

        save_state(state)

        ###########################################################
        # 3. LOAD JD
        ###########################################################

        state.raw_jd_text = jd_text.strip()

        state.update_status("jd_loaded")

        save_state(state)

        ###########################################################
        # 4. JD CACHE
        ###########################################################

        state.jd_cache_key = create_jd_cache_key(
            state.raw_jd_text
        )

        cached_jd = load_cached_jd(
            state.raw_jd_text
        )

        if cached_jd is not None:

            state.jd_cache_hit = True

            parsed_jd = cached_jd

            print("JD PARSE CACHE HIT.")

        else:

            state.jd_cache_hit = False

            parsed_jd = parse_jd(
                state.raw_jd_text
            )

            cache_path = save_cached_jd(
                raw_jd=state.raw_jd_text,
                parsed_jd=parsed_jd,
            )

            print("JD PARSE CACHE MISS.")
            print(
                f"Parsed JD cached at: "
                f"{cache_path}"
            )

        state.parsed_jd = parsed_jd

        state.application_document_requirements = (
            parsed_jd.application_document_requirements.copy()
        )

        state.update_status("jd_parsed")

        save_state(state)

        ###########################################################
        # 5. VALIDATE JD
        ###########################################################

        if not validate_jd_input_quality(state):

            save_state(state)

            return state

        state.update_status(
            "jd_validated"
        )

        save_state(state)

        ###########################################################
        # 6. MATCH CV AGAINST JD
        ###########################################################

        state.update_status(
            "matching"
        )

        save_state(state)

        match_analysis = compare_cv_to_jd(
            parsed_cv=state.parsed_cv,
            parsed_jd=state.parsed_jd,
        )

        ###########################################################
        # 7. VALIDATE MATCH COVERAGE
        ###########################################################

        validate_match_coverage(
            parsed_jd=state.parsed_jd,
            match=match_analysis,
        )

        ###########################################################
        # 8. DETERMINISTIC SCORING
        ###########################################################

        match_analysis = (
            compute_deterministic_match_scores(
                match_analysis
            )
        )

        state.match_analysis = match_analysis

        state.update_status(
            "match_complete"
        )

        save_state(state)

        ###########################################################
        # 9. MATCH GATE
        ###########################################################

        if not should_generate_cover_letter(
            match_analysis
        ):

            state.update_status(
                "rejected"
            )

            save_state(state)

            print()

            print(
                "MATCH REJECTED:"
            )

            print_match_breakdown(
                match_analysis
            )

            return state

        ###########################################################
        # MATCH PASSED
        ###########################################################

        print()

        print(
            "MATCH PASSED."
        )

        print_match_breakdown(
            match_analysis
        )

        ###########################################################
        # 10. COVER LETTER LOOP
        ###########################################################

        while (
            state.retry_count
            <= MAX_COVER_LETTER_RETRIES
        ):

            attempt_number = (
                state.retry_count + 1
            )

            print()

            print(
                "Generating cover letter "
                f"attempt {attempt_number}..."
            )

            ###################################################
            # WRITE
            ###################################################

            state.update_status(
                "writing_cover_letter"
            )

            save_state(state)

            state.cover_letter = (
                write_cover_letter(
                    parsed_cv=state.parsed_cv,
                    parsed_jd=state.parsed_jd,
                    match_analysis=state.match_analysis,
                    eval_feedback=state.eval_feedback,
                )
            )

            state.update_status(
                "cover_letter_ready"
            )

            save_state(state)

            ###################################################
            # EVALUATE
            ###################################################

            state.update_status(
                "evaluating_cover_letter"
            )

            save_state(state)

            eval_result = (
                evaluate_cover_letter(
                    cover_letter=state.cover_letter,
                    parsed_cv=state.parsed_cv,
                    parsed_jd=state.parsed_jd,
                )
            )

            eval_result = (
                validate_eval_result(
                    cover_letter=state.cover_letter,
                    eval_result=eval_result,
                )
            )

            state.eval_result = (
                eval_result
            )

            state.eval_score = (
                eval_result.overall_score
            )

            state.eval_feedback = (
                eval_result.feedback_text
            )

            ###################################################
            # SAVE ATTEMPT
            ###################################################

            state.cover_letter_attempts.append(

                CoverLetterAttempt(
                    attempt_number=attempt_number,
                    cover_letter=state.cover_letter,
                    eval_result=eval_result,
                )

            )

            state.update_status(
                "evaluation_complete"
            )

            save_state(state)

            print(
                f"Evaluation score: "
                f"{state.eval_score}"
                f"/{EVAL_PASS_THRESHOLD}"
            )
            ###################################################
            # PASSED EVALUATION
            ###################################################

            if (
                state.eval_score
                >= EVAL_PASS_THRESHOLD
            ):

                state.update_status(
                    "completed"
                )

                save_state(state)

                cover_letter_key = save_cover_letter_to_s3(
                    run_id=state.run_id,
                    cover_letter=state.cover_letter,
                )

                state.cover_letter_s3_key = cover_letter_key

                save_state(state)

                print()

                print(
                    "COVER LETTER ACCEPTED."
                )

                print(
                    f"Saved to S3: {cover_letter_key}"
                )

                print()

                if (
                    state.application_document_requirements
                ):

                    print(
                        "Required application documents:"
                    )

                    for requirement in (
                        state.application_document_requirements
                    ):

                        print(
                            f"- {requirement}"
                        )

                    print()

                print(
                    state.cover_letter
                )

                return state

            ###################################################
            # FAILED BUT RETRY AVAILABLE
            ###################################################

            if (
                state.retry_count
                >= MAX_COVER_LETTER_RETRIES
            ):
                break

            state.retry_count += 1

            save_state(state)

            print()

            print(
                "Evaluation failed."
            )

            print(
                f"Retry "
                f"{state.retry_count}"
                f"/"
                f"{MAX_COVER_LETTER_RETRIES}"
            )

            print(
                "Using evaluator feedback "
                "for regeneration."
            )

        ###########################################################
        # MAXIMUM RETRIES EXHAUSTED
        ###########################################################

        state.set_error(
            "Cover letter failed evaluation after "
            f"{MAX_COVER_LETTER_RETRIES} retries. "
            f"Final score: {state.eval_score}."
        )

        save_state(state)

        print()

        print(
            "COVER LETTER FAILED."
        )

        print()

        print(
            "Final evaluator feedback:"
        )

        print(
            state.eval_feedback
        )

        print()

        return state

    ###############################################################
    # UNEXPECTED EXCEPTION
    ###############################################################

    except Exception as error:

        state.set_error(
            str(error)
        )

        save_state(state)

        print()

        print(
            "PIPELINE FAILED."
        )

        print(
            f"Error: {error}"
        )

        print(
            f"Run ID: {state.run_id}"
        )

        return state

