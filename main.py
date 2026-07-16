import argparse
from pathlib import Path

from agents.cover_letter_writer import write_cover_letter
from agents.cv_parser import extract_pdf_text, parse_cv
from agents.evaluator import evaluate_cover_letter
from agents.jd_parser import parse_jd, read_clipboard_windows
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
from control_plane.state import CoverLetterState, save_state

from models.eval_schema import CoverLetterAttempt
from models.match_schema import MatchAnalysis


MATCH_BASE_THRESHOLD = 65
MATCH_CORE_THRESHOLD = 60

EVAL_PASS_THRESHOLD = 70
MAX_COVER_LETTER_RETRIES = 2


def should_generate_cover_letter(
    match: MatchAnalysis,
) -> bool:
    if match.base_score is None:
        raise ValueError(
            "base_score is missing. Run deterministic scoring first."
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


def save_cover_letter_text(
    run_id: str,
    cover_letter: str,
) -> Path:
    output_dir = Path("output/cover_letters")
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = output_dir / f"{run_id}_cover_letter.txt"

    with open(path, "w", encoding="utf-8") as file:
        file.write(cover_letter)

    return path


def print_match_breakdown(
    match: MatchAnalysis,
) -> None:
    print("Deterministic score breakdown:")
    print(
        f"- core_must_have_score: {match.core_must_have_score} "
        f"/ required {MATCH_CORE_THRESHOLD}"
    )
    print(f"- eligibility_score: {match.eligibility_score}")
    print(f"- supporting_score: {match.supporting_score}")
    print(
        f"- base_score: {match.base_score} "
        f"/ required {MATCH_BASE_THRESHOLD}"
    )
    print(
        f"- nice_to_have_score: {match.nice_to_have_score} "
        "(bonus only)"
    )
    print(f"- overall_score with bonus: {match.overall_score}")
    print()
    print("LLM recommendation, informational only:")
    print(f"- recommendation: {match.recommendation}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the CV-JD matching, cover-letter generation, "
            "and evaluation pipeline."
        )
    )

    parser.add_argument(
        "--cv",
        required=True,
        type=str,
        help="Path to the CV PDF.",
    )

    parser.add_argument(
        "--jd-source",
        choices=["clipboard", "argument"],
        default="clipboard",
    )

    parser.add_argument(
        "--jd",
        type=str,
        default=None,
    )

    args = parser.parse_args()

    state = CoverLetterState(
        cv_path=args.cv,
        jd_source=args.jd_source,
    )

    save_state(state)

    try:
        # 1. Load CV text
        state.raw_cv_text = extract_pdf_text(args.cv)
        state.update_status("cv_loaded")
        save_state(state)

        # 2. Parse CV
        state.parsed_cv = parse_cv(state.raw_cv_text)
        state.update_status("cv_parsed")
        save_state(state)

        # 3. Load JD text
        if args.jd_source == "clipboard":
            raw_jd_text = read_clipboard_windows()

        elif args.jd_source == "argument":
            if not args.jd or not args.jd.strip():
                raise ValueError(
                    "--jd is required when --jd-source argument is used."
                )

            raw_jd_text = args.jd.strip()

        else:
            raise ValueError(
                f"Unsupported JD source: {args.jd_source}"
            )

        state.raw_jd_text = raw_jd_text
        state.update_status("jd_loaded")
        save_state(state)

        # 4. Load cached ParsedJD or parse once
        state.jd_cache_key = create_jd_cache_key(raw_jd_text)

        cached_jd = load_cached_jd(raw_jd_text)

        if cached_jd is not None:
            state.jd_cache_hit = True
            parsed_jd = cached_jd

            print("JD PARSE CACHE HIT.")
            print("Reusing previously parsed JD.")

        else:
            state.jd_cache_hit = False
            parsed_jd = parse_jd(raw_jd_text)

            cache_path = save_cached_jd(
                raw_jd=raw_jd_text,
                parsed_jd=parsed_jd,
            )

            print("JD PARSE CACHE MISS.")
            print(f"Parsed JD cached at: {cache_path}")

        state.parsed_jd = parsed_jd

        state.application_document_requirements = (
            parsed_jd.application_document_requirements.copy()
        )

        state.update_status("jd_parsed")
        save_state(state)

        # 5. Validate JD
        if not validate_jd_input_quality(state):
            save_state(state)

            print("JD INPUT VALIDATION FAILED.")
            print(state.summary)
            return

        state.update_status("jd_validated")
        save_state(state)

        # 6. Match CV against fixed JD requirements
        state.update_status("matching")
        save_state(state)

        match_analysis = compare_cv_to_jd(
            parsed_cv=state.parsed_cv,
            parsed_jd=state.parsed_jd,
        )

        validate_match_coverage(
            parsed_jd=state.parsed_jd,
            match=match_analysis,
        )

        match_analysis = compute_deterministic_match_scores(
            match_analysis
        )

        state.match_analysis = match_analysis
        state.update_status("match_complete")
        save_state(state)

        # 7. Match gate
        if not should_generate_cover_letter(match_analysis):
            state.update_status("rejected")
            save_state(state)

            print(
                "MATCH REJECTED: cover letter will not be generated."
            )
            print()

            print_match_breakdown(match_analysis)

            print("Pipeline summary:")
            print(state.summary)
            return

        print("MATCH PASSED.")
        print()
        print_match_breakdown(match_analysis)

        # 8. Writer and evaluator loop
        while state.retry_count <= MAX_COVER_LETTER_RETRIES:
            attempt_number = state.retry_count + 1

            print(
                f"Generating cover letter attempt {attempt_number}..."
            )

            state.update_status("writing_cover_letter")
            save_state(state)

            state.cover_letter = write_cover_letter(
                parsed_cv=state.parsed_cv,
                parsed_jd=state.parsed_jd,
                match_analysis=state.match_analysis,
                eval_feedback=state.eval_feedback,
            )

            state.update_status("cover_letter_ready")
            save_state(state)

            state.update_status("evaluating_cover_letter")
            save_state(state)

            eval_result = evaluate_cover_letter(
                cover_letter=state.cover_letter,
                parsed_cv=state.parsed_cv,
                parsed_jd=state.parsed_jd,
            )

            eval_result = validate_eval_result(
                cover_letter=state.cover_letter,
                eval_result=eval_result,
            )

            state.eval_result = eval_result
            state.eval_score = eval_result.overall_score
            state.eval_feedback = eval_result.feedback_text

            state.cover_letter_attempts.append(
                CoverLetterAttempt(
                    attempt_number=attempt_number,
                    cover_letter=state.cover_letter,
                    eval_result=eval_result,
                )
            )

            state.update_status("evaluation_complete")
            save_state(state)

            print(
                f"Evaluation score: "
                f"{state.eval_score}/{EVAL_PASS_THRESHOLD}"
            )

            if state.eval_score >= EVAL_PASS_THRESHOLD:
                state.update_status("completed")
                save_state(state)

                output_path = save_cover_letter_text(
                    run_id=state.run_id,
                    cover_letter=state.cover_letter,
                )

                print()
                print("COVER LETTER ACCEPTED.")
                print(f"Saved to: {output_path}")
                print()

                if state.application_document_requirements:
                    print("Required application documents:")
                    for requirement in (
                        state.application_document_requirements
                    ):
                        print(f"- {requirement}")
                    print()

                print(state.cover_letter)
                return

            if state.retry_count >= MAX_COVER_LETTER_RETRIES:
                break

            state.retry_count += 1
            save_state(state)

            print(
                f"Evaluation failed. Retrying "
                f"{state.retry_count}/{MAX_COVER_LETTER_RETRIES} "
                "using evaluator feedback."
            )
            print()

        # 9. Maximum retries reached
        state.set_error(
            "Cover letter failed evaluation after "
            f"{MAX_COVER_LETTER_RETRIES} retries. "
            f"Final score: {state.eval_score}."
        )

        save_state(state)

        print("COVER LETTER FAILED AFTER MAXIMUM RETRIES.")
        print()
        print("Final evaluator feedback:")
        print(state.eval_feedback)
        print()
        print(state.summary)

    except Exception as error:
        state.set_error(str(error))
        save_state(state)

        print()
        print("PIPELINE FAILED.")
        print(f"Error: {error}")
        print(f"Run ID: {state.run_id}")

        raise


if __name__ == "__main__":
    main()