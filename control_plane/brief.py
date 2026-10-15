from control_plane.cover_letter_containment import CLOSING_LINE, known_organisations, real_held_titles
from control_plane.state import CoverLetterState
from cv.facts import CVFacts
from agents.fact_render import render_facts_with_ids
from guidelines import GENERIC_HOOK_EXAMPLES, LETTER_LENGTH_RULE, JD_VOCABULARY_MIRRORING_GUIDANCE, TRADE_OFF_OWNERSHIP_GUIDANCE


def build_brief(state: CoverLetterState, facts: CVFacts, applied_for_role: str, strongest_evidence: str | None) -> str:
    """Everything a drafter needs to write the letter, from approved evidence only. Rules are imported, not pasted."""

    jd = state.parsed_jd
    organisations = ", ".join(known_organisations(facts, jd.company_name)) or "(none)"
    titles = ", ".join(real_held_titles(facts)) or "(none)"
    hooks = "\n".join(f"- {example}" for example in GENERIC_HOOK_EXAMPLES)
    sections = [
        "# Cover letter brief",
        f"Applying for (NOT a role the candidate has held): {applied_for_role}\nCompany: {jd.company_name or '(not stated)'}",
        f"## Parsed job description\n{jd.model_dump_json(indent=2)}",
        f"## Match analysis\n{state.match_analysis.model_dump_json(indent=2)}",
        f"## Strongest evidence (the CV leads with this)\n{strongest_evidence or '(none)'}",
        f"## Fact base (the ONLY source of claims; IDs in brackets)\n{render_facts_with_ids(facts)}",
        f"## Real employers and institutions\n{organisations}\n\n## Real held titles\n{titles}",
        "## Rules\n"
        f"- Plain text. {LETTER_LENGTH_RULE} End with the line {CLOSING_LINE!r} then {facts.personal.full_name!r}.\n"
        "- Never state an employer, institution or held title outside the lists above.\n"
        f"- Do not open with generic wording such as:\n{hooks}\n"
        f"{TRADE_OFF_OWNERSHIP_GUIDANCE}\n\n{JD_VOCABULARY_MIRRORING_GUIDANCE}",
    ]

    return "\n\n".join(sections) + "\n"
