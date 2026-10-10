from pathlib import Path

from agents.cover_letter_writer import write_cover_letter
from agents.evaluator import evaluate_cover_letter
from agents.matcher import compare_cv_to_jd

from control_plane.eval_validation import validate_eval_result
from control_plane.jd_cache import (
create_jd_cache_key,
parse_jd_cached,
)
from control_plane.match_diagnostics import underrepresented_requirements
from control_plane.match_validation import validate_match_coverage
from control_plane.quality_gates import validate_jd_input_quality
from control_plane.scoring import compute_deterministic_match_scores
from control_plane.state import (
CoverLetterState,
PipelineStatus,
save_state,
)
from control_plane.thresholds import (
    EVAL_HOOK_MIN_SCORE,
    EVAL_PASS_THRESHOLD,
    MATCH_BASE_THRESHOLD,
    MATCH_CORE_THRESHOLD,
    MAX_COVER_LETTER_RETRIES,
)

from control_plane import storage

from cv.facts import CVFacts
from cv.selection_rules import requirement_evidence_fact_ids

from models.eval_schema import CoverLetterAttempt
from models.match_schema import MatchAnalysis


def _advance(state: CoverLetterState, status: PipelineStatus) -> None:
    """Every stage transition goes through here, so it is always persisted (invariant 4)."""

    state.update_status(status)
    save_state(state)


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


