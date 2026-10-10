# Phase J item 2: the profile can cite a real, valid fact_id (satisfying
# profile_evidence's existing citation check) while still writing a
# claim -- a JD word like "compliance" -- that fact doesn't actually
# support. check_containment alone can't catch this (it only extracts
# capitalised proper nouns/numbers as candidate tokens); this is exactly
# the failure mode check_jd_vocabulary_grounding exists for.

from cv.containment import check_jd_vocabulary_grounding
from cv.selector import ProfileSelection, validate_profile_selection
from models.jd_schema import ParsedJD


def _compliance_jd() -> ParsedJD:
    return ParsedJD(
        core_must_have_skills=[
            "Ensure compliance with data governance and security requirements",
        ],
    )


def test_profile_mirroring_jd_compliance_language_with_no_supporting_fact_fails(facts):
    jd = _compliance_jd()
    profile = ProfileSelection(
        profile_evidence=["proj.widget-analyzer"],
        profile="I built a Widget Analyzer for real-time data, ensuring compliance throughout.",
    )

    errors = validate_profile_selection(profile, facts, jd, valid_ids={"proj.widget-analyzer"})

    assert any("compliance" in error.lower() for error in errors)


def test_check_jd_vocabulary_grounding_flags_compliance_directly(facts):
    jd = _compliance_jd()
    text = "I built a Widget Analyzer for real-time data, ensuring compliance throughout."

    violations = check_jd_vocabulary_grounding(text, facts, jd, cited_ids=["proj.widget-analyzer"])

    assert any(v.lower() == "compliance" for v in violations)


def test_check_jd_vocabulary_grounding_passes_ordinary_paraphrase(facts):
    # Reusing the fact base's own real words (from a cited entry) is
    # fine, even paraphrased -- the check only concerns JD vocabulary
    # words absent from what was actually cited.
    jd = _compliance_jd()
    text = "I built a Widget Analyzer that processed 1000 widgets per second."

    assert check_jd_vocabulary_grounding(text, facts, jd, cited_ids=["proj.widget-analyzer"]) == []


def test_check_jd_vocabulary_grounding_passes_when_the_word_is_genuinely_supported(facts):
    # If the cited fact's own text genuinely contains the JD word, it is
    # grounded and must not be flagged.
    jd = ParsedJD(core_must_have_skills=["Experience processing widgets at scale"])
    text = "I built a Widget Analyzer that processes real-time widgets."

    assert check_jd_vocabulary_grounding(text, facts, jd, cited_ids=["proj.widget-analyzer"]) == []
