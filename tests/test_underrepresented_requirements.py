# Phase G item 2: a core-must-have the matcher scored strong/partial
# (real, true evidence) that the writer never mentioned -- the mirror
# image of weak_requirements(). Not a fabrication risk, a missed-case one.

from control_plane.match_diagnostics import underrepresented_requirements
from models.match_schema import MatchAnalysis, MatchEvidence


def _match(*evidences: MatchEvidence) -> MatchAnalysis:
    return MatchAnalysis(core_must_have_matches=list(evidences), match_summary="Test match.")


def test_strong_requirement_never_mentioned_is_flagged():
    match = _match(
        MatchEvidence(
            requirement_id="core_1",
            jd_requirement="SQL",
            cv_evidence="SQL used at Robert Bosch GmbH.",
            strength="strong",
            explanation="Direct SQL evidence.",
        ),
    )
    letter = "I have strong Python and machine-learning experience relevant to this role."

    result = underrepresented_requirements(match, letter)

    assert len(result) == 1
    assert result[0]["jd_requirement"] == "SQL"
    assert result[0]["strength"] == "strong"


def test_strong_requirement_that_is_mentioned_passes():
    match = _match(
        MatchEvidence(
            requirement_id="core_1",
            jd_requirement="SQL",
            cv_evidence="SQL used at Robert Bosch GmbH.",
            strength="strong",
            explanation="Direct SQL evidence.",
        ),
    )
    letter = "I have hands-on SQL experience from production data-engineering work."

    assert underrepresented_requirements(match, letter) == []


def test_partial_requirement_never_mentioned_is_flagged():
    match = _match(
        MatchEvidence(
            requirement_id="core_1",
            jd_requirement="Build and maintain data pipelines, models and storage structures",
            cv_evidence="Built data-processing workflows on Hadoop.",
            strength="partial",
            explanation="Related pipeline evidence.",
        ),
    )
    letter = "I have designed and deployed several agentic AI systems for real-world use."

    result = underrepresented_requirements(match, letter)

    assert len(result) == 1
    assert "pipelines" in result[0]["jd_requirement"]


def test_partial_requirement_with_a_stemmed_match_passes():
    # Requirement says "pipelines" (plural); letter says "pipeline"
    # (singular) -- the stem-prefix comparison must still catch this.
    match = _match(
        MatchEvidence(
            requirement_id="core_1",
            jd_requirement="Build and maintain data pipelines, models and storage structures",
            cv_evidence="Built data-processing workflows on Hadoop.",
            strength="partial",
            explanation="Related pipeline evidence.",
        ),
    )
    letter = "I built a robust data pipeline for large-scale processing."

    assert underrepresented_requirements(match, letter) == []


def test_weak_evidence_is_never_flagged_even_if_unmentioned():
    match = _match(
        MatchEvidence(
            requirement_id="core_1",
            jd_requirement="Kubernetes orchestration at scale",
            strength="not_evidenced",
            explanation="No Kubernetes experience anywhere in the CV.",
            gap_note="No Kubernetes experience.",
        ),
    )
    letter = "I have strong Python and machine-learning experience relevant to this role."

    assert underrepresented_requirements(match, letter) == []


def test_only_core_must_have_matches_are_considered_not_supporting():
    match = MatchAnalysis(
        core_must_have_matches=[],
        supporting_matches=[
            MatchEvidence(
                requirement_id="sup_1",
                jd_requirement="Public speaking experience",
                strength="strong",
                explanation="Gave several conference talks.",
            ),
        ],
        match_summary="Test match.",
    )
    letter = "I have strong Python and machine-learning experience relevant to this role."

    assert underrepresented_requirements(match, letter) == []
