import re

from cv.containment import normalize_for_match
from cv.facts import CVFacts
from models.cover_letter_schema import CoverLetterDraft


def real_employers(facts: CVFacts) -> list[str]:
    return [fact.organisation for fact in facts.work_experience.entries]


def real_institutions(facts: CVFacts) -> list[str]:
    return [fact.institution for fact in facts.education.entries]


def real_held_titles(facts: CVFacts) -> list[str]:
    return [fact.position for fact in facts.work_experience.entries]


def known_organisations(facts: CVFacts, target_company: str | None = None) -> list[str]:
    """
    Real employers/institutions a letter may name, plus the target company
    itself (an aspirational mention like "at n8n, I would..." is not an
    employer-history claim).
    """

    organisations = [*real_employers(facts), *real_institutions(facts)]

    if target_company:
        organisations.append(target_company)

    return organisations


# Item 4: a targeted, hard-fail check for one specific, high-precision
# fabrication shape -- "<role> at/with/for <Organisation>". Narrow on
# purpose: a specific grammatical pattern plus a small closed list keeps
# the false-positive rate low enough to hard-fail on.
_ROLE_WORD_PATTERN = (
    r"(?:Engineer|Manager|Developer|Scientist|Analyst|Intern|Lead|Director|"
    r"Specialist|Consultant|Researcher|Architect|Designer|Officer|"
    r"Coordinator|Administrator|Founder)"
)

_POSITION_AT_ORGANISATION_PATTERN = re.compile(
    rf"\b{_ROLE_WORD_PATTERN}\b\s+(?:at|with|for)\s+((?:[A-Z][A-Za-z0-9&.'-]*\s*){{1,4}})"
)

# Catches the other common construction, found live in a real generated
# letter that the role-word pattern above missed entirely: a sentence or
# clause OPENING with the organisation itself -- "At Agentic AI, I was
# deeply involved...", "With Acme Corp, I led..." -- with no role word
# before it at all. Anchored to sentence/paragraph start (or the very
# start of the letter) so it doesn't fire mid-sentence on unrelated uses
# of "at"/"with"/"for".
_ORG_LED_CLAUSE_PATTERN = re.compile(
    r"(?:^|[.!?]\s+)(?:At|With|For)\s+((?:[A-Z][A-Za-z0-9&.'-]*\s*){1,4}),\s+I\b",
    re.MULTILINE,
)


def find_position_at_organisation_claims(cover_letter: str) -> list[str]:
    """
    Every "<role> at/with/for <Capitalized Phrase>" or "<At/With/For>
    <Capitalized Phrase>, I ..." construction in the letter, as the raw
    organisation phrase claimed.
    """

    claims = []

    for pattern in (_POSITION_AT_ORGANISATION_PATTERN, _ORG_LED_CLAUSE_PATTERN):
        for match in pattern.finditer(cover_letter):
            org_phrase = match.group(1).strip().rstrip(",.;:")

            if org_phrase:
                claims.append(org_phrase)

    return claims


def check_fabricated_employer(
    cover_letter: str,
    known_organisations: list[str],
) -> list[str]:
    """
    Hard fail: every "<role> at/with/for <Organisation>" claim must match
    one of the candidate's real, closed-list employers or education
    institutions. Returns the offending organisation phrases as claimed;
    empty means every claim is real. Callers should reject and retry on
    any violation.

    Matched as a substring against a normalised blob of the known names
    (same technique as cv/containment.py), not exact equality -- the
    extraction pattern stops at the first
    lowercase connector word ("University of Technology" only captures
    "University"), so a claim is often a true prefix of the real name
    rather than an exact match.
    """

    known_blob = normalize_for_match(" ".join(known_organisations))
    violations = []

    for org_phrase in find_position_at_organisation_claims(cover_letter):
        normalized = normalize_for_match(org_phrase)

        if not normalized or normalized not in known_blob:
            violations.append(org_phrase)

    return violations


