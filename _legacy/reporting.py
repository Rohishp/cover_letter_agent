from control_plane.jd_cache import get_jd_cache_key
from control_plane.match_diagnostics import (
    BAND_NOISE_MARGIN,
    hard_gaps,
    match_band,
    shaky_requirements,
    weak_requirements,
)
from control_plane.state import CoverLetterState

from control_plane.thresholds import (
    EVAL_PASS_THRESHOLD,
    MATCH_BASE_THRESHOLD,
    MATCH_CORE_THRESHOLD,
    MAX_COVER_LETTER_RETRIES,
)


def print_jd_cache_status(state: CoverLetterState) -> None:
    if state.jd_cache_hit:
        print("JD PARSE CACHE HIT.")
    else:
        print("JD PARSE CACHE MISS.")
        print(f"Parsed JD cached at: {get_jd_cache_key(state.raw_jd_text)}")


def _print_score_breakdown(state: CoverLetterState) -> None:
    match = state.match_analysis

    print("Deterministic score breakdown:")

    print(
        f"- core_must_have_score: "
        f"{match.core_must_have_score} "
        f"/ required {MATCH_CORE_THRESHOLD}"
    )

    print(f"- eligibility_score: {match.eligibility_score}")

    print(f"- supporting_score: {match.supporting_score}")

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

    print(f"- overall_score with bonus: {match.overall_score}")

    print()

    band = match_band(match, MATCH_BASE_THRESHOLD, MATCH_CORE_THRESHOLD)

    print(
        f"Fit band: {band.upper()} "
        f"(scores vary ~{BAND_NOISE_MARGIN} points between runs on the same inputs)"
    )

    shaky = shaky_requirements(match)

    if shaky:
        print("Likely to change between runs (core requirements not judged strong):")

        for requirement in shaky:
            print(f"- {requirement}")

    gaps = hard_gaps(match)

    if gaps:
        print("Hard gaps (core requirements with no CV evidence):")

        for gap in gaps:
            print(f"- {gap['jd_requirement']}: {gap['gap_note'] or 'no gap note provided'}")

    print()

    print("LLM recommendation (informational only):")

    print(f"- recommendation: {match.recommendation}")

    print()


def print_match_breakdown(state: CoverLetterState) -> None:
    print()
    print("MATCH PASSED.")
    _print_score_breakdown(state)


def print_weak_requirements(match) -> None:
    weak = weak_requirements(match)

    if not weak:
        return

    print("Weak requirements:")

    for item in weak:
        gap = item["gap_note"] or "no gap note provided"
        print(f"- [{item['category']}] {item['jd_requirement']} ({item['strength']}): {gap}")

    print()


def print_forced_notice(state: CoverLetterState) -> None:
    match = state.match_analysis

    print()
    print("FORCED GENERATION -- MATCH GATE WOULD HAVE REJECTED")
    print(f"base_score: {match.base_score} (required {MATCH_BASE_THRESHOLD})")
    print(f"core_must_have_score: {match.core_must_have_score} (required {MATCH_CORE_THRESHOLD})")
    print()
    print_weak_requirements(match)


def print_rejection_report(state: CoverLetterState) -> None:
    print()
    print("MATCH REJECTED:")
    _print_score_breakdown(state)
    print_weak_requirements(state.match_analysis)


def print_retry_notices(state: CoverLetterState) -> None:
    attempts = state.cover_letter_attempts

    for index, attempt in enumerate(attempts):
        print()

        print(
            "Generating cover letter "
            f"attempt {attempt.attempt_number}..."
        )

        print(
            f"Evaluation score: "
            f"{attempt.eval_result.overall_score}"
            f"/{EVAL_PASS_THRESHOLD}"
        )

        is_last_attempt = index == len(attempts) - 1

        if not is_last_attempt:
            print()
            print("Evaluation failed.")
            print(f"Retry {attempt.attempt_number}/{MAX_COVER_LETTER_RETRIES}")
            print("Using evaluator feedback for regeneration.")


def print_final_result(state: CoverLetterState) -> None:
    if state.status == "completed":
        print()
        print("COVER LETTER ACCEPTED.")
        print(f"Saved: {state.cover_letter_key}")
        print()

        if state.application_document_requirements:
            print("Required application documents:")

            for requirement in state.application_document_requirements:
                print(f"- {requirement}")

            print()

        print(state.cover_letter)

        return

    if state.status != "failed" or not state.error:
        return

    # Set only by validate_jd_input_quality's early, silent return.
    if state.error.startswith("JD validation failed:"):
        return

    # Set only after the cover-letter retry loop exhausts its attempts.
    if state.error.startswith("Cover letter failed evaluation after"):
        print()
        print("COVER LETTER FAILED.")
        print()
        print("Final evaluator feedback:")
        print(state.eval_feedback)
        print()
        return

    print()
    print("PIPELINE FAILED.")
    print(f"Error: {state.error}")
    print(f"Run ID: {state.run_id}")


def print_fact_base_coverage_report(coverage_gaps: list[dict]) -> None:
    """
    Phase H item 2: report-only, printed on every run. Never gates,
    never retries, never feeds generation -- only a human editing
    cv_facts.yaml can close a gap this surfaces.
    """

    if not coverage_gaps:
        return

    print()
    print(
        "Fact-base coverage gaps (not blocking -- edit cv_facts.yaml to close, "
        "never auto-generated):"
    )

    for gap in coverage_gaps:
        found_in = ", ".join(gap["found_in"])
        print(f"- {gap['requirement']} (present in: {found_in})")
        print(f"  {gap['suggestion']}")


COVER_LETTER_MODEL_SETTINGS = {
    "matcher_model": "gpt-4o",
    "matcher_temperature": 0,
    "matcher_seed": 42,
    "evaluator_model": "gpt-4o",
    "evaluator_temperature": 0,
    "evaluator_seed": 42,
    "writer_model": "gpt-4o",
    "writer_temperature": 0,
    "writer_seed": 42,
}


def build_cover_letter_run_summary(state: CoverLetterState) -> dict:
    """
    JSON-able summary of one cover-letter run: scores, status, and the
    model settings used. Used by apply.py for run.json.
    """

    match = state.match_analysis

    return {
        "run_id": state.run_id,
        "status": state.status,
        "match_scores": {
            "core_must_have_score": match.core_must_have_score if match else None,
            "eligibility_score": match.eligibility_score if match else None,
            "supporting_score": match.supporting_score if match else None,
            "nice_to_have_score": match.nice_to_have_score if match else None,
            "base_score": match.base_score if match else None,
            "overall_score": match.overall_score if match else None,
        },
        "weak_requirements": weak_requirements(match) if match else [],
        "eval_score": state.eval_score,
        "retry_count": state.retry_count,
        "cover_letter_key": state.cover_letter_key,
        "forced": state.forced,
        "match_gate_result": state.match_gate_result,
        "underrepresented_requirements": state.underrepresented_requirements,
        "error": state.error,
        "model_settings": COVER_LETTER_MODEL_SETTINGS,
    }
