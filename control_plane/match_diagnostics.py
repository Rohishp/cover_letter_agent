import re

from models.match_schema import MatchAnalysis


WEAK_STRENGTHS = {"indirect", "not_evidenced"}
STRONG_STRENGTHS = {"strong", "partial"}

# Deliberately small and generic -- this is a simple keyword-presence
# check (Phase G item 2), not NLP. Filters common connector words that
# would trivially "match" almost any letter.
_REQUIREMENT_KEY_TERM_STOPWORDS = {
    "and", "for", "the", "are", "was", "with", "that", "this", "your",
    "have", "will", "from", "into", "well", "solutions", "requirements",
    "ensure",
}


def weak_requirements(match: MatchAnalysis) -> list[dict]:
    """
    Every core-must-have or eligibility requirement whose evidence
    strength is 'indirect' or 'not_evidenced'.

    Purely informational, for a human reading the rejection report or
    run.json -- this never feeds should_generate_cover_letter or any
    other gate.
    """

    weak: list[dict] = []

    for category, matches in (
        ("core_must_have", match.core_must_have_matches),
        ("eligibility", match.eligibility_matches),
    ):
        for evidence in matches:
            if evidence.strength in WEAK_STRENGTHS:
                weak.append(
                    {
                        "category": category,
                        "jd_requirement": evidence.jd_requirement,
                        "strength": evidence.strength,
                        "gap_note": evidence.gap_note,
                    }
                )

    return weak


# Measured, not guessed: four matcher calls on identical inputs moved the
# core score by up to 13 points and the base score by up to 8. A margin
# smaller than this is indistinguishable from run-to-run noise.
BAND_NOISE_MARGIN = 8


def hard_gaps(match: MatchAnalysis) -> list[dict]:
    """
    Core must-haves with no CV evidence at all. Report-only, like
    weak_requirements(): the human reads it to decide, no gate reads it.
    """

    return [
        {"jd_requirement": e.jd_requirement, "gap_note": e.gap_note}
        for e in match.core_must_have_matches
        if e.strength == "not_evidenced"
    ]


def shaky_requirements(match: MatchAnalysis) -> list[str]:
    """
    Core requirements not judged 'strong'. Measured: these are the ones
    whose strength flips between runs on identical inputs; 'strong' ones
    held steady. Report-only.
    """

    return [
        e.jd_requirement
        for e in match.core_must_have_matches
        if e.strength != "strong"
    ]


def match_band(match: MatchAnalysis, base_threshold: int, core_threshold: int) -> str:
    """
    'strong' / 'borderline' / 'weak', from the deterministic scores only.
    Report-only; the gate in pipeline.py is unchanged.

    Margin is the smaller of the base and core distances to their
    thresholds. Within BAND_NOISE_MARGIN either side is borderline, because
    the score can cross the threshold between runs on the same inputs. A
    clear pass with a missing core requirement is held at borderline.
    """

    margin = min(
        match.base_score - base_threshold,
        match.core_must_have_score - core_threshold,
    )

    if margin <= -BAND_NOISE_MARGIN:
        return "weak"

    if margin >= BAND_NOISE_MARGIN and not hard_gaps(match):
        return "strong"

    return "borderline"


def _requirement_key_terms(jd_requirement: str) -> list[str]:
    # {2,} (3+ total chars) rather than a longer minimum -- short but
    # meaningful acronyms like "SQL"/"AWS"/"ETL" are exactly the kind of
    # term this check most needs to catch, not noise to filter out.
    words = re.findall(r"[A-Za-z][A-Za-z0-9+.#-]{2,}", jd_requirement)
    return [w.lower() for w in words if w.lower() not in _REQUIREMENT_KEY_TERM_STOPWORDS]


def _requirement_represented_in_letter(jd_requirement: str, cover_letter_lower: str) -> bool:
    """
    True if any key term from jd_requirement shows up in the letter.
    Compares a short prefix ("stem") of each word rather than the whole
    word, so ordinary suffix variation ("pipelines" in the requirement,
    "pipeline" in the letter) doesn't cause a false miss -- still a
    simple substring check, not real stemming/NLP.
    """

    for word in _requirement_key_terms(jd_requirement):
        stem = word[:6] if len(word) > 6 else word

        if stem in cover_letter_lower:
            return True

    return False


def underrepresented_requirements(match: MatchAnalysis, cover_letter_text: str) -> list[dict]:
    """
    Every core-must-have requirement the matcher scored 'strong' or
    'partial' (real, true evidence) whose key terms never appear
    anywhere in the generated cover letter -- the mirror image of
    weak_requirements(): not a fabrication risk, a missed-case risk.
    Genuine ammunition the matcher found and the writer left unused.

    Scoped to core must-haves only, not supporting/nice-to-have -- the
    goal is making sure the highest-stakes evidenced requirements aren't
    silently dropped, not forcing every possible keyword into the letter.
    """

    cover_letter_lower = cover_letter_text.lower()
    underrepresented: list[dict] = []

    for evidence in match.core_must_have_matches:
        if evidence.strength not in STRONG_STRENGTHS:
            continue

        if not _requirement_represented_in_letter(evidence.jd_requirement, cover_letter_lower):
            underrepresented.append(
                {
                    "category": "core_must_have",
                    "jd_requirement": evidence.jd_requirement,
                    "strength": evidence.strength,
                    "cv_evidence": evidence.cv_evidence,
                }
            )

    return underrepresented
