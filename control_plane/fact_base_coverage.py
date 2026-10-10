from cv.facts import CVFacts
from cv.schema import CVContent
from cv.selection_rules import _term_mentioned
from models.jd_schema import ParsedJD


def underdescribed_requirements(
    parsed_jd: ParsedJD, facts: CVFacts, selected_content: CVContent
) -> list[dict]:
    """
    A JD-named requirement term that IS true of the candidate (appears
    as a tool/skill-group entry ANYWHERE in the fact base -- not just
    what survived selection onto this specific CV) but is demonstrated
    in NONE of the bullets actually rendered on this application's CV --
    the fact base under-describes real evidence it already has (Phase H
    item 2).

    facts is checked for "is it true of the candidate at all" (a tools
    line or skill-group item anywhere in cv_facts.yaml); selected_content
    is checked for "is it demonstrated in what this application actually
    shows" (the rendered bullets). A tool that's true of the candidate
    but whose entry got cut from this specific CV entirely is a
    different, existing concern (weak_requirements /
    underrepresented_requirements), not this diagnostic's.

    Report-only, deliberately outside the generation path: nothing
    consumes this automatically, nothing retries on it, no gate reads it.
    The system must never rewrite or extend fact-base bullets to cover a
    requirement -- that is invention inside the candidate's own work
    history, which invariants 2 ("parsers extract, they do not infer")
    and 3 ("the writer uses approved evidence only") both forbid, and it
    would be strictly harder to spot than the fabrications this phase
    closes. Only a human editing cv_facts.yaml may close a gap this
    surfaces; `suggestion` names which entry could legitimately carry the
    evidence, never drafted bullet text.
    """

    requirement_terms = [
        *parsed_jd.core_must_have_skills,
        *parsed_jd.supporting_skills,
        *parsed_jd.technical_skills,
    ]

    bullet_text = " ".join(
        bullet
        for entry in (*selected_content.experience, *selected_content.education, *selected_content.projects)
        for bullet in entry.bullets
    )

    findings: list[dict] = []

    for requirement in requirement_terms:
        found_in: list[str] = []

        for fact in facts.work_experience.entries:
            if fact.tools and _term_mentioned(fact.tools, requirement):
                found_in.append(f"tools line: {fact.position}")

        for fact in facts.projects.entries:
            if fact.tools and _term_mentioned(fact.tools, requirement):
                found_in.append(f"tools line: {fact.name}")

        for group in facts.skills.groups:
            items_text = ", ".join(group.items)

            if _term_mentioned(items_text, requirement):
                found_in.append(f"skill group: {group.name}")

        if not found_in:
            # Not true of the candidate anywhere in the fact base -- a
            # different problem (weak_requirements /
            # underrepresented_requirements), not this diagnostic's.
            continue

        if _term_mentioned(bullet_text, requirement):
            continue

        first_entry_name = found_in[0].split(": ", 1)[1]

        findings.append(
            {
                "requirement": requirement,
                "found_in": found_in,
                "suggestion": (
                    f"'{first_entry_name}' bullets could legitimately demonstrate "
                    f"{requirement} -- edit cv_facts.yaml to describe it, do not "
                    "auto-generate bullet text"
                ),
            }
        )

    return findings
