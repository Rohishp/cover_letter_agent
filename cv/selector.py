import re

from pydantic import BaseModel

from agents.client import client
from cv.checks import find_third_person_phrases, profile_opens_with
from cv.containment import check_citation_specificity, check_containment, check_jd_vocabulary_grounding
from cv.facts import CVFacts, ids_by_kind
from cv.schema import PROFILE_MAX_CHARS
from guidelines import (
    JD_VOCABULARY_MIRRORING_GUIDANCE,
    TRADE_OFF_OWNERSHIP_GUIDANCE,
)
from models.jd_schema import ParsedJD


MAX_ATTEMPTS = 2

# The profile writer gets extra attempts over MAX_ATTEMPTS: in practice
# (verified live against a real fact base) first-person prose consistently
# overshoots PROFILE_MAX_CHARS on the first try, and the model doesn't
# reliably converge in a single retry. Selection (MAX_ATTEMPTS) doesn't
# have this problem, so it stays separate rather than raising the shared
# constant for both. Bumped 3 -> 4 (Phase H): "my experience includes"
# proved unusually sticky, failing all 3 attempts twice in a row on a
# real run even after being named explicitly in both the prompt's own
# example list and the retry feedback.
PROFILE_MAX_ATTEMPTS = 5

MIDDLE_SECTIONS = {"skills", "experience", "projects", "education"}

# Stripped before comparing target_title against parsed_jd.job_title:
# gender markers (EN "m/f/x", DE "m/w/d") and generic seniority/employment
# adjectives that don't affect whether the ROLE described is the same one.
_TITLE_NOISE_TOKENS = {
    "m", "f", "x", "d", "w",
    "junior", "senior", "mid", "entry", "lead", "principal",
    "staff", "trainee", "intern", "associate",
}
_TITLE_STOPWORDS = {"a", "an", "the", "of", "and", "or", "for", "in", "at", "to", "with"}

FORCED_PROFILE_INSTRUCTION = (
    "This match was borderline and generation was explicitly forced by a "
    "human reviewer who has already seen the weak points. Build the single "
    "strongest, honest through-line connecting the most JD-relevant real "
    "evidence shown to you -- one clear narrative, not a list of disconnected "
    "facts. Do not overstate fit; state the genuine connection as directly and "
    "confidently as the evidence actually supports."
)

