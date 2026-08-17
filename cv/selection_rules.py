import re

from pydantic import BaseModel

from cv.facts import CVFacts, ids_by_kind
from cv.render import FIRST_SECTION, LAST_SECTIONS, validate_section_order
from cv.schema import (
    Certification,
    CVContent,
    EducationEntry,
    ExperienceEntry,
    Language,
    ProjectEntry,
    SkillGroup,
)
from cv.selector import CVSelection, ItemRank
from models.jd_schema import ParsedJD


MAX_SKILL_GROUPS = 4
MIN_PROJECTS = 2
MAX_PROJECTS = 3

EXPERIENCE_BULLET_MAX = 5
EDUCATION_BULLET_MAX = 4
PROJECT_RESULT_BULLET_MAX = 4

EXPERIENCE_BULLET_MIN = 3
EDUCATION_BULLET_MIN = 0
PROJECT_RESULT_BULLET_MIN = 1

# Large but finite: an unranked bullet must still be adjustable by
# FIGURE_RANK_BONUS below (inf - bonus == inf, which would silently
# defeat the bonus for every unranked bullet).
WORST_RANK = 1_000_000.0

# A fixed nudge applied to any bullet containing a figure before ranking,
# so a quantified line reliably outranks a similarly-scored unquantified
# one instead of relying on a tie-break that almost never fires (model
# ranks are rarely exactly tied). The figure-density floor in
# cv/density_floor.py is the actual guarantee; this bonus is a first pass.
FIGURE_RANK_BONUS = 2.0

# A single bullet reading exactly this is a status marker, not real
# content -- render it on the dates line instead of as a bullet.
IN_PROGRESS_MARKER = "in progress."

# Used only during page-fit and the density floor, before the real
# profile is written (item 4: profile is written last, from the final
# selected content). Deliberately sized at the schema max so a fit
# validated against this placeholder can never be broken by the real
# (equal-or-shorter) profile that replaces it.
PROFILE_PLACEHOLDER = (
    "Placeholder profile text reserving maximum layout space during selection "
    "and page-fit. The real, evidence-based profile is written after final "
    "content is chosen and replaces this text before the CV is delivered to "
    "reserve worst-case space so the real, shorter profile always fits."
)[:320]


def _has_digit(text: str) -> bool:
    return any(char.isdigit() for char in text)


def _rank_map(ranks: list[ItemRank]) -> dict[str, ItemRank]:
    return {item.id: item for item in ranks}


def _effective_rank(bullet_id: str, text: str, rank_map: dict[str, ItemRank]) -> float:
    ranked = rank_map.get(bullet_id)
    base_rank = ranked.rank if ranked is not None else WORST_RANK
    return base_rank - FIGURE_RANK_BONUS if _has_digit(text) else base_rank


class ExclusionNote(BaseModel):
    kind: str          # "project" | "skill_group" | "bullet"
    id: str
    label: str
    reason: str
    rank: float | None = None


class SelectionReport(BaseModel):
    section_order: list[str]           # full 8-section order, head+middle+tail
    section_order_reason: str
    excluded_projects: list[ExclusionNote] = []
    excluded_skill_groups: list[ExclusionNote] = []
    excluded_bullets: list[ExclusionNote] = []   # filled in by the page-fit step


class SelectionState(BaseModel):
    """
    The current, mutable budget: which projects and skill groups are
    still included, how many bullets each bullet-bearing entry may keep,
    and any explicit bullet-set overrides (set only by the figure-density
    floor's swaps, which replace one specific bullet with another rather
    than just shrinking a count).
    """

    project_ids: list[str]             # kept projects, in rank order (best first)
    skill_group_ids: list[str]         # kept skill groups, in rank order (best first)
    bullet_caps: dict[str, int]        # entry_id -> current max bullets for that entry
    bullet_overrides: dict[str, list[str]] = {}   # entry_id -> explicit bullet texts to render


def resolve_section_order(selection: CVSelection) -> list[str]:
    full_order = [FIRST_SECTION, *selection.section_order, *LAST_SECTIONS]
    validate_section_order(full_order)
    return full_order


