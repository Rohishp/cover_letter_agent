from control_plane.match_diagnostics import hard_gaps, match_band, shaky_requirements
from control_plane.scoring import compute_deterministic_match_scores
from models.match_schema import MatchAnalysis, MatchEvidence


BASE_T, CORE_T = 65, 60


def _ev(i, strength, gap=None):
    return MatchEvidence(
        requirement_id=f"core_{i}", jd_requirement=f"req {i}",
        strength=strength, explanation="x", gap_note=gap,
    )


def _match(strengths):
    match = MatchAnalysis(
        core_must_have_matches=[_ev(i, s) for i, s in enumerate(strengths)],
        match_summary="t",
    )
    return compute_deterministic_match_scores(match)


def test_clear_pass_without_gaps_is_strong():
    assert match_band(_match(["strong"] * 4), BASE_T, CORE_T) == "strong"


def test_clear_fail_is_weak():
    assert match_band(_match(["not_evidenced"] * 4), BASE_T, CORE_T) == "weak"


def test_near_threshold_is_borderline_on_either_side():
    # core 67: passes, but only 7 above the core threshold
    assert match_band(_match(["strong"] * 3 + ["partial"] + ["indirect"] * 2 + ["not_evidenced"]), BASE_T, CORE_T) == "borderline"
    # core 56: fails, but only 4 below it
    assert match_band(_match(["strong"] * 2 + ["partial"] * 2 + ["indirect"] + ["not_evidenced"] * 2), BASE_T, CORE_T) == "borderline"


def test_hard_gap_holds_a_clear_pass_at_borderline():
    match = _match(["strong"] * 9 + ["not_evidenced"])
    assert match.core_must_have_score >= CORE_T + 8
    assert match_band(match, BASE_T, CORE_T) == "borderline"


def test_hard_gaps_lists_only_not_evidenced_core_with_note():
    match = MatchAnalysis(
        core_must_have_matches=[_ev(1, "not_evidenced", "no SQL anywhere"), _ev(2, "indirect", "x"), _ev(3, "strong")],
        match_summary="t",
    )
    assert hard_gaps(match) == [{"jd_requirement": "req 1", "gap_note": "no SQL anywhere"}]


def test_shaky_requirements_are_core_items_not_judged_strong():
    match = MatchAnalysis(
        core_must_have_matches=[_ev(1, "strong"), _ev(2, "partial"), _ev(3, "not_evidenced")],
        match_summary="t",
    )
    assert shaky_requirements(match) == ["req 2", "req 3"]