SYSTEM_PROMPT = (
    "You are ranking a candidate's real CV facts against one job description. "
    "You never invent experience, numbers, employers, or skills -- you only judge "
    "and rank facts that are explicitly given to you in the fact base below.\n\n"

    "Every fact-base item has a stable ID in brackets, e.g. [exp.sms-group.b2]. "
    "Reference items ONLY by these exact IDs. Do not rank or cite an ID that is "
    "not shown to you.\n\n"

    "Rank bullets, projects, and skill groups by how strongly each evidences the "
    "job description's requirements. Rank 1 is strongest within its own list.\n\n"

    f"{TRADE_OFF_OWNERSHIP_GUIDANCE}\n\n"

    f"{JD_VOCABULARY_MIRRORING_GUIDANCE}\n\n"

    "For every ranked bullet or project, set evidences_requirement to the exact "
    "requirement text (copied verbatim from the parsed job description's "
    "core_must_have_skills, supporting_skills, eligibility_constraints, or "
    "nice_to_have_skills) that it evidences, or null if it does not clearly "
    "evidence any single named requirement. These four lists are the ONLY valid "
    "source -- never copy text from technical_skills or any other field, even "
    "when the bullet's connection to the requirement runs through a specific "
    "technology named there.\n\n"

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
    "profile_evidence, conditioned on it.\n\n"

    "The FIRST SENTENCE must be built from the single highest-ranked project or "
    "experience item (when one is identified for you below) -- not just include it "
    "somewhere in the profile, lead with it. A lower-ranked fact, however "
    "senior-sounding or recent, belongs in a supporting sentence after the opening, "
    "never before it.\n\n"

    "Sentences after the first should be built from the next-highest-ranked "
    "JD-relevant evidence -- when a requirement-coverage list is shown to you below, "
    "prefer citing the evidence for a requirement on that list over a fact with no "
    "JD linkage at all, even if that fact is chronologically or academically more "
    "prominent. Never fill a sentence with a bare list of skills that has no "
    "connection to a specific requirement -- every sentence should read as if it "
    "was written for this JD, not any application.\n\n"

    "You do not need to mention every remaining skill or tool -- the profile is only "
    "2-3 lines. If you run out of room, stop after the strongest 2-3 pieces of "
    "evidence rather than adding a closing sentence that just lists whatever "
    "wasn't mentioned yet. That closing-list impulse is exactly what produces "
    "generic filler like 'my skills include' or 'my experience includes' -- if "
    "you notice yourself about to write a sentence whose only content is a list of "
    "skills/tools with no single requirement it's proving, delete that sentence "
    "instead of keeping it.\n\n"

    f"profile MUST be at most {PROFILE_MAX_CHARS} characters -- not words, "
    f"characters, counted exactly. Write it in the "
    f"{PROFILE_MAX_CHARS - 60}-{PROFILE_MAX_CHARS - 20} character range so it "
    "has margin. This is checked deterministically and enforced with no "
    "truncation: going over the limit means the whole profile is rejected "
    "and you have to rewrite it from scratch, so favor one or two shorter, "
    "punchier sentences over a longer one with more clauses.\n\n"

    "Every sentence that cites a fact must also carry at least one distinguishing "
    "detail from that fact's own bullet text -- a number, or a named method or "
    "technology -- not just the fact's existence. 'exemplifies my ability to design "
    "and deploy AI solutions with precision' cites a real project while saying "
    "nothing that project's own bullets don't already make specific (which "
    "experiment, which number, which tool). This is checked deterministically: a "
    "sentence with no shared distinguishing detail from what it cites is rejected, "
    "the same way an uncited claim is. Avoid generic CV boilerplate such as "
    "'results-driven professional', 'passionate about leveraging', 'proven track "
    "record', 'team player', 'detail-oriented', 'self-starter', 'my skills "
    "include', 'my experience includes' -- language that could describe anyone "
    "fails this check structurally, since it shares nothing specific with any "
    "cited fact.\n\n"

    "Write in first person, as the candidate describing themselves "
    "(\"I built...\", \"my experience...\"). Never use third-person "
    "candidate-referring language such as 'this candidate', 'the "
    "candidate', 'their experience', or 'they have' -- nobody writes their "
    "own CV summary about themselves in the third person.\n\n"

    f"{JD_VOCABULARY_MIRRORING_GUIDANCE}"
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
    # No max_length here (item 1): a hard schema cap gets enforced as a
    # silent mid-word truncation rather than a validation failure. Length
    # is checked deterministically in validate_profile_selection instead,
    # which triggers the normal retry path on a violation.
    profile: str                               # written after profile_evidence, conditioned on it


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
    for cert_id, cert in zip(ids_by_kind(facts, "certification"), facts.certifications.entries):
        lines.append(f"[{cert_id}] {cert.name} -- {cert.issuer}")

    lines.append("")
    lines.append("LANGUAGES (tier 1, always renders in full):")
    for lang_id, language_fact in zip(ids_by_kind(facts, "language"), facts.languages.entries):
        lines.append(f"[{lang_id}] {language_fact.language} ({language_fact.level})")

    return "\n".join(lines)


def _requirement_texts(parsed_jd: ParsedJD) -> set[str]:
    return {
        *parsed_jd.core_must_have_skills,
        *parsed_jd.supporting_skills,
        *parsed_jd.eligibility_constraints,
        *parsed_jd.nice_to_have_skills,
    }


def _title_tokens(title: str) -> set[str]:
    without_parens = re.sub(r"\([^)]*\)", " ", title.lower())
    words = re.findall(r"[a-z0-9]+", without_parens)
    return {word for word in words if word not in _TITLE_NOISE_TOKENS and word not in _TITLE_STOPWORDS}


def title_overlaps_job_title(target_title: str, job_title: str | None) -> bool:
    """
    True when job_title is null (nothing to compare against, so the
    model's honest variant is allowed unchanged) or when target_title
    shares at least half of job_title's significant tokens.
    """

    if not job_title:
        return True

    jd_tokens = _title_tokens(job_title)

    if not jd_tokens:
        return True

    target_tokens = _title_tokens(target_title)
    shared = jd_tokens & target_tokens

    return len(shared) >= max(1, len(jd_tokens) // 2)


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

    if not title_overlaps_job_title(selection.target_title, parsed_jd.job_title):
        errors.append(
            f"target_title {selection.target_title!r} does not share significant "
            f"token overlap with the JD's job_title {parsed_jd.job_title!r}"
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
    top_ranked_opening_label: str | None = None,
) -> list[str]:
    errors: list[str] = []

    for evidence_id in profile_selection.profile_evidence:
        if evidence_id not in valid_ids:
            errors.append(
                f"profile_evidence cites {evidence_id!r}, which is not present in "
                "the final rendered document"
            )

    cited_ids = set(profile_selection.profile_evidence)

    # Scoped to what the profile actually CITED, not the whole fact base
    # (Phase J item 2) -- a profile citing proj.pr-review-agent but
    # naming a proper noun/number that only appears in a different,
    # uncited entry is exactly as ungrounded as citing nothing at all.
    for violation in check_containment(profile_selection.profile, facts, parsed_jd, only_ids=cited_ids):
        errors.append(f"profile contains an ungrounded entity: {violation!r}")

    # check_containment only catches proper nouns/numbers; a real JD
    # word mirrored into the profile with no cited fact to support it
    # (e.g. "ensuring compliance" with no compliance-related fact cited)
    # is invisible to it -- see check_jd_vocabulary_grounding's docstring.
    for violation in check_jd_vocabulary_grounding(
        profile_selection.profile, facts, parsed_jd, list(cited_ids)
    ):
        errors.append(
            f"profile uses the JD's own word {violation!r} but no cited fact "
            f"(profile_evidence: {sorted(cited_ids)}) supports it"
        )

    # Phase K: citation proves the claim isn't invented; specificity
    # proves it isn't generic. Replaces the old banned-phrase list -- a
    # profile forced to carry a real distinguishing detail from its own
    # cited evidence has no room left to be boilerplate.
    for violation in check_citation_specificity(
        profile_selection.profile, facts, list(cited_ids)
    ):
        errors.append(f"profile lacks specificity: {violation}")

    if len(profile_selection.profile) > PROFILE_MAX_CHARS:
        over_by = len(profile_selection.profile) - PROFILE_MAX_CHARS
        errors.append(
            f"profile is {len(profile_selection.profile)} chars, {over_by} over "
            f"the {PROFILE_MAX_CHARS}-char limit -- cut a whole clause or "
            f"sentence, not individual words, to land at {PROFILE_MAX_CHARS - 40} "
            "chars or fewer, well under the limit so it survives without "
            "cutting off mid-sentence"
        )

    for phrase in find_third_person_phrases(profile_selection.profile):
        errors.append(f"profile uses third-person candidate language: {phrase!r}")

    if top_ranked_opening_label and not profile_opens_with(
        profile_selection.profile, top_ranked_opening_label
    ):
        errors.append(
            f"profile does not open with the top-ranked evidence "
            f"({top_ranked_opening_label!r}) -- the first sentence must be built "
            "from it, not a lower-ranked fact"
        )

    return errors


def _format_requirement_coverage(requirement_coverage: dict[str, list[str]]) -> str:
    return "\n".join(
        f"- {requirement}: evidenced by {', '.join(fact_ids)}"
        for requirement, fact_ids in requirement_coverage.items()
    )


def _call_profile_writer(
    content_block: str,
    jd_block: str,
    feedback: str | None,
    forced: bool = False,
    top_ranked_evidence: str | None = None,
    requirement_coverage: dict[str, list[str]] | None = None,
) -> ProfileSelection:
    system_content = PROFILE_SYSTEM_PROMPT

    if forced:
        system_content = f"{system_content}\n\n{FORCED_PROFILE_INSTRUCTION}"

    user_content = f"Final CV content:\n{content_block}\n\nParsed job description:\n{jd_block}"

    if top_ranked_evidence:
        user_content += (
            "\n\nThe selector's own relevance ranking already identified this as "
            "the strongest available evidence for this specific role -- your FIRST "
            "sentence must be built from it, not around whichever entry merely "
            "sounds most senior or most recently credentialed, unless it "
            "genuinely has no substance to draw from. Other true facts can follow "
            "in supporting sentences after the opening:\n"
            f"{top_ranked_evidence}"
        )

    if requirement_coverage:
        user_content += (
            "\n\nJD requirements with real fact-base evidence -- prefer building "
            "sentences after the first from these over an unlinked fact:\n"
            f"{_format_requirement_coverage(requirement_coverage)}"
        )

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
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
    forced: bool = False,
    top_ranked_evidence: str | None = None,
    top_ranked_opening_label: str | None = None,
    requirement_coverage: dict[str, list[str]] | None = None,
) -> ProfileSelection:
    """
    Call 2 of 2: write the profile from only the final, already-selected
    CV content (content_block), so it can never cite something the page
    budget or selection rules cut. Retries up to PROFILE_MAX_ATTEMPTS - 1
    times on validation failure.

    forced: when the match gate was overridden, ask for the single
    strongest honest through-line (item 8) -- the evidence-citation
    validator below is unchanged either way.

    top_ranked_evidence (Phase F item 1): the selector's own rank-1
    project and top-ranked experience bullet, as plain text -- without
    this the profile was observed defaulting to whichever entry sounded
    most senior/recent rather than the actual highest-relevance evidence.

    top_ranked_opening_label (Phase F addendum 3, item 1): the rank-1
    project's plain name, checked deterministically against the profile's
    first sentence -- including the top-ranked evidence isn't enough if
    it's buried in a later sentence behind a less-relevant fact.

    requirement_coverage (Phase H item 4): {jd_requirement: [fact_ids]}
    for every JD requirement term with locatable fact-base evidence --
    same input, same shared helper (requirement_evidence_fact_ids in
    cv/selection_rules.py) as the letter's coverage retry. Without this
    the profile's later sentences defaulted to the next chronologically
    prominent fact (e.g. an unrelated thesis) or generic filler ("My
    skills include...") instead of the next-most-JD-relevant evidence.
    """

    jd_block = parsed_jd.model_dump_json(indent=2)

    feedback = None
    last_errors: list[str] = []

    for _attempt in range(1, PROFILE_MAX_ATTEMPTS + 1):
        profile_selection = _call_profile_writer(
            content_block, jd_block, feedback, forced=forced, top_ranked_evidence=top_ranked_evidence,
            requirement_coverage=requirement_coverage,
        )
        errors = validate_profile_selection(
            profile_selection, facts, parsed_jd, valid_ids,
            top_ranked_opening_label=top_ranked_opening_label,
        )

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
        f"{PROFILE_MAX_ATTEMPTS} attempts: " + "; ".join(last_errors)
    )