def select_top_bullets(
    bullet_items: list[tuple[str, str]],
    rank_map: dict[str, ItemRank],
    max_count: int,
) -> list[str]:
    """
    Keep the highest-ranked bullets (figure bonus already folded into the
    rank via _effective_rank), capped at max_count. Kept bullets are
    returned in their original order.
    """

    if len(bullet_items) <= max_count:
        return [text for _bullet_id, text in bullet_items]

    ordered = sorted(
        bullet_items,
        key=lambda item: _effective_rank(item[0], item[1], rank_map),
    )
    kept_ids = {bullet_id for bullet_id, _text in ordered[:max_count]}

    return [text for bullet_id, text in bullet_items if bullet_id in kept_ids]


def sort_bullets_by_priority(
    bullet_items: list[tuple[str, str]],
    rank_map: dict[str, ItemRank],
) -> list[tuple[str, str]]:
    """
    Same priority order as select_top_bullets, without capping -- used by
    the page-fit and density-floor steps to know exactly which bullet is
    "next to drop" or "best to swap in" for a given entry.
    """

    return sorted(
        bullet_items,
        key=lambda item: _effective_rank(item[0], item[1], rank_map),
    )


def _kept_bullets_for_entry(
    entry_id: str,
    bullet_items: list[tuple[str, str]],
    rank_map: dict[str, ItemRank],
    state: SelectionState,
) -> list[str]:
    if entry_id in state.bullet_overrides:
        override_texts = set(state.bullet_overrides[entry_id])
        return [text for _bullet_id, text in bullet_items if text in override_texts]

    return select_top_bullets(bullet_items, rank_map, state.bullet_caps[entry_id])


def _fact_for_entry(facts: CVFacts, entry_id: str, kind: str):
    if kind == "experience":
        entries = facts.work_experience.entries
    elif kind == "education":
        entries = facts.education.entries
    elif kind == "project":
        entries = facts.projects.entries
    else:
        raise ValueError(f"no bullet-bearing entries for kind={kind!r}")

    for candidate_id, fact in zip(ids_by_kind(facts, kind), entries):
        if candidate_id == entry_id:
            return fact

    raise KeyError(entry_id)


def _is_in_progress_only(bullets: list[str]) -> bool:
    return len(bullets) == 1 and bullets[0].strip().lower() == IN_PROGRESS_MARKER


def _is_ongoing(dates: str) -> bool:
    lowered = dates.lower()
    return "present" in lowered or "ongoing" in lowered


def _end_year_month(dates: str) -> int:
    matches = re.findall(r"(\d{2})\.(\d{4})", dates)

    if not matches:
        return 0

    month, year = matches[-1]
    return int(year) * 100 + int(month)


def most_recent_completed_education_id(facts: CVFacts) -> str | None:
    """
    The education entry -- among those not still in progress -- with the
    latest end date. Only this entry keeps its bullets; older completed
    degrees render as a heading line only. Deterministic date-string
    parsing, no judgment involved.
    """

    entry_ids = ids_by_kind(facts, "education")
    completed = [
        (entry_id, fact)
        for entry_id, fact in zip(entry_ids, facts.education.entries)
        if not _is_ongoing(fact.dates)
    ]

    if not completed:
        return None

    completed.sort(key=lambda pair: _end_year_month(pair[1].dates), reverse=True)
    return completed[0][0]