def run_pipeline(
jd_text: str,
facts: CVFacts,
applied_for_role: str,
force: bool = False,
strongest_evidence: str | None = None,
) -> CoverLetterState:
    """
    Run the complete CV → JD → Match → Cover Letter pipeline.

    This function contains all business logic.

    It is independent of:

    - CLI
    - FastAPI
    - clipboard
    - terminal

    Those interfaces simply call this function.

    force: an explicit, human-invoked override. It changes nothing about
    what should_generate_cover_letter computes or what the writer is
    told to do -- it only changes what happens after the gate function
    returns False. See the match gate below.

    strongest_evidence (item 6): the CV selection's top-ranked project, as
    plain text, passed straight through to the writer as a hint. Optional
    and caller-supplied (apply.py computes it).

    facts, applied_for_role: the CV fact base is the only CV evidence --
    the matcher, writer and evaluator all read it. (A parsed resume PDF
    was the source of the "AI Engineer at Agentic AI" fabrication and is
    no longer read at all.)
    """

    state = CoverLetterState()

    save_state(state)

    try:

        # 1. LOAD JD

        state.raw_jd_text = jd_text.strip()

        _advance(state, "jd_loaded")

        # 2. JD CACHE

        state.jd_cache_key = create_jd_cache_key(
            state.raw_jd_text
        )

        parsed_jd, state.jd_cache_hit = parse_jd_cached(
            state.raw_jd_text
        )

        state.parsed_jd = parsed_jd

        state.application_document_requirements = (
            parsed_jd.application_document_requirements.copy()
        )

        _advance(state, "jd_parsed")

        # 3. VALIDATE JD

        if not validate_jd_input_quality(state):

            save_state(state)

            return state

        _advance(state, "jd_validated")

        # 4. MATCH FACT BASE AGAINST JD

        _advance(state, "matching")

        match_analysis = compare_cv_to_jd(
            parsed_jd=state.parsed_jd,
            facts=facts,
        )

        # 5. VALIDATE MATCH COVERAGE

        validate_match_coverage(
            parsed_jd=state.parsed_jd,
            match=match_analysis,
        )

        # 6. DETERMINISTIC SCORING

        match_analysis = (
            compute_deterministic_match_scores(
                match_analysis
            )
        )

        state.match_analysis = match_analysis

        _advance(state, "match_complete")

        # 7. MATCH GATE

        gate_passed = should_generate_cover_letter(
            match_analysis
        )

        if not gate_passed and not force:

            state.match_gate_result = "would_have_rejected"

            _advance(state, "rejected")

            return state

        if not gate_passed and force:

            state.forced = True
            state.match_gate_result = "would_have_rejected"


        else:

            state.match_gate_result = "passed"

        save_state(state)

        # MATCH PASSED (OR FORCED)

        # 8. COVER LETTER LOOP

        # Computed once: which fact-base IDs evidence each of the JD's own
        # requirement terms. Reused every retry iteration below to turn an
        # underrepresented requirement into a fact-ID citation, never a
        # bare term (Phase H item 3 -- a bare-term nudge with no grounded
        # evidence is what caused the writer to invent a job role).
        requirement_evidence = requirement_evidence_fact_ids(
            facts, state.parsed_jd, raw_jd_text=state.raw_jd_text
        )

        while (
            state.retry_count
            <= MAX_COVER_LETTER_RETRIES
        ):

            attempt_number = (
                state.retry_count + 1
            )

            # WRITE

            _advance(state, "writing_cover_letter")

            underrepresented_hint = [
                {
                    "jd_requirement": item["jd_requirement"],
                    "fact_ids": requirement_evidence[item["jd_requirement"]],
                }
                for item in state.underrepresented_requirements
                if item["jd_requirement"] in requirement_evidence
            ]

            state.cover_letter = (
                write_cover_letter(
                    facts=facts,
                    parsed_jd=state.parsed_jd,
                    match_analysis=state.match_analysis,
                    applied_for_role=applied_for_role,
                    eval_feedback=state.eval_feedback,
                    strongest_evidence=strongest_evidence,
                    underrepresented_requirements_hint=underrepresented_hint,
                )
            )

            _advance(state, "cover_letter_ready")

            # EVALUATE

            _advance(state, "evaluating_cover_letter")

            eval_result = (
                evaluate_cover_letter(
                    cover_letter=state.cover_letter,
                    facts=facts,
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

            # UNDERREPRESENTED REQUIREMENTS (Phase G item 2): drives one
            # retry with explicit guidance, same ceiling as eval-driven
            # retries below -- see the acceptance condition further down.

            state.underrepresented_requirements = (
                underrepresented_requirements(
                    match=state.match_analysis,
                    cover_letter_text=state.cover_letter,
                )
            )

            # SAVE ATTEMPT

            state.cover_letter_attempts.append(

                CoverLetterAttempt(
                    attempt_number=attempt_number,
                    cover_letter=state.cover_letter,
                    eval_result=eval_result,
                )

            )

            _advance(state, "evaluation_complete")

            # PASSED EVALUATION

            eval_passed = (
                state.eval_score
                >= EVAL_PASS_THRESHOLD
                and eval_result.hook.score
                >= EVAL_HOOK_MIN_SCORE
            )

            is_final_attempt = (
                state.retry_count
                >= MAX_COVER_LETTER_RETRIES
            )

            # A residual underrepresented requirement on the final
            # allowed attempt still accepts the letter -- it's a
            # missed-case risk, not a fabrication risk (unlike the
            # writer's own hard-fail checks), so it should never itself
            # destroy an otherwise-passing letter. It stays visible in
            # state.underrepresented_requirements either way.
            if eval_passed and (not state.underrepresented_requirements or is_final_attempt):

                _advance(state, "completed")

                state.cover_letter_key = storage.write_text(
                    f"cover_letters/{state.run_id}.txt",
                    state.cover_letter,
                )

                save_state(state)

                return state

            # FAILED BUT RETRY AVAILABLE

            if is_final_attempt:
                break

            state.retry_count += 1

            save_state(state)

        # MAXIMUM RETRIES EXHAUSTED

        state.set_error(
            "Cover letter failed evaluation after "
            f"{MAX_COVER_LETTER_RETRIES} retries. "
            f"Final score: {state.eval_score}."
        )

        save_state(state)

        return state

    # UNEXPECTED EXCEPTION

    except Exception as error:

        state.set_error(
            str(error)
        )

        save_state(state)

        return state
