import re

from cv.facts import CVFacts
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


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return ALIAS_TABLE.get(text, text)


def known_entities_blob(facts: CVFacts, parsed_jd: ParsedJD) -> str:
    """
    Every string in the fact base and the parsed JD, normalised and
    joined into one blob -- the ground truth an LLM-written profile or
    target_title is checked against.
    """

    parts: list[str] = [facts.personal.full_name, facts.personal.location]

    for fact in facts.work_experience.entries:
        parts += [fact.organisation, fact.city]

        if fact.tools:
            parts.append(fact.tools)

        if fact.topic:
            parts.append(fact.topic)

        parts += fact.bullets

    for fact in facts.education.entries:
        parts += [fact.degree, fact.institution, fact.city]
        parts += fact.bullets

    for fact in facts.projects.entries:
        parts += [fact.name, fact.tools, fact.intro]
        parts += fact.bullets

    for group in facts.skills.groups:
        parts.append(group.name)
        parts += group.items

    parts += facts.coursework.items

    for cert in facts.certifications.entries:
        parts += [cert.name, cert.issuer]

    for language_fact in facts.languages.entries:
        parts.append(language_fact.language)

    if parsed_jd.company_name:
        parts.append(parsed_jd.company_name)

    if parsed_jd.job_title:
        parts.append(parsed_jd.job_title)

    parts += parsed_jd.technical_skills
    parts += parsed_jd.core_must_have_skills
    parts += parsed_jd.supporting_skills
    parts += parsed_jd.eligibility_constraints
    parts += parsed_jd.nice_to_have_skills

    return _normalize(" ".join(parts))


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
) -> list[str]:
    """
    Every company name, tool name and number in `text` must appear in the
    fact base or the parsed JD. Returns the offending tokens as they
    appear in `text`; empty means `text` is fully grounded.
    """

    blob = known_entities_blob(facts, parsed_jd)
    violations = []

    for token in _candidate_tokens(text):
        normalized = _normalize(token)

        if not normalized:
            continue

        if normalized not in blob:
            violations.append(token)

    return violations
