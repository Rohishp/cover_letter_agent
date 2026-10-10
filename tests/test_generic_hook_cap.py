from control_plane.eval_validation import starts_with_generic_hook, validate_eval_result
from models.eval_schema import CriterionScore, EvalResult


def _result(hook_score):
    c = lambda s: CriterionScore(score=s, feedback="x")
    return EvalResult(
        hook=c(hook_score), keyword_match=c(10), proof_over_pitch=c(10),
        zero_resume_duplication=c(10), cta=c(10),
        overall_score=0, feedback_text="x", passed=True,
    )


def test_generic_opening_is_detected_after_salutation():
    assert starts_with_generic_hook("Dear Team,\nI am writing to express my interest in the role.")
    assert not starts_with_generic_hook("Dear Team,\nLast quarter I cut judge variance by 40%.")


def test_generic_opening_caps_the_hook_score_at_five():
    result = validate_eval_result("I am writing to express my interest in the role.", _result(18))

    assert result.hook.score == 5
    assert result.overall_score == 5 + 40


def test_specific_opening_leaves_the_hook_score_alone():
    result = validate_eval_result("Last quarter I cut judge variance by 40%.", _result(18))

    assert result.hook.score == 18
