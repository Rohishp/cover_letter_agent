# The LLM and storage layer are mocked throughout: every network- or
# disk-touching function pipeline.py calls is patched, so these tests
# never hit OpenAI, S3, or the local filesystem. Phase H: run_pipeline
# now requires facts/applied_for_role to generate a cover letter (the
# writer is grounded in CVFacts, not parsed_cv).

from unittest.mock import MagicMock, patch

import pipeline
from models.eval_schema import CriterionScore, EvalResult
from models.jd_schema import ParsedJD
from models.match_schema import MatchAnalysis, MatchEvidence


# validate_jd_input_quality requires >= 200 characters of raw JD text.
JD_TEXT = (
    "Backend Engineer at Test Co. We are looking for a backend engineer "
    "with strong Python and Kubernetes experience to join our platform "
    "team. You will own services end to end, from design through "
    "production operation, working closely with product and SRE."
)

APPLIED_FOR_ROLE = "Backend Engineer"

PARSED_JD = ParsedJD(
    job_title="Backend Engineer",
    company_name="Test Co",
    core_must_have_skills=["Python", "Kubernetes"],
)

PASSING_COVER_LETTER = (
    "Building reliable systems with Python and Kubernetes is exactly what excites "
    "me about this role at Test Co."
)

PASSING_EVAL_RESULT = EvalResult(
    hook=CriterionScore(score=15, feedback="ok"),
    keyword_match=CriterionScore(score=15, feedback="ok"),
    proof_over_pitch=CriterionScore(score=15, feedback="ok"),
    zero_resume_duplication=CriterionScore(score=15, feedback="ok"),
    cta=CriterionScore(score=15, feedback="ok"),
    overall_score=75,
    feedback_text="Looks good.",
)


def _rejecting_match() -> MatchAnalysis:
    return MatchAnalysis(
        core_must_have_matches=[
            MatchEvidence(
                requirement_id="core_1",
                jd_requirement="Python",
                strength="not_evidenced",
                explanation="No Python anywhere in the CV.",
                gap_note="No Python experience anywhere in the CV.",
            ),
            MatchEvidence(
                requirement_id="core_2",
                jd_requirement="Kubernetes",
                strength="not_evidenced",
                explanation="No Kubernetes anywhere in the CV.",
                gap_note="No Kubernetes experience anywhere in the CV.",
            ),
        ],
        match_summary="Weak match.",
    )


def _passing_match() -> MatchAnalysis:
    return MatchAnalysis(
        core_must_have_matches=[
            MatchEvidence(
                requirement_id="core_1",
                jd_requirement="Python",
                strength="strong",
                explanation="Extensive Python experience.",
            ),
            MatchEvidence(
                requirement_id="core_2",
                jd_requirement="Kubernetes",
                strength="strong",
                explanation="Led Kubernetes migrations.",
            ),
        ],
        match_summary="Strong match.",
    )


def _build_mocks(match_analysis: MatchAnalysis) -> dict:
    return {
        "parse_jd_cached": MagicMock(return_value=(PARSED_JD, True)),
        "compare_cv_to_jd": MagicMock(return_value=match_analysis),
        "write_cover_letter": MagicMock(return_value=PASSING_COVER_LETTER),
        "evaluate_cover_letter": MagicMock(return_value=PASSING_EVAL_RESULT),
        "save_state": MagicMock(return_value=None),
        "storage": MagicMock(write_text=MagicMock(return_value="cover_letters/test.txt")),
    }


def _run(facts, force: bool, match_analysis: MatchAnalysis):
    mocks = _build_mocks(match_analysis)

    with patch.multiple(pipeline, **mocks):
        state = pipeline.run_pipeline(
            jd_text=JD_TEXT,
            force=force,
            facts=facts,
            applied_for_role=APPLIED_FOR_ROLE,
        )

    return state, mocks


def test_force_false_on_rejecting_fixture_stays_rejected(facts):
    state, mocks = _run(facts, force=False, match_analysis=_rejecting_match())

    assert state.status == "rejected"
    assert state.cover_letter is None
    assert state.forced is False
    assert state.match_gate_result == "would_have_rejected"
    mocks["write_cover_letter"].assert_not_called()


def test_force_true_on_rejecting_fixture_proceeds_and_writes(facts):
    state, mocks = _run(facts, force=True, match_analysis=_rejecting_match())

    assert state.forced is True
    assert state.match_gate_result == "would_have_rejected"
    assert state.status != "rejected"
    assert state.cover_letter is not None

    mocks["write_cover_letter"].assert_called_once_with(
        facts=facts,
        parsed_jd=state.parsed_jd,
        match_analysis=state.match_analysis,
        applied_for_role=APPLIED_FOR_ROLE,
        eval_feedback=None,
        strongest_evidence=None,
        underrepresented_requirements_hint=[],
    )


def test_forced_write_call_is_byte_identical_to_a_normal_passing_call(facts):
    """
    The exact kwargs write_cover_letter receives during a forced run must
    be indistinguishable in shape from the kwargs it receives during a
    genuine, non-forced pass -- same keys, same eval_feedback=None on the
    first attempt, no force-related content anywhere.
    """

    forced_state, forced_mocks = _run(facts, force=True, match_analysis=_rejecting_match())
    forced_call_kwargs = forced_mocks["write_cover_letter"].call_args.kwargs

    normal_state, normal_mocks = _run(facts, force=False, match_analysis=_passing_match())
    normal_call_kwargs = normal_mocks["write_cover_letter"].call_args.kwargs

    assert normal_state.forced is False
    assert normal_state.match_gate_result == "passed"

    # Same keys, same call shape, eval_feedback=None on the first attempt
    # in both cases -- force injects nothing extra into the call.
    assert set(forced_call_kwargs.keys()) == set(normal_call_kwargs.keys())
    assert forced_call_kwargs["eval_feedback"] is None
    assert normal_call_kwargs["eval_feedback"] is None
    assert forced_call_kwargs["facts"] == normal_call_kwargs["facts"] == facts
    assert forced_call_kwargs["parsed_jd"] == normal_call_kwargs["parsed_jd"] == PARSED_JD
