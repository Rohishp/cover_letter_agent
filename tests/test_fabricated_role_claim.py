# Phase H: a fabricated HELD ROLE claim ("my role as an AI Engineer
# involved...") names no organisation at all, so check_fabricated_employer
# never fires -- this is a separate, narrow backstop matching a claimed
# role phrase against the closed list of the candidate's real held titles.

from control_plane.cover_letter_containment import check_fabricated_role_claim, find_role_claims


REAL_HELD_TITLES = ["Data Science Intern", "Research Intern"]


def test_fabricated_role_claim_with_no_organisation_named_fails():
    letter = (
        "My role as an AI Engineer involved designing and deploying agentic AI "
        "systems using Python, OpenAI Agents SDK, and RAG architectures."
    )

    violations = check_fabricated_role_claim(letter, REAL_HELD_TITLES)

    assert "AI Engineer" in violations


def test_real_held_title_passes():
    letter = "My role as a Data Science Intern involved cleaning large-scale manufacturing data."

    violations = check_fabricated_role_claim(letter, REAL_HELD_TITLES)

    assert violations == []


def test_working_as_construction_also_fails():
    letter = "Working as an AI Engineer, I have shipped several agentic systems."

    violations = check_fabricated_role_claim(letter, REAL_HELD_TITLES)

    assert "AI Engineer" in violations


def test_applied_for_role_mentioned_without_a_role_claim_construction_passes():
    """
    Describing the role being applied for is fine and expected -- only
    the "my role as X" / "working as X" construction claims X was HELD.
    """

    letter = "I'm excited to apply for the AI Engineer position at your company."

    violations = check_fabricated_role_claim(letter, REAL_HELD_TITLES)

    assert violations == []


def test_find_role_claims_extracts_the_raw_phrase():
    letter = "In my role as an AI Engineer, I designed agentic systems."

    claims = find_role_claims(letter)

    assert "AI Engineer" in claims