def initial_state(
    facts: CVFacts,
    selection: CVSelection,
    parsed_jd: ParsedJD,
) -> tuple[SelectionState, SelectionReport]:
    """
    Compute the starting budget: which projects and skill groups are
    included, and the bullet cap for every bullet-bearing entry. This is
    where inclusion/exclusion is decided; the page-fit loop only shrinks
    what this returns, and the density floor only swaps within it.
    """

    project_ids, excluded_projects = _ranked_projects(facts, selection)
    skill_group_ids, excluded_skill_groups = _top_skill_groups(facts, selection)

    most_recent_education_id = most_recent_completed_education_id(facts)

    bullet_caps: dict[str, int] = {}

    for entry_id, fact in zip(ids_by_kind(facts, "experience"), facts.work_experience.entries):
        bullet_caps[entry_id] = min(EXPERIENCE_BULLET_MAX, len(fact.bullets))

    for entry_id, fact in zip(ids_by_kind(facts, "education"), facts.education.entries):
        if _is_in_progress_only(fact.bullets):
            bullet_caps[entry_id] = 0
        elif entry_id != most_recent_education_id:
            bullet_caps[entry_id] = 0
        else:
            bullet_caps[entry_id] = min(EDUCATION_BULLET_MAX, len(fact.bullets))

    for entry_id, fact in zip(ids_by_kind(facts, "project"), facts.projects.entries):
        if entry_id in project_ids:
            bullet_caps[entry_id] = min(PROJECT_RESULT_BULLET_MAX, len(fact.bullets))

    report = SelectionReport(
        section_order=resolve_section_order(selection),
        section_order_reason=selection.section_order_reason,
        excluded_projects=excluded_projects,
        excluded_skill_groups=excluded_skill_groups,
    )

    state = SelectionState(
        project_ids=project_ids,
        skill_group_ids=skill_group_ids,
        bullet_caps=bullet_caps,
    )

    return state, report


def _ranked_projects(
    facts: CVFacts,
    selection: CVSelection,
) -> tuple[list[str], list[ExclusionNote]]:
    """
    Rank all projects by JD relevance; keep between MIN_PROJECTS and
    MAX_PROJECTS. The page budget (cv/page_fit.py) is what prevents
    bloat -- this rule only ever subtracts the weakest projects, never
    excludes a project for lack of a specific uncovered requirement.
    """

    project_ids = ids_by_kind(facts, "project")
    rank_map = _rank_map(selection.project_ranks)

    scored = []

    for project_id, fact in zip(project_ids, facts.projects.entries):
        ranked = rank_map.get(project_id)
        rank = ranked.rank if ranked is not None else WORST_RANK
        scored.append((rank, project_id, fact))

    ordered = sorted(scored, key=lambda triple: triple[0])
    keep_count = min(MAX_PROJECTS, len(ordered))

    kept = ordered[:keep_count]
    dropped = ordered[keep_count:]

    excluded = [
        ExclusionNote(
            kind="project",
            id=project_id,
            label=fact.name,
            reason=(
                "unranked, " if rank == WORST_RANK else f"rank {int(rank)}, "
            )
            + f"cut by {MAX_PROJECTS}-project cap",
            rank=None if rank == WORST_RANK else rank,
        )
        for rank, project_id, fact in dropped
    ]

    return [project_id for _rank, project_id, _fact in kept], excluded


def _top_skill_groups(
    facts: CVFacts,
    selection: CVSelection,
) -> tuple[list[str], list[ExclusionNote]]:
    group_ids = ids_by_kind(facts, "skill_group")
    rank_map = _rank_map(selection.skill_group_ranks)

    scored = []

    for group_id, group in zip(group_ids, facts.skills.groups):
        ranked = rank_map.get(group_id)
        rank = ranked.rank if ranked else WORST_RANK
        scored.append((rank, group_id, group))

    ordered = sorted(scored, key=lambda triple: triple[0])
    kept = ordered[:MAX_SKILL_GROUPS]
    dropped = ordered[MAX_SKILL_GROUPS:]

    excluded = [
        ExclusionNote(
            kind="skill_group",
            id=group_id,
            label=group.name,
            reason="cut by top-4 cap",
            rank=None if rank == WORST_RANK else rank,
        )
        for rank, group_id, group in dropped
    ]

    return [group_id for _rank, group_id, _group in kept], excluded


def select_coursework(facts: CVFacts, parsed_jd: ParsedJD) -> list[str]:
    if not facts.coursework.items:
        return []

    jd_terms = [
        *parsed_jd.core_must_have_skills,
        *parsed_jd.supporting_skills,
        *parsed_jd.technical_skills,
        *parsed_jd.nice_to_have_skills,
        *parsed_jd.eligibility_constraints,
    ]

    coursework_text = " ".join(facts.coursework.items).lower()

    for term in jd_terms:
        if term.strip() and term.lower() in coursework_text:
            return list(facts.coursework.items)

    return []


