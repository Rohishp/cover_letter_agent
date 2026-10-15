import re
from dataclasses import dataclass

from agents.cover_letter_writer import write_cover_letter
from agents.evaluator import evaluate_cover_letter
from agents.matcher import compare_cv_to_jd
from control_plane import storage
from control_plane.eval_validation import validate_eval_result
from control_plane.jd_cache import create_jd_cache_key, parse_jd_cached
from control_plane.match_diagnostics import underrepresented_requirements
from control_plane.match_validation import validate_match_coverage
from control_plane.quality_gates import validate_jd_input_quality
from control_plane.scoring import compute_deterministic_match_scores
from control_plane.state import CoverLetterState, PipelineStatus, save_state
from control_plane.thresholds import (
    EVAL_HOOK_MIN_SCORE,
    EVAL_PASS_THRESHOLD,
    MATCH_BASE_THRESHOLD,
    MATCH_CORE_THRESHOLD,
    MAX_COVER_LETTER_RETRIES,
)
from cv.facts import CVFacts
from cv.selection_rules import requirement_evidence_fact_ids
from models.eval_schema import CoverLetterAttempt
from models.match_schema import MatchAnalysis


_API_KEY = re.compile(r"sk-[A-Za-z0-9_-]+")


def redact(text: str) -> str:
    """SDK errors can echo a (masked) API key; never persist or show it."""

    return _API_KEY.sub("sk-***", text)


@dataclass
class Inputs:
    facts: CVFacts
    applied_for_role: str
    force: bool
    strongest_evidence: str | None
    draft: str | None = None  # a letter written outside OpenAI: evaluated once, never retried here


def _advance(state: CoverLetterState, status: PipelineStatus) -> None:
    """Every stage transition goes through here, so it is always persisted (invariant 4)."""

    state.update_status(status)
    save_state(state)


def should_generate_cover_letter(match: MatchAnalysis) -> bool:
    """Deterministic gate. The LLM recommendation is informational only."""

    if match.base_score is None or match.core_must_have_score is None:
        raise ValueError("Match scores are missing. Run deterministic scoring first.")

    return (
        match.base_score >= MATCH_BASE_THRESHOLD
        and match.core_must_have_score >= MATCH_CORE_THRESHOLD
    )


# Stages: each takes (state, inputs) and returns True to end the run early.

def parse_jd_stage(state: CoverLetterState, _inputs: Inputs) -> bool:
    state.jd_cache_key = create_jd_cache_key(state.raw_jd_text)
    state.parsed_jd, state.jd_cache_hit = parse_jd_cached(state.raw_jd_text)
    state.application_document_requirements = (
        state.parsed_jd.application_document_requirements.copy()
    )
    _advance(state, "jd_parsed")
    return False


def validate_jd(state: CoverLetterState, _inputs: Inputs) -> bool:
    if not validate_jd_input_quality(state):
        save_state(state)
        return True

    _advance(state, "jd_validated")
    return False


def match_stage(state: CoverLetterState, inputs: Inputs) -> bool:
    _advance(state, "matching")
    analysis = compare_cv_to_jd(parsed_jd=state.parsed_jd, facts=inputs.facts)
    validate_match_coverage(parsed_jd=state.parsed_jd, match=analysis)
    state.match_analysis = compute_deterministic_match_scores(analysis)
    _advance(state, "match_complete")
    return False


def gate(state: CoverLetterState, inputs: Inputs) -> bool:
    """Python decides. `force` only changes what happens after a failed gate."""

    if should_generate_cover_letter(state.match_analysis):
        state.match_gate_result = "passed"
        save_state(state)
        return False

    state.match_gate_result = "would_have_rejected"

    if not inputs.force:
        _advance(state, "rejected")
        return True

    state.forced = True
    save_state(state)
    return False


