from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

from cv.containment import check_containment
from cv.facts import CVFacts, ids_by_kind
from models.jd_schema import ParsedJD


load_dotenv()
client = OpenAI()

MAX_ATTEMPTS = 2

MIDDLE_SECTIONS = {"skills", "experience", "projects", "education"}

SYSTEM_PROMPT = (
    "You are ranking a candidate's real CV facts against one job description. "
    "You never invent experience, numbers, employers, or skills -- you only judge "
    "and rank facts that are explicitly given to you in the fact base below.\n\n"

    "Every fact-base item has a stable ID in brackets, e.g. [exp.sms-group.b2]. "
    "Reference items ONLY by these exact IDs. Do not rank or cite an ID that is "
    "not shown to you.\n\n"

    "Rank bullets, projects, and skill groups by how strongly each evidences the "
    "job description's requirements. Rank 1 is strongest within its own list.\n\n"

    "For every ranked bullet or project, set evidences_requirement to the exact "
    "requirement text (copied verbatim from the parsed job description's "
    "core_must_have_skills, supporting_skills, eligibility_constraints, or "
    "nice_to_have_skills) that it evidences, or null if it does not clearly "
    "evidence any single named requirement.\n\n"

    "section_order lists exactly the four sections skills, experience, projects, "
    "education -- a permutation of these four, nothing added, nothing removed -- "
    "in the order they should appear on the CV, strongest evidence for this "
    "specific role first. section_order_reason explains that choice in one "
    "concise sentence, written before section_order.\n\n"

    "target_title should reflect the job description's own title, or a close, "
    "honest variant a candidate with this fact base could credibly use -- never "
    "a title implying seniority or a role the fact base does not support."
)

PROFILE_SYSTEM_PROMPT = (
    "You write the 2-3 line profile summary for one already-finalised CV. You never "
    "invent experience, numbers, employers, or skills -- you only reference facts "
    "explicitly shown to you below.\n\n"

    "What is shown to you below is NOT the full fact base -- it is only the content "
    "that survived selection and actually appears on this specific CV. Some real "
    "facts about the candidate were cut for this application and must not be "
    "referenced, even though they are true.\n\n"

    "Every shown item has a stable ID in brackets. profile_evidence lists the exact "
    "IDs that back every claim in profile. Reference ONLY IDs shown to you here.\n\n"

    "profile is a 2-3 line, evidence-based summary connecting the candidate to this "
    "role, using only facts named in profile_evidence, written after "
    "profile_evidence, conditioned on it."
)


class ItemRank(BaseModel):
    id: str
    rank: int
    evidences_requirement: str | None = None


class CVSelection(BaseModel):
    section_order_reason: str                 # why this middle order
    section_order: list[str]                  # the four middle sections only
    bullet_ranks: list[ItemRank]
    project_ranks: list[ItemRank]
    skill_group_ranks: list[ItemRank]
    target_title: str


class ProfileSelection(BaseModel):
    profile_evidence: list[str]                # IDs of surviving content backing the profile
    profile: str = Field(max_length=320)       # written after profile_evidence, conditioned on it


