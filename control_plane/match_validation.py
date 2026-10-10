from models.jd_schema import ParsedJD
from models.match_schema import MatchAnalysis, MatchEvidence


def _expected_items(
    prefix: str,
    requirements: list[str],
) -> list[tuple[str, str]]:
    return [
        (f"{prefix}_{index}", requirement)
        for index, requirement in enumerate(requirements, start=1)
    ]


def _actual_items(
    evidence_items: list[MatchEvidence],
) -> list[tuple[str, str]]:
    return [
        (item.requirement_id, item.jd_requirement)
        for item in evidence_items
    ]


def validate_match_coverage(
    parsed_jd: ParsedJD,
    match: MatchAnalysis,
) -> None:
    """
    Verify that every fixed requirement was evaluated exactly once,
    in the correct category, order, and wording.
    """

    expected = {
        "core": _expected_items(
            "core",
            parsed_jd.core_must_have_skills,
        ),
        "supporting": _expected_items(
            "supporting",
            parsed_jd.supporting_skills,
        ),
        "eligibility": _expected_items(
            "eligibility",
            parsed_jd.eligibility_constraints,
        ),
        "nice": _expected_items(
            "nice",
            parsed_jd.nice_to_have_skills,
        ),
    }

    actual = {
        "core": _actual_items(match.core_must_have_matches),
        "supporting": _actual_items(match.supporting_matches),
        "eligibility": _actual_items(match.eligibility_matches),
        "nice": _actual_items(match.nice_to_have_matches),
    }

    for category, expected_items in expected.items():
        actual_items = actual[category]

        if actual_items != expected_items:
            raise ValueError(
                f"Matcher output mismatch for category '{category}'. "
                f"Expected: {expected_items}. "
                f"Received: {actual_items}."
            )