# Phase H: a real regression this narrowly missed -- "My role as an AI
# Engineer involved designing and deploying agentic AI systems..." names
# no organisation at all, so find_position_at_organisation_claims never
# fires, yet it still fabricates a held role the candidate never had
# (the real held titles are things like "Data Science Intern", not "AI
# Engineer" -- that string is the role being APPLIED FOR). Same pattern
# as the employer check, one level narrower: match a claimed role phrase
# against the closed list of REAL held titles instead of organisations.
_ROLE_CLAIM_PATTERN = re.compile(
    r"(?i:my role as|in my role as|working as|serving as|my position as|"
    r"i have worked as|i worked as)\s+(?:(?i:an?)\s+)?"
    r"((?:[A-Z][A-Za-z0-9&.'-]*\s*){1,4})"
)


def find_role_claims(cover_letter: str) -> list[str]:
    """
    Every "my role as/working as/... <Capitalized Phrase>" construction,
    as the raw role phrase claimed.
    """

    claims = []

    for match in _ROLE_CLAIM_PATTERN.finditer(cover_letter):
        role_phrase = match.group(1).strip().rstrip(",.;:")

        if role_phrase:
            claims.append(role_phrase)

    return claims


def check_fabricated_role_claim(cover_letter: str, real_held_titles: list[str]) -> list[str]:
    """
    Hard fail: every "my role as X" / "working as X" claim must match one
    of the candidate's real, closed-list held titles. applied_for_role
    (the role being applied for) must never appear in this construction --
    it was never held.
    """

    known_blob = normalize_for_match(" ".join(real_held_titles))
    violations = []

    for role_phrase in find_role_claims(cover_letter):
        normalized = normalize_for_match(role_phrase)

        if not normalized or normalized not in known_blob:
            violations.append(role_phrase)

    return violations


# Phase F addendum 3, item 2: hard-fail check for a letter volunteering a
# skill/tool gap -- bluntly ("I don't have X") or dressed up as
# forward-looking enthusiasm ("eager to expand my expertise in X"). Same
# failure mode as check_fabricated_employer above: the writer disclosing
# a weakness the deterministic match gate never even flagged as missing
# (real case: the JD's "Azure AI... or equivalent" was already satisfied
# by AWS experience per the matcher, yet the letter still hedged on
# Azure). Every phrase below ends in a preposition ("in"/"with") that
# grammatically requires a following skill/tool object, so a genuine,
# self-contained enthusiasm line ("excited to bring these skills to your
# team") doesn't reference a specific gap and correctly never matches.
# Phase J item 3: a real shipped letter read "While I have not worked
# directly with Azure AI or Databricks..." -- neither the phrase list nor
# HEDGE_PATTERNS caught it, because "directly" sits between "worked" and
# "with", breaking the "worked with" adjacency every existing entry
# assumed. Added "have not worked" (no "with" needed -- also covers
# "have not worked directly", "have not worked closely", etc.) and the
# two sentence-opener forms actually seen. This list will keep lagging
# new phrasings -- it is a backstop, not a guarantee of catching every
# way a gap can be disclosed; treat a pass here as "no known phrase
# matched", not "definitely no hedge".
HEDGE_PHRASES = (
    "although i lack",
    "though i lack",
    "i lack",
    "i don't have",
    "i do not have",
    "i haven't had",
    "i have not had",
    "i haven't yet",
    "i have not yet",
    "have not yet worked with",
    "haven't worked with",
    "have not worked",
    "while i have not",
    "though i have not",
    "eager to learn",
    "looking forward to learning",
    "still growing my experience with",
    "hope to gain experience in",
    "working to strengthen my skills in",
)

# Adverb-tolerant version of "have not/haven't worked with": allows
# exactly one inserted word between "worked" and "with" ("worked
# directly with", "worked closely with", ...) instead of requiring
# strict adjacency the way the plain phrases above do.
_WORKED_ADVERB_WITH_PATTERN = re.compile(
    r"(?:have not|haven't) worked(?:\s+\w+)?\s+with",
    re.IGNORECASE,
)