def _render_facts_with_ids(facts: CVFacts) -> str:
    lines: list[str] = []

    experience_ids = ids_by_kind(facts, "experience")
    education_ids = ids_by_kind(facts, "education")
    project_ids = ids_by_kind(facts, "project")
    skill_group_ids = ids_by_kind(facts, "skill_group")

    lines.append("WORK EXPERIENCE (tier 1, always renders in full -- rank bullets only):")
    for entry_id, fact in zip(experience_ids, facts.work_experience.entries):
        lines.append(f"[{entry_id}] {fact.position} -- {fact.organisation}, {fact.city} ({fact.dates})")
        for index, bullet in enumerate(fact.bullets, start=1):
            lines.append(f"  [{entry_id}.b{index}] {bullet}")

    lines.append("")
    lines.append("EDUCATION (tier 1, always renders in full -- rank bullets only):")
    for entry_id, fact in zip(education_ids, facts.education.entries):
        lines.append(f"[{entry_id}] {fact.degree} -- {fact.institution}, {fact.city} ({fact.dates})")
        for index, bullet in enumerate(fact.bullets, start=1):
            lines.append(f"  [{entry_id}.b{index}] {bullet}")

    lines.append("")
    lines.append("PROJECTS (rank for inclusion, 2-3 kept downstream):")
    for entry_id, fact in zip(project_ids, facts.projects.entries):
        lines.append(f"[{entry_id}] {fact.name} ({fact.dates}) -- {fact.intro}")
        for index, bullet in enumerate(fact.bullets, start=1):
            lines.append(f"  [{entry_id}.b{index}] {bullet}")

    lines.append("")
    lines.append("SKILL GROUPS (rank for inclusion, top groups kept downstream):")
    for group_id, group in zip(skill_group_ids, facts.skills.groups):
        lines.append(f"[{group_id}] {group.name}: {', '.join(group.items)}")

    if facts.coursework.items:
        lines.append("")
        lines.append(
            "COURSEWORK (tier 3, single unit -- included only if the JD names a "
            "coursework item):"
        )
        lines.append(f"[coursework] {'; '.join(facts.coursework.items)}")

    lines.append("")
    lines.append("CERTIFICATIONS (tier 1, always renders in full):")
    for cert in facts.certifications.entries:
        lines.append(f"- {cert.name} -- {cert.issuer}")

    lines.append("")
    lines.append("LANGUAGES (tier 1, always renders in full):")
    for language_fact in facts.languages.entries:
        lines.append(f"- {language_fact.language} ({language_fact.level})")

    return "\n".join(lines)


def _requirement_texts(parsed_jd: ParsedJD) -> set[str]:
    return {
        *parsed_jd.core_must_have_skills,
        *parsed_jd.supporting_skills,
        *parsed_jd.eligibility_constraints,
        *parsed_jd.nice_to_have_skills,
    }


def validate_selection(
    selection: CVSelection,
    facts: CVFacts,
    parsed_jd: ParsedJD,
) -> list[str]:
    """
    Deterministic gate on the LLM's output. Returns a list of violation
    messages; empty means the selection is usable as-is.
    """

    errors: list[str] = []
    requirement_texts = _requirement_texts(parsed_jd)

    all_ranks = [
        *selection.bullet_ranks,
        *selection.project_ranks,
        *selection.skill_group_ranks,
    ]

    for item in all_ranks:
        if facts.by_id(item.id) is None:
            errors.append(f"unknown id in rank list: {item.id}")

    # The prompt only asks for a verbatim evidences_requirement on bullets
    # and projects ("For every ranked bullet or project..."); skill groups
    # are never asked to be exact-quote precise, so don't hold them to it.
    for item in [*selection.bullet_ranks, *selection.project_ranks]:
        if (
            item.evidences_requirement is not None
            and item.evidences_requirement not in requirement_texts
        ):
            errors.append(
                "evidences_requirement not found in parsed JD: "
                f"{item.evidences_requirement!r} (id={item.id})"
            )

    if len(selection.section_order) != len(MIDDLE_SECTIONS) or set(
        selection.section_order
    ) != MIDDLE_SECTIONS:
        errors.append(
            f"section_order must be a permutation of {sorted(MIDDLE_SECTIONS)}, "
            f"got {selection.section_order}"
        )

    # Hard fail: every company name, tool name and number in the
    # generated text must be grounded in the fact base or the JD.
    for violation in check_containment(selection.target_title, facts, parsed_jd):
        errors.append(f"target_title contains an ungrounded entity: {violation!r}")

    return errors