def materialize(
    facts: CVFacts,
    parsed_jd: ParsedJD,
    selection: CVSelection,
    state: SelectionState,
    profile: str,
) -> CVContent:
    """
    Pure: build the CVContent that a given SelectionState (and a given
    profile string) describes. Used for page-fit iterations, the density
    floor's trial renders, and the final render alike.
    """

    bullet_rank_map = _rank_map(selection.bullet_ranks)

    experience = []

    for entry_id, fact in zip(ids_by_kind(facts, "experience"), facts.work_experience.entries):
        bullet_items = [
            (f"{entry_id}.b{index}", bullet)
            for index, bullet in enumerate(fact.bullets, start=1)
        ]
        kept = _kept_bullets_for_entry(entry_id, bullet_items, bullet_rank_map, state)

        experience.append(
            ExperienceEntry(
                position=fact.position,
                organisation=fact.organisation,
                city=fact.city,
                dates=fact.dates,
                tools=fact.tools,
                topic=fact.topic,
                bullets=kept,
            )
        )

    education = []

    for entry_id, fact in zip(ids_by_kind(facts, "education"), facts.education.entries):
        dates = fact.dates

        if _is_in_progress_only(fact.bullets):
            dates = f"{fact.dates}, ongoing"

        bullet_items = [
            (f"{entry_id}.b{index}", bullet)
            for index, bullet in enumerate(fact.bullets, start=1)
        ]
        kept = _kept_bullets_for_entry(entry_id, bullet_items, bullet_rank_map, state)

        education.append(
            EducationEntry(
                position=fact.degree,
                organisation=fact.institution,
                city=fact.city,
                dates=dates,
                bullets=kept,
            )
        )

    project_facts = {
        entry_id: fact
        for entry_id, fact in zip(ids_by_kind(facts, "project"), facts.projects.entries)
    }

    projects = []

    for entry_id in state.project_ids:
        fact = project_facts[entry_id]
        result_bullet_items = [
            (f"{entry_id}.b{index}", bullet)
            for index, bullet in enumerate(fact.bullets, start=1)
        ]
        kept_results = _kept_bullets_for_entry(entry_id, result_bullet_items, bullet_rank_map, state)

        projects.append(
            ProjectEntry(
                position=fact.name,
                organisation="Personal project",
                city="",
                dates=fact.dates,
                tools=fact.tools,
                bullets=[fact.intro, *kept_results],
            )
        )

    skill_group_facts = {
        group_id: group
        for group_id, group in zip(ids_by_kind(facts, "skill_group"), facts.skills.groups)
    }
    skill_groups = [
        SkillGroup(name=skill_group_facts[gid].name, items=skill_group_facts[gid].items)
        for gid in state.skill_group_ids
    ]

    return CVContent(
        full_name=facts.personal.full_name,
        target_title=selection.target_title,
        location=facts.personal.location,
        contact_details=[facts.personal.email, facts.personal.phone],
        contact_links=[facts.personal.linkedin, facts.personal.github],
        profile=profile,
        skill_groups=skill_groups,
        experience=experience,
        education=education,
        projects=projects,
        certifications=[
            Certification(
                name=cert.name,
                issuer=cert.issuer,
                issued=cert.issued,
                expires=cert.expires,
            )
            for cert in facts.certifications.entries
        ],
        languages=[
            Language(language=entry.language, level=entry.level)
            for entry in facts.languages.entries
        ],
        coursework=select_coursework(facts, parsed_jd),
    )