def _attempt(state: CoverLetterState, inputs: Inputs, requirement_evidence: dict) -> bool:
    """One write + evaluate round. Returns whether the letter passed evaluation."""

    _advance(state, "writing_cover_letter")

    # A fact-ID citation, never a bare term: a bare-term nudge with no grounded
    # evidence is what once made the writer invent a job role.
    hint = [
        {"jd_requirement": item["jd_requirement"], "fact_ids": requirement_evidence[item["jd_requirement"]]}
        for item in state.underrepresented_requirements
        if item["jd_requirement"] in requirement_evidence
    ]

    state.cover_letter = inputs.draft if inputs.draft is not None else write_cover_letter(
        facts=inputs.facts,
        parsed_jd=state.parsed_jd,
        match_analysis=state.match_analysis,
        applied_for_role=inputs.applied_for_role,
        eval_feedback=state.eval_feedback,
        strongest_evidence=inputs.strongest_evidence,
        underrepresented_requirements_hint=hint,
    )
    _advance(state, "cover_letter_ready")

    _advance(state, "evaluating_cover_letter")
    result = validate_eval_result(
        cover_letter=state.cover_letter,
        eval_result=evaluate_cover_letter(
            cover_letter=state.cover_letter,
            facts=inputs.facts,
            parsed_jd=state.parsed_jd,
        ),
    )
    state.eval_result = result
    state.eval_score = result.overall_score
    state.eval_feedback = result.feedback_text
    state.underrepresented_requirements = underrepresented_requirements(
        match=state.match_analysis, cover_letter_text=state.cover_letter
    )
    state.cover_letter_attempts.append(
        CoverLetterAttempt(
            attempt_number=state.retry_count + 1,
            cover_letter=state.cover_letter,
            eval_result=result,
        )
    )
    _advance(state, "evaluation_complete")

    return state.eval_score >= EVAL_PASS_THRESHOLD and result.hook.score >= EVAL_HOOK_MIN_SCORE


def write_and_evaluate(state: CoverLetterState, inputs: Inputs) -> bool:
    requirement_evidence = requirement_evidence_fact_ids(
        inputs.facts, state.parsed_jd, raw_jd_text=state.raw_jd_text
    )

    while True:
        passed = _attempt(state, inputs, requirement_evidence)
        is_final = inputs.draft is not None or state.retry_count >= MAX_COVER_LETTER_RETRIES

        # A residual underrepresented requirement on the final attempt still accepts
        # the letter: a missed-case risk, not a fabrication risk. It stays visible
        # in state.underrepresented_requirements.
        if passed and (not state.underrepresented_requirements or is_final):
            _advance(state, "completed")
            state.cover_letter_key = storage.write_text(
                f"cover_letters/{state.run_id}.txt", state.cover_letter
            )
            save_state(state)
            return True

        if is_final:
            state.set_error(
                f"Cover letter failed evaluation after {state.retry_count} "
                f"retries. Final score: {state.eval_score}."
            )
            save_state(state)
            return True

        state.retry_count += 1
        save_state(state)


STAGES = [parse_jd_stage, validate_jd, match_stage, gate, write_and_evaluate]
PREPARE_STAGES, FINISH_STAGES = STAGES[:-1], STAGES[-1:]


def _execute(state: CoverLetterState, inputs: Inputs, stages: list) -> CoverLetterState:
    try:
        for stage in stages:
            if stage(state, inputs):
                break
    except Exception as error:
        state.set_error(redact(str(error)))
        save_state(state)

    return state


def _run(jd_text: str, inputs: Inputs, stages: list) -> CoverLetterState:
    state = CoverLetterState()
    save_state(state)

    def load_jd(state: CoverLetterState, _inputs: Inputs) -> bool:
        state.raw_jd_text = jd_text.strip()
        _advance(state, "jd_loaded")
        return False

    return _execute(state, inputs, [load_jd, *stages])


def run_pipeline(
    jd_text: str,
    facts: CVFacts,
    applied_for_role: str,
    force: bool = False,
    strongest_evidence: str | None = None,
) -> CoverLetterState:
    """
    JD -> match -> gate -> cover letter. All business logic; knows nothing of its caller.

    force is a human-invoked override: it only changes what happens after the
    gate returns False. strongest_evidence is the CV selection's top-ranked
    project as plain text, passed to the writer as a hint.
    """

    return _run(jd_text, Inputs(facts, applied_for_role, force, strongest_evidence), STAGES)


def run_prepare(jd_text: str, facts: CVFacts, force: bool = False) -> CoverLetterState:
    """The stages up to and including the gate. Ends "match_complete" (go), or "rejected" / "failed"."""

    return _run(jd_text, Inputs(facts, "", force, None), PREPARE_STAGES)


def run_finish(
    state: CoverLetterState,
    facts: CVFacts,
    applied_for_role: str,
    strongest_evidence: str | None = None,
    draft: str | None = None,
) -> CoverLetterState:
    """Write (or take `draft`) and evaluate for a state that run_prepare left at the gate."""

    return _execute(state, Inputs(facts, applied_for_role, state.forced, strongest_evidence, draft), FINISH_STAGES)
