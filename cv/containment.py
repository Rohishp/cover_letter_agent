import re

from cv.facts import CVFacts, ids_by_kind
from models.jd_schema import ParsedJD


# Small, explicit alias table -- not general NLP, just the handful of
# abbreviations a CV realistically uses that wouldn't otherwise
# substring-match the fact base or JD verbatim.
ALIAS_TABLE = {
    "k8s": "kubernetes",
    "js": "javascript",
    "ts": "typescript",
}

_NUMBER_PATTERN = re.compile(r"^\d+(?:\.\d+)?%?x?$")


def normalize_for_match(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return ALIAS_TABLE.get(text, text)


def fact_base_blob(facts: CVFacts, only_ids: set[str] | None = None) -> str:
    """
    Every string belonging to the fact base itself -- no JD content.
    only_ids, if given, restricts this to entries/skill-groups/etc. whose
    own ID (or, for a bullet ID, whose parent entry's ID) is in the set
    -- Phase J item 2's tighter grounding: does a claim trace to what was
    actually CITED, not just to anything anywhere in the whole fact base.
    Not normalised -- callers normalise after combining with anything
    else they need in the blob.
    """

    def _included(entry_id: str) -> bool:
        if only_ids is None:
            return True
        if entry_id in only_ids:
            return True
        return any(cited.startswith(f"{entry_id}.") for cited in only_ids)

    parts: list[str] = [facts.personal.full_name, facts.personal.location]

    for entry_id, fact in zip(ids_by_kind(facts, "experience"), facts.work_experience.entries):
        if not _included(entry_id):
            continue

        parts += [fact.organisation, fact.city]

        if fact.tools:
            parts.append(fact.tools)

        if fact.topic:
            parts.append(fact.topic)

        parts += fact.bullets

    for entry_id, fact in zip(ids_by_kind(facts, "education"), facts.education.entries):
        if not _included(entry_id):
            continue

        parts += [fact.degree, fact.institution, fact.city]
        parts += fact.bullets

    for entry_id, fact in zip(ids_by_kind(facts, "project"), facts.projects.entries):
        if not _included(entry_id):
            continue

        parts += [fact.name, fact.tools, fact.intro]
        parts += fact.bullets

    for group_id, group in zip(ids_by_kind(facts, "skill_group"), facts.skills.groups):
        if not _included(group_id):
            continue

        parts.append(group.name)
        parts += group.items

    if only_ids is None or "coursework" in only_ids:
        parts += facts.coursework.items

    for cert_id, cert in zip(ids_by_kind(facts, "certification"), facts.certifications.entries):
        if not _included(cert_id):
            continue

        parts += [cert.name, cert.issuer]

    for lang_id, language_fact in zip(ids_by_kind(facts, "language"), facts.languages.entries):
        if not _included(lang_id):
            continue

        parts.append(language_fact.language)

    return " ".join(parts)


def known_entities_blob(
    facts: CVFacts, parsed_jd: ParsedJD, only_ids: set[str] | None = None
) -> str:
    """
    Every string in the fact base and the parsed JD, normalised and
    joined into one blob -- the ground truth an LLM-written profile or
    target_title is checked against. only_ids narrows the fact-base
    portion to what was actually cited (see fact_base_blob); the
    candidate's own name/location and every parsed_jd field stay
    unconditional either way -- they are safe, known-context vocabulary,
    not something that needs its own citation.
    """

    parts = [fact_base_blob(facts, only_ids)]

    if parsed_jd.company_name:
        parts.append(parsed_jd.company_name)

    if parsed_jd.job_title:
        parts.append(parsed_jd.job_title)

    parts += parsed_jd.technical_skills
    parts += parsed_jd.core_must_have_skills
    parts += parsed_jd.supporting_skills
    parts += parsed_jd.eligibility_constraints
    parts += parsed_jd.nice_to_have_skills

    return normalize_for_match(" ".join(parts))


def _candidate_tokens(text: str) -> list[str]:
    """
    Candidate named entities from free text: every number, plus every
    capitalised word that is not the first word of its sentence (ordinary
    sentence-initial capitalisation is grammar, not a named entity).
    """

    candidates = []

    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        words = [word for word in sentence.split() if word]

        for position, raw_word in enumerate(words):
            word = raw_word.strip(".,;:()'\"")

            if not word:
                continue

            if _NUMBER_PATTERN.match(word):
                candidates.append(word)
                continue

            if position == 0:
                continue

            if word[0].isupper():
                candidates.append(word)

    return candidates


def check_containment(
    text: str,
    facts: CVFacts,
    parsed_jd: ParsedJD,
    only_ids: set[str] | None = None,
) -> list[str]:
    """
    Every company name, tool name and number in `text` must appear in the
    fact base or the parsed JD. Returns the offending tokens as they
    appear in `text`; empty means `text` is fully grounded. only_ids (
    Phase J item 2), if given, tightens this to the fact base actually
    cited rather than the whole fact base -- see known_entities_blob.
    """

    blob = known_entities_blob(facts, parsed_jd, only_ids)
    violations = []

    for token in _candidate_tokens(text):
        normalized = normalize_for_match(token)

        if not normalized:
            continue

        if normalized not in blob:
            violations.append(token)

    return violations


_SIGNIFICANT_WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9+.#-]{2,}")

# Same small connector-word set control_plane/match_diagnostics.py and
# cv/selection_rules.py each already carry their own copy of (importing
# either would cycle back through cv.selector -> cv.containment) --
# without it, ordinary words like "and"/"with"/"solutions" inside a JD
# requirement sentence would become "JD vocabulary" to check-ground,
# producing meaningless pass/fail noise unrelated to any real claim.
_JD_VOCABULARY_STOPWORDS = {
    "and", "for", "the", "are", "was", "with", "that", "this", "your",
    "have", "will", "from", "into", "well", "using", "used", "based",
    "solutions", "requirements", "ensure",
}

# Confirmed live (Phase J verification): "Build and maintain data
# pipelines..." in a JD's core_must_have_skills made "build"/"maintain"
# into flaggable "JD vocabulary" -- ordinary professional verbs nearly
# any honest work description shares with nearly any JD, not evidence of
# mirroring THIS JD's specific language the way a distinctive noun like
# "compliance"/"governance" is. Excluded so the check targets what it was
# built for: a specific, unusual claim-word smuggled in with no grounded
# fact, not routine verb overlap.
_GENERIC_PROFESSIONAL_VERBS = {
    "build", "built", "maintain", "maintained", "design", "designed",
    "develop", "developed", "deploy", "deployed", "deliver", "delivered",
    "support", "supported", "create", "created", "manage", "managed",
    "lead", "led", "translate", "translated", "collaborate", "collaborated",
    "communicate", "communicated", "work", "worked", "drive", "driven",
    "ship", "shipped", "own", "owned", "test", "tested", "review", "reviewed",
}

# Deliberately not JD_VOCABULARY_MIRRORING_GUIDANCE's whole prompt text --
# just the field names it grants permission to mirror from, so this check
# and that guidance can never silently drift out of scope of each other.
_JD_VOCABULARY_FIELDS = ("core_must_have_skills", "supporting_skills", "technical_skills")


def check_jd_vocabulary_grounding(
    text: str,
    facts: CVFacts,
    parsed_jd: ParsedJD,
    cited_ids: list[str],
) -> list[str]:
    """
    Phase J item 2: catches a failure mode check_containment structurally
    cannot -- a real JD word (e.g. "compliance", "governance") mirrored
    into the profile with no cited fact that actually supports it.
    check_containment's _candidate_tokens only extracts capitalised
    proper nouns and numbers; an ordinary lowercase claim word is
    invisible to it. This checks specifically the JD's own vocabulary
    fields (core_must_have_skills/supporting_skills/technical_skills --
    exactly what JD_VOCABULARY_MIRRORING_GUIDANCE permits reusing "when a
    real fact honestly matches") against the CITED facts only, using
    fact_base_blob (never known_entities_blob) so a JD word can't ground
    itself just by being JD vocabulary -- the JD's own presence proves
    nothing about whether the candidate's cited evidence supports it.

    Deliberately narrow: only JD-vocabulary words are checked, not every
    common word in the profile, so ordinary honest paraphrasing ("built"
    vs. a fact's "developed") is never flagged.
    """

    jd_vocabulary_blob = " ".join(
        item for field in _JD_VOCABULARY_FIELDS for item in getattr(parsed_jd, field)
    )
    jd_words = {
        word.lower()
        for word in _SIGNIFICANT_WORD_PATTERN.findall(jd_vocabulary_blob)
        if word.lower() not in _JD_VOCABULARY_STOPWORDS
        and word.lower() not in _GENERIC_PROFESSIONAL_VERBS
    }

    cited_blob = normalize_for_match(fact_base_blob(facts, only_ids=set(cited_ids)))

    violations = []

    for word in _SIGNIFICANT_WORD_PATTERN.findall(text):
        if word.lower() not in jd_words:
            continue

        if normalize_for_match(word) not in cited_blob:
            violations.append(word)

    return violations


# Phase K: citing a real fact proves a claim isn't invented; it doesn't
# prove the claim is USEFUL. "exemplifies my ability to design and deploy
# AI solutions with precision" can cite a real project ID while engaging
# with none of what's actually distinctive about it. Reusing the same
# min-length threshold as _JD_VOCABULARY_STOPWORDS filtering elsewhere in
# this module: long enough that ordinary connector words never qualify as
# "distinguishing", short enough that real technology/method words
# ("Lambda", "RAG") still do.
_SPECIFICITY_MIN_WORD_LEN = 5


def check_citation_specificity(text: str, facts: CVFacts, cited_ids: list[str]) -> list[str]:
    """
    Requires at least one DISTINGUISHING TOKEN -- a number (via
    _candidate_tokens, same as check_containment), or a specific
    method/technology word 5+ characters long -- shared between `text`
    and the bullet/intro/tools text of its own cited fact(s) (via
    fact_base_blob, scoped the same way check_containment's only_ids is).
    A paragraph or profile that cites a real fact but shares no such
    token with it could describe any candidate with a similar-sounding
    claim, not specifically the cited one -- this is what makes a
    citation SPECIFIC, not just non-fabricated.

    One mechanism, reused: the same primitives check_containment and
    check_jd_vocabulary_grounding are built from
    (_candidate_tokens/normalize_for_match/fact_base_blob), not a third
    implementation.
    """

    if not cited_ids:
        return ["cites no fact_ids -- there is nothing to be specific about"]

    cited_text = fact_base_blob(facts, only_ids=set(cited_ids))

    text_tokens = {normalize_for_match(t) for t in _candidate_tokens(text) if normalize_for_match(t)}
    cited_tokens = {normalize_for_match(t) for t in _candidate_tokens(cited_text) if normalize_for_match(t)}

    text_words = {
        word.lower()
        for word in _SIGNIFICANT_WORD_PATTERN.findall(text)
        if len(word) >= _SPECIFICITY_MIN_WORD_LEN
        and word.lower() not in _JD_VOCABULARY_STOPWORDS
        and word.lower() not in _GENERIC_PROFESSIONAL_VERBS
    }
    cited_words = {
        word.lower()
        for word in _SIGNIFICANT_WORD_PATTERN.findall(cited_text)
        if len(word) >= _SPECIFICITY_MIN_WORD_LEN
    }

    if (text_tokens & cited_tokens) or (text_words & cited_words):
        return []

    return [
        "no distinguishing detail (a number, named method, or technology term) from "
        "any cited fact's own text appears -- this could describe any candidate with "
        "a similarly-shaped claim, not specifically what was cited"
    ]
