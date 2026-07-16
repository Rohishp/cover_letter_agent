from models.match_schema import MatchAnalysis, MatchEvidence


STRENGTH_POINTS = {
    "strong": 1.0,
    "partial": 0.70,
    "indirect": 0.50,
    "not_evidenced": 0.0,
}


CORE_WEIGHT = 0.70
ELIGIBILITY_WEIGHT = 0.20
SUPPORTING_WEIGHT = 0.10

NICE_TO_HAVE_BONUS_WEIGHT = 0.10


def score_evidence_list(
    evidence_items: list[MatchEvidence],
    empty_score: int = 0,
) -> int:
    """
    Convert fixed evidence judgments into a deterministic 0-100 score.
    """

    if not evidence_items:
        return empty_score

    earned = sum(
        STRENGTH_POINTS[item.strength]
        for item in evidence_items
    )

    return round(
        earned / len(evidence_items) * 100
    )


def compute_deterministic_match_scores(
    match: MatchAnalysis,
) -> MatchAnalysis:
    """
    Calculate all match scores deterministically.

    Nice-to-have evidence adds a bonus but cannot reduce base eligibility.
    """

    core_score = score_evidence_list(
        match.core_must_have_matches,
        empty_score=0,
    )

    supporting_score = score_evidence_list(
        match.supporting_matches,
        empty_score=100,
    )

    eligibility_score = score_evidence_list(
        match.eligibility_matches,
        empty_score=100,
    )

    nice_score = score_evidence_list(
        match.nice_to_have_matches,
        empty_score=0,
    )

    base_score = round(
        core_score * CORE_WEIGHT
        + eligibility_score * ELIGIBILITY_WEIGHT
        + supporting_score * SUPPORTING_WEIGHT
    )

    nice_bonus = round(
        nice_score * NICE_TO_HAVE_BONUS_WEIGHT
    )

    overall_score = min(
        100,
        base_score + nice_bonus,
    )

    match.core_must_have_score = core_score
    match.supporting_score = supporting_score
    match.eligibility_score = eligibility_score
    match.nice_to_have_score = nice_score
    match.base_score = base_score
    match.overall_score = overall_score

    return match