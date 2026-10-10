from control_plane.match_diagnostics import weak_requirements
from models.match_schema import MatchAnalysis, MatchEvidence


def _evidence(requirement_id, jd_requirement, strength, gap_note=None):
    return MatchEvidence(
        requirement_id=requirement_id,
        jd_requirement=jd_requirement,
        strength=strength,
        explanation="test explanation",
        gap_note=gap_note,
    )


def test_weak_requirements_includes_indirect_and_not_evidenced():
    match = MatchAnalysis(
        core_must_have_matches=[
            _evidence("core_1", "Python", "not_evidenced", "No Python experience anywhere in the CV."),
            _evidence("core_2", "Docker", "indirect", "Only container-adjacent tooling, not Docker itself."),
        ],
        match_summary="test",
    )

    result = weak_requirements(match)

    assert len(result) == 2
    assert result[0] == {
        "category": "core_must_have",
        "jd_requirement": "Python",
        "strength": "not_evidenced",
        "gap_note": "No Python experience anywhere in the CV.",
    }
    assert result[1]["strength"] == "indirect"


def test_weak_requirements_excludes_strong_and_partial():
    match = MatchAnalysis(
        core_must_have_matches=[
            _evidence("core_1", "Python", "strong"),
            _evidence("core_2", "SQL", "partial"),
        ],
        match_summary="test",
    )

    assert weak_requirements(match) == []


def test_weak_requirements_covers_core_and_eligibility_only():
    match = MatchAnalysis(
        core_must_have_matches=[
            _evidence("core_1", "Python", "not_evidenced", "No evidence."),
        ],
        supporting_matches=[
            _evidence("supporting_1", "Documentation", "not_evidenced", "Should not appear."),
        ],
        eligibility_matches=[
            _evidence("eligibility_1", "EU work authorization", "indirect", "Unclear from CV."),
        ],
        nice_to_have_matches=[
            _evidence("nice_1", "Rust", "not_evidenced", "Should not appear."),
        ],
        match_summary="test",
    )

    result = weak_requirements(match)
    categories = {item["category"] for item in result}

    assert categories == {"core_must_have", "eligibility"}
    assert len(result) == 2


def test_weak_requirements_handles_null_gap_note():
    match = MatchAnalysis(
        core_must_have_matches=[
            _evidence("core_1", "Python", "not_evidenced", gap_note=None),
        ],
        match_summary="test",
    )

    result = weak_requirements(match)

    assert result[0]["gap_note"] is None


def test_weak_requirements_empty_when_no_matches():
    match = MatchAnalysis(match_summary="test")

    assert weak_requirements(match) == []