# Generalizes the "eager to <verb> my skills/expertise in X" family
# instead of enumerating verbs one real-run failure at a time -- but the
# verb list is a deliberate closed set of growth-implying verbs
# ("expand", "develop", "leverage", ...), NOT a \w+ wildcard: a first
# attempt at \w+ also matched "eager to BRING my expertise in Python to
# your team", which offers EXISTING strength and isn't a gap disclosure
# at all -- exactly the over-triggering false positive this check must
# avoid. "bring"/"contribute"/"apply"/"offer" stay unmatched on purpose.
_EAGER_SKILL_GAP_PATTERN = re.compile(
    r"(?:eager|keen|excited) to (?:expand|develop|build|grow|strengthen|hone|"
    r"leverage|gain|advance|improve) my (?:skills|expertise) in\b",
    re.IGNORECASE,
)
_LOOKING_FORWARD_SKILL_GAP_PATTERN = re.compile(
    r"looking forward to (?:expand|develop|build|grow|strengthen|hone|leverage|"
    r"gain|advance|improve)ing my (?:skills|expertise) in\b",
    re.IGNORECASE,
)

HEDGE_PATTERNS = (
    _EAGER_SKILL_GAP_PATTERN,
    _LOOKING_FORWARD_SKILL_GAP_PATTERN,
    _WORKED_ADVERB_WITH_PATTERN,
)


def find_hedge_phrases(cover_letter: str) -> list[str]:
    lowered = cover_letter.lower()
    matches = [phrase for phrase in HEDGE_PHRASES if phrase in lowered]

    for pattern in HEDGE_PATTERNS:
        matches += [match.group(0).lower() for match in pattern.finditer(cover_letter)]

    return matches


def check_hedge_disclosure(cover_letter: str) -> list[str]:
    """
    Hard fail: the letter must never volunteer a skill/tool gap, blunt or
    softened as forward-looking enthusiasm. The deterministic match gate
    is the only thing allowed to judge fit; a self-disclosed gap
    undermines that even when the gate itself found no problem. Always
    active (no known_organisations-style opt-out needed -- this needs no
    fact base, just the letter text).
    """

    return find_hedge_phrases(cover_letter)


# Phase J item 1: assemble_cover_letter() (agents/cover_letter_writer.py)
# is the single owner of this literal string -- imported from here, not
# redefined there, so the check below can never drift from what
# assembly actually appends.
CLOSING_LINE = "Best regards,"


def check_letter_structure(
    cover_letter: str,
    draft: CoverLetterDraft,
    facts: CVFacts,
) -> list[str]:
    """
    Hard fail: a real cover letter needs a greeting, at least one factual
    (evidenced) paragraph, a closing line, and the candidate's own exact
    name as the final line. assemble_cover_letter() already guarantees
    the closing line and name unconditionally -- this checks the
    assembled text directly rather than trusting that invariant blindly,
    the same "deterministic checks beat prompt instructions" principle
    every other check in this module follows.
    """

    violations: list[str] = []
    lines = [line for line in cover_letter.strip().splitlines() if line.strip()]

    if not lines or not lines[0].strip().lower().startswith("dear"):
        violations.append("missing a greeting line starting with 'Dear'")

    if not any(paragraph.kind == "factual" for paragraph in draft.paragraphs):
        violations.append(
            "no factual (evidenced) paragraph -- the letter makes no grounded claim "
            "about the candidate"
        )

    if CLOSING_LINE not in cover_letter:
        violations.append(f"missing the closing line {CLOSING_LINE!r}")

    if not lines or lines[-1].strip() != facts.personal.full_name:
        violations.append(
            f"final line is not the candidate's exact name {facts.personal.full_name!r}"
        )

    return violations


_FIGURE_RE = re.compile(r"\d[\d.,]*\d|\d")


def check_ungrounded_figures(letter: str, source_text: str) -> list[str]:
    """Numbers in a plain-text letter that appear in neither the fact base nor the JD (an invented figure)."""

    known = {m.rstrip(".,") for m in _FIGURE_RE.findall(source_text)}

    return [
        f"figure {figure!r} is in neither the fact base nor the JD"
        for figure in dict.fromkeys(m.rstrip(".,") for m in _FIGURE_RE.findall(letter))
        if figure not in known
    ]