def _call_selector(
    facts_block: str,
    jd_block: str,
    feedback: str | None,
) -> CVSelection:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Fact base:\n{facts_block}\n\nParsed job description:\n{jd_block}",
        },
    ]

    if feedback:
        messages.append({"role": "user", "content": feedback})

    response = client.beta.chat.completions.parse(
        model="gpt-4o",
        temperature=0,
        seed=42,
        messages=messages,
        response_format=CVSelection,
    )

    selection = response.choices[0].message.parsed

    if selection is None:
        raise ValueError("CV selector returned no structured CVSelection.")

    return selection


def select_cv_content(facts: CVFacts, parsed_jd: ParsedJD) -> CVSelection:
    """
    Call 1 of 2: rank fact-base items against one JD, choose section order
    and a target title. No profile is written here -- see write_profile().

    Retries once, with the specific validation failures fed back, if the
    model's output references an unknown ID, cites a requirement the JD
    never named, or returns a malformed section_order.
    """

    facts_block = _render_facts_with_ids(facts)
    jd_block = parsed_jd.model_dump_json(indent=2)

    feedback = None
    last_errors: list[str] = []

    for _attempt in range(1, MAX_ATTEMPTS + 1):
        selection = _call_selector(facts_block, jd_block, feedback)
        errors = validate_selection(selection, facts, parsed_jd)

        if not errors:
            return selection

        last_errors = errors
        feedback = (
            "The previous response was invalid for these reasons:\n"
            + "\n".join(f"- {error}" for error in errors)
            + "\nFix these specific problems and return a corrected, fully valid response."
        )

    raise ValueError(
        "CV selector output failed validation after "
        f"{MAX_ATTEMPTS} attempts: " + "; ".join(last_errors)
    )


def validate_profile_selection(
    profile_selection: ProfileSelection,
    facts: CVFacts,
    parsed_jd: ParsedJD,
    valid_ids: set[str],
) -> list[str]:
    errors: list[str] = []

    for evidence_id in profile_selection.profile_evidence:
        if evidence_id not in valid_ids:
            errors.append(
                f"profile_evidence cites {evidence_id!r}, which is not present in "
                "the final rendered document"
            )

    for violation in check_containment(profile_selection.profile, facts, parsed_jd):
        errors.append(f"profile contains an ungrounded entity: {violation!r}")

    return errors


def _call_profile_writer(
    content_block: str,
    jd_block: str,
    feedback: str | None,
) -> ProfileSelection:
    messages = [
        {"role": "system", "content": PROFILE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Final CV content:\n{content_block}\n\nParsed job description:\n{jd_block}",
        },
    ]

    if feedback:
        messages.append({"role": "user", "content": feedback})

    response = client.beta.chat.completions.parse(
        model="gpt-4o",
        temperature=0,
        seed=42,
        messages=messages,
        response_format=ProfileSelection,
    )

    profile_selection = response.choices[0].message.parsed

    if profile_selection is None:
        raise ValueError("Profile writer returned no structured ProfileSelection.")

    return profile_selection


def write_profile(
    facts: CVFacts,
    parsed_jd: ParsedJD,
    content_block: str,
    valid_ids: set[str],
) -> ProfileSelection:
    """
    Call 2 of 2: write the profile from only the final, already-selected
    CV content (content_block), so it can never cite something the page
    budget or selection rules cut. Retries once on validation failure.
    """

    jd_block = parsed_jd.model_dump_json(indent=2)

    feedback = None
    last_errors: list[str] = []

    for _attempt in range(1, MAX_ATTEMPTS + 1):
        profile_selection = _call_profile_writer(content_block, jd_block, feedback)
        errors = validate_profile_selection(profile_selection, facts, parsed_jd, valid_ids)

        if not errors:
            return profile_selection

        last_errors = errors
        feedback = (
            "The previous response was invalid for these reasons:\n"
            + "\n".join(f"- {error}" for error in errors)
            + "\nFix these specific problems and return a corrected, fully valid response."
        )

    raise ValueError(
        "Profile writer output failed validation after "
        f"{MAX_ATTEMPTS} attempts: " + "; ".join(last_errors)
    )