def surviving_ids(
    facts: CVFacts,
    parsed_jd: ParsedJD,
    selection: CVSelection,
    state: SelectionState,
) -> set[str]:
    """
    Every fact-base ID actually present in the CV that `state` describes
    -- what the profile-writing call is allowed to cite.
    """

    ids: set[str] = set()
    ids.update(ids_by_kind(facts, "experience"))
    ids.update(ids_by_kind(facts, "education"))
    ids.update(ids_by_kind(facts, "certification"))
    ids.update(ids_by_kind(facts, "language"))
    ids.update(state.project_ids)
    ids.update(state.skill_group_ids)

    rank_map = _rank_map(selection.bullet_ranks)

    for entry_id, cap in state.bullet_caps.items():
        ref = facts.by_id(entry_id)

        if ref is None or ref.kind not in ("experience", "education", "project"):
            continue

        fact = _fact_for_entry(facts, entry_id, ref.kind)
        bullet_items = [
            (f"{entry_id}.b{index}", bullet)
            for index, bullet in enumerate(fact.bullets, start=1)
        ]
        kept = set(_kept_bullets_for_entry(entry_id, bullet_items, rank_map, state))

        for bullet_id, text in bullet_items:
            if text in kept:
                ids.add(bullet_id)

    if select_coursework(facts, parsed_jd):
        ids.add("coursework")

    return ids


def render_final_content_with_ids(
    facts: CVFacts,
    parsed_jd: ParsedJD,
    selection: CVSelection,
    state: SelectionState,
) -> str:
    """
    Renders only what survived selection, with IDs -- the input to the
    profile-writing call, so it can only ever cite what is actually on
    the final CV.
    """

    rank_map = _rank_map(selection.bullet_ranks)
    lines: list[str] = []

    lines.append("EXPERIENCE (as it appears on the final CV):")
    for entry_id, fact in zip(ids_by_kind(facts, "experience"), facts.work_experience.entries):
        lines.append(f"[{entry_id}] {fact.position} -- {fact.organisation}, {fact.city} ({fact.dates})")
        bullet_items = [(f"{entry_id}.b{i}", b) for i, b in enumerate(fact.bullets, start=1)]
        kept = set(_kept_bullets_for_entry(entry_id, bullet_items, rank_map, state))
        for bullet_id, text in bullet_items:
            if text in kept:
                lines.append(f"  [{bullet_id}] {text}")

    lines.append("")
    lines.append("EDUCATION (as it appears on the final CV):")
    for entry_id, fact in zip(ids_by_kind(facts, "education"), facts.education.entries):
        lines.append(f"[{entry_id}] {fact.degree} -- {fact.institution}, {fact.city} ({fact.dates})")
        bullet_items = [(f"{entry_id}.b{i}", b) for i, b in enumerate(fact.bullets, start=1)]
        kept = set(_kept_bullets_for_entry(entry_id, bullet_items, rank_map, state))
        for bullet_id, text in bullet_items:
            if text in kept:
                lines.append(f"  [{bullet_id}] {text}")

    project_facts = {
        entry_id: fact
        for entry_id, fact in zip(ids_by_kind(facts, "project"), facts.projects.entries)
    }

    if state.project_ids:
        lines.append("")
        lines.append("PROJECTS (as they appear on the final CV):")
        for project_id in state.project_ids:
            fact = project_facts[project_id]
            lines.append(f"[{project_id}] {fact.name} -- {fact.intro}")
            bullet_items = [(f"{project_id}.b{i}", b) for i, b in enumerate(fact.bullets, start=1)]
            kept = set(_kept_bullets_for_entry(project_id, bullet_items, rank_map, state))
            for bullet_id, text in bullet_items:
                if text in kept:
                    lines.append(f"  [{bullet_id}] {text}")

    skill_group_facts = {
        group_id: group
        for group_id, group in zip(ids_by_kind(facts, "skill_group"), facts.skills.groups)
    }

    if state.skill_group_ids:
        lines.append("")
        lines.append("SKILL GROUPS (as they appear on the final CV):")
        for group_id in state.skill_group_ids:
            group = skill_group_facts[group_id]
            lines.append(f"[{group_id}] {group.name}: {', '.join(group.items)}")

    if select_coursework(facts, parsed_jd):
        lines.append("")
        lines.append(f"[coursework] {'; '.join(facts.coursework.items)}")

    lines.append("")
    lines.append("CERTIFICATIONS (always present):")
    for cert in facts.certifications.entries:
        lines.append(f"- {cert.name} -- {cert.issuer}")

    lines.append("")
    lines.append("LANGUAGES (always present):")
    for language_fact in facts.languages.entries:
        lines.append(f"- {language_fact.language} ({language_fact.level})")

    return "\n".join(lines)
