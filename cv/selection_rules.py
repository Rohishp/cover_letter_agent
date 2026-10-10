import re

from pydantic import BaseModel

from cv.facts import CVFacts, SkillGroupFact, ids_by_kind
from cv.render import FIRST_SECTION, LAST_SECTIONS, validate_section_order
from cv.schema import (
    PROFILE_MAX_CHARS,
    Certification,
    CVContent,
    EducationEntry,
    ExperienceEntry,
    Language,
    ProjectEntry,
    SkillGroup,
)
from cv.selector import CVSelection, ItemRank
from guidelines import HEADLINE_TABLE_STAKES_TERMS
from models.jd_schema import ParsedJD


MAX_SKILL_GROUPS = 4
MIN_PROJECTS = 2
MAX_PROJECTS = 3

# Forced runs (state.forced == True: a human explicitly overrode a
# would-have-rejected match) search deeper before page-fit trims back
# down -- more honest proof-points matter more when no single one is
# decisive. MIN_PROJECTS is unchanged.
MAX_PROJECTS_FORCED = 4
MAX_SKILL_GROUPS_FORCED = 5

# A quality floor, separate from the count cap above (Phase F addendum 2:
# real case -- forced mode's 4th project slot got filled by a one-bullet
# project with no distinguishing content, just because the cap had room).
# Raising MAX_PROJECTS_FORCED should widen how many projects COULD
# qualify, not guarantee that many get shown. Cheap and Python-only, no
# new LLM judgment call: a project needs either real bullet count or at
# least one bullet carrying a number (the same digit signal
# metric_density already scans for) to have earned its slot.
PROJECT_QUALITY_MIN_BULLETS = 2

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

# A skill group naming the employer's own product, or a tool the JD names
# explicitly, is unusually strong and honest signal that plain LLM
# relevance ranking underweights (Phase E.1 item 5: real case -- an
# "Automation" group containing "n8n" was cut by the cap for an n8n JD).
#
# Phase F direct-evidence re-verification found this did not actually
# promote either real-world group: (a) parsed_jd's structured fields
# (core_must_have_skills etc.) are LLM-merged into generalised capability
# labels ("AI-native by default") and never retain literal tool names like
# "n8n"/"Claude Code" -- checking only those fields can never match, no
# matter the bonus size, so raw (unparsed) JD text is now checked too;
# (b) even where the company-name match DID fire ("n8n" venue "n8n"), a
# flat +2.0 nudge on a group the LLM ranked dead last (7th of 7) only
# produced a tie with the 5th-place group, which then lost on stable-sort
# list order. A same-size nudge can only ever move a group *up* by that
# fixed amount, never guarantee a top-N slot regardless of how bad the
# LLM's raw rank was. Replaced with a hard partition instead of an
# additive nudge: every matching group sorts strictly ahead of every
# non-matching group (ties within each partition still follow the LLM's
# own relative ranking).
BUILDER_FIRST_JD_KEYWORDS = (
    "side project",
    "personal project",
    "portfolio",
    "tinkering",
    "visible building",
    "open-source",
    "open source",
    "public demo",
    "solo",
)

# Phase F item 2: the deterministic override target when Projects should
# be promoted ahead of Experience. Skills/Education keep their usual
# fixed roles; this only ever reorders the Projects-vs-Experience pair.
DETERMINISTIC_BUILDER_FIRST_ORDER = ["skills", "projects", "experience", "education"]

# Used only during page-fit and the density floor, before the real
# profile is written (item 4: profile is written last, from the final
# selected content). Deliberately sized at the schema max so a fit
# validated against this placeholder can never be broken by the real
# (equal-or-shorter) profile that replaces it.
_PROFILE_PLACEHOLDER_BASE = (
    "Placeholder profile text reserving maximum layout space during selection "
    "and page-fit. The real, evidence-based profile is written after final "
    "content is chosen and replaces this text before the CV is delivered. "
)
# Repeated, then cut to exactly PROFILE_MAX_CHARS -- the base sentence alone
# is shorter than the limit, so a plain [:PROFILE_MAX_CHARS] slice would
# silently under-reserve space instead of covering the true worst case.
PROFILE_PLACEHOLDER = (_PROFILE_PLACEHOLDER_BASE * 3)[:PROFILE_MAX_CHARS]


def _has_digit(text: str) -> bool:
    return any(char.isdigit() for char in text)


def _term_mentioned(haystack: str, needle: str) -> bool:
    """
    Whole-word (or whole-phrase), case-insensitive containment -- avoids
    short items like "AI" or "Git" false-matching inside unrelated words.
    """

    needle = needle.strip()

    if not needle or not haystack:
        return False

    return re.search(rf"\b{re.escape(needle)}\b", haystack, re.IGNORECASE) is not None


# Phase G item 1: generalises the E.1/Phase F company-name-and-one-tool
# signal into a real requirement-match boost, using the JD's own
# structured requirement fields the matcher already produces -- no second,
# separate keyword list to maintain per application. core_must_have_skills
# and supporting_skills are the two fields Phase G explicitly names;
# technical_skills is included too because that's concretely where the JD
# parser puts literal tool/tech terms it generalises OUT of the other two
# (e.g. "RAG architectures", "SQL", "vector databases" showed up only
# there for a real JD -- core_must_have_skills held only broad capability
# sentences with no matching tokens at all). raw_jd_text stays as the
# last-resort fallback for terms the parser generalised out of every
# structured field (Phase F's "n8n"/"Claude Code" case).
_REQUIREMENT_MATCH_STOPWORDS = {
    "and", "for", "the", "are", "was", "with", "that", "this", "your",
    "have", "will", "from", "into", "well", "using", "used", "based",
}


def _significant_words(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9+.#-]{2,}", text)
    return [w for w in words if w.lower() not in _REQUIREMENT_MATCH_STOPWORDS]


def _jd_requirement_blob(parsed_jd: ParsedJD, raw_jd_text: str = "") -> str:
    structured = " ".join(
        [
            *parsed_jd.core_must_have_skills,
            *parsed_jd.supporting_skills,
            *parsed_jd.technical_skills,
        ]
    )
    return f"{structured} {raw_jd_text}"


def _terms_match_text(candidate_terms: list[str], text: str) -> bool:
    """
    True if any candidate_term appears as a whole phrase in text. Lowest
    -level primitive shared by every JD-requirement-matching caller in
    this module (Phase H item 1: one helper, not duplicated logic).
    """

    return any(_term_mentioned(text, term) for term in candidate_terms if term)


def _prose_matches_requirement(prose_text: str, requirement: str) -> bool:
    """
    True if a significant word from requirement appears in prose_text --
    catches paraphrased matches ("vector databases" JD phrasing vs. a
    project's own "vector store" wording) that a discrete tool-tag
    comparison wouldn't.
    """

    if not prose_text:
        return False

    return any(_term_mentioned(prose_text, word) for word in _significant_words(requirement))


def _matches_jd_requirement_signal(
    candidate_terms: list[str],
    prose_text: str,
    parsed_jd: ParsedJD,
    raw_jd_text: str = "",
) -> bool:
    """
    True when either:
    (a) one of candidate_terms (a skill group's items, or a project's
        comma-split tools) appears as a whole phrase in the JD's own
        requirement blob (core must-haves, supporting skills,
        technical_skills, raw JD text) or its company name; or
    (b) a significant word from a technical_skills entry appears in
        prose_text (a project's intro/bullets).

    Reasonably tolerant on purpose: this feeds a rank boost/partition,
    not a hard gate, so a modest false-positive rate is an acceptable
    trade for not silently missing a real requirement match. Simple
    substring/word overlap throughout, no NLP.
    """

    company_name = parsed_jd.company_name or ""
    requirement_blob = _jd_requirement_blob(parsed_jd, raw_jd_text)

    if _terms_match_text(candidate_terms, company_name) or _terms_match_text(candidate_terms, requirement_blob):
        return True

    if prose_text:
        for skill_phrase in parsed_jd.technical_skills:
            if _prose_matches_requirement(prose_text, skill_phrase):
                return True

    return False


def _skill_group_matches_jd_signal(
    group: SkillGroupFact, parsed_jd: ParsedJD, raw_jd_text: str = ""
) -> bool:
    return _matches_jd_requirement_signal(group.items, "", parsed_jd, raw_jd_text)


def _project_matches_jd_signal(fact, parsed_jd: ParsedJD, raw_jd_text: str = "") -> bool:
    tools = [t.strip() for t in fact.tools.split(",") if t.strip()]
    prose = f"{fact.intro} {' '.join(fact.bullets)}"
    return _matches_jd_requirement_signal(tools, prose, parsed_jd, raw_jd_text)


def requirement_evidence_fact_ids(
    facts: CVFacts, parsed_jd: ParsedJD, raw_jd_text: str = ""
) -> dict[str, list[str]]:
    """
    For each of the JD's own requirement terms (core_must_have_skills +
    supporting_skills + technical_skills -- the field scope Phase G
    settled on), which fact-base IDs (projects, skill groups, experience
    entries) provide real evidence for it. Reuses the exact matching
    primitives the project/skill-group rank boost uses (Phase H item 1:
    one shared helper for both the letter's coverage retry and the
    profile's coverage input -- not duplicated logic).

    A requirement absent from this dict has no locatable fact-base
    evidence at all -- callers must never nudge toward it with a bare
    term in that case (Phase H's root-cause finding: a coverage hint
    naming a keyword with no real evidence to point to is what caused
    the writer to fabricate a job role in the first place).
    """

    requirement_terms = [
        *parsed_jd.core_must_have_skills,
        *parsed_jd.supporting_skills,
        *parsed_jd.technical_skills,
    ]

    project_ids = ids_by_kind(facts, "project")
    skill_group_ids = ids_by_kind(facts, "skill_group")
    experience_ids = ids_by_kind(facts, "experience")

    evidence_map: dict[str, list[str]] = {}

    for requirement in requirement_terms:
        matched_ids: list[str] = []

        for project_id, fact in zip(project_ids, facts.projects.entries):
            tools = [t.strip() for t in fact.tools.split(",") if t.strip()]
            prose = f"{fact.intro} {' '.join(fact.bullets)}"

            if _terms_match_text(tools, requirement) or _prose_matches_requirement(prose, requirement):
                matched_ids.append(project_id)

        for group_id, group in zip(skill_group_ids, facts.skills.groups):
            if _terms_match_text(group.items, requirement):
                matched_ids.append(group_id)

        for entry_id, fact in zip(experience_ids, facts.work_experience.entries):
            if fact.tools:
                tools = [t.strip() for t in fact.tools.split(",") if t.strip()]

                if _terms_match_text(tools, requirement):
                    matched_ids.append(entry_id)

        if matched_ids:
            evidence_map[requirement] = matched_ids

    return evidence_map


HEADLINE_MAX_ITEMS = 6

# Heuristic pre-filter only, same empirical basis as checks.py's
# BULLET_CHARS_PER_LINE (10pt Calibri, ~6.87in usable column -- the
# headline renders at the same BODY_SIZE). The real backstop is
# cv/checks.py's headline_fits check against the actual PDF render;
# this cap just keeps obviously-too-long candidates from ever reaching it.
HEADLINE_MAX_CHARS = 95


def select_positioning_phrase(
    facts: CVFacts, parsed_jd: ParsedJD, raw_jd_text: str = ""
) -> str | None:
    """
    Pick one specialisation phrase (Phase I item 1's headline strip) from
    the closed, human-authored facts.personal.positioning list, by JD
    relevance. Never invents one: if the field is empty, or no candidate
    shares any significant word with the JD, returns None and the
    headline renders without a specialisation segment.
    """

    candidates = facts.personal.positioning

    if not candidates:
        return None

    requirement_blob = _jd_requirement_blob(parsed_jd, raw_jd_text)

    best_phrase = None
    best_score = 0

    for phrase in candidates:
        score = sum(
            1 for word in _significant_words(phrase) if _term_mentioned(requirement_blob, word)
        )
        if score > best_score:
            best_score = score
            best_phrase = phrase

    return best_phrase


def _is_headline_table_stakes(item: str) -> bool:
    return item.strip().lower() in {t.lower() for t in HEADLINE_TABLE_STAKES_TERMS}


def _drop_less_specific_duplicates(
    ranked_terms: list[tuple[str, str]]
) -> list[tuple[str, str]]:
    """
    Phase I addendum: when the fact base names both a general and a more
    specific form of the same term (e.g. "OpenAI" from a project's tools
    line vs. "OpenAI Agents SDK" from a skill group), prefer the specific
    one on the headline -- simple containment rule, both already
    fact-base-grounded candidates: if one candidate string is a substring
    of another, drop the shorter. Order among survivors is unchanged.
    """

    texts = [item for item, _fact_id in ranked_terms]

    def _is_substring_of_another(item: str) -> bool:
        item_l = item.strip().lower()
        return any(
            item_l != other.strip().lower() and item_l in other.strip().lower()
            for other in texts
        )

    return [
        (item, fact_id) for item, fact_id in ranked_terms if not _is_substring_of_another(item)
    ]


def headline_terms(
    facts: CVFacts, selection: CVSelection, parsed_jd: ParsedJD, raw_jd_text: str = ""
) -> list[tuple[str, str]]:
    """
    Real skill/tool item strings the candidate has AND the JD names, most
    differentiating first, for the headline strip's term source (Phase I
    item 1 + the ranking addendum). Every returned item is one
    (item_text, fact_id) pair, so every word on the strip is traceable to
    a real fact-base ID -- a term the candidate doesn't have is
    structurally impossible to produce here.

    Ranking is two axes, deliberately not one:
    - JD prominence (core_must_have_skills, then supporting_skills, then
      technical_skills, then raw JD text as last resort -- the exact
      field scope requirement_evidence_fact_ids() uses) answers
      "how strongly does the JD ask for this," which is right for
      requirement COVERAGE but wrong for a headline on its own: a term
      nearly every applicant also has (Python, SQL, CI/CD...) scores
      maximally on prominence and near-zero on differentiating this
      candidate. HEADLINE_TABLE_STAKES_TERMS (guidelines.py) demotes
      those terms to the bottom of the headline ordering ONLY -- they
      are never removed from candidacy (a sparse match set can still
      fill the strip), and this list affects nothing outside this
      function: Skills-section rendering, tools: lines, and all
      requirement-coverage logic are untouched.
    - the item's own skill-group rank, as a tiebreak within each
      prominence tier.

    Reuses _term_mentioned/_terms_match_text, the same primitives
    requirement_evidence_fact_ids() is built from, rather than a third
    matching path -- just inverted for display: a candidate item string
    traceable to one fact-base ID, instead of a JD requirement mapped to
    every fact-base ID that supports it.
    """

    tiers = [
        parsed_jd.core_must_have_skills,
        parsed_jd.supporting_skills,
        parsed_jd.technical_skills,
    ]

    def _prominence(item: str) -> int | None:
        for tier_index, terms in enumerate(tiers):
            if any(_term_mentioned(term, item) for term in terms):
                return tier_index
        if raw_jd_text and _term_mentioned(raw_jd_text, item):
            return len(tiers)
        return None

    skill_group_rank_map = _rank_map(selection.skill_group_ranks)

    candidates: list[tuple[int, float, str, str]] = []

    for group_id, group in zip(ids_by_kind(facts, "skill_group"), facts.skills.groups):
        ranked = skill_group_rank_map.get(group_id)
        group_rank = ranked.rank if ranked else WORST_RANK

        for item in group.items:
            prominence = _prominence(item)
            if prominence is not None:
                candidates.append((prominence, group_rank, item, group_id))

    # Experience/project tools are a supplementary source with no
    # skill-group rank of their own -- they lose ties against
    # skill-group-sourced items (WORST_RANK), since Phase I's ordering
    # rule only names skill-group rank as the tiebreak.
    for entry_id, fact in zip(ids_by_kind(facts, "experience"), facts.work_experience.entries):
        if not fact.tools:
            continue
        for tool in [t.strip() for t in fact.tools.split(",") if t.strip()]:
            prominence = _prominence(tool)
            if prominence is not None:
                candidates.append((prominence, WORST_RANK, tool, entry_id))

    for proj_id, fact in zip(ids_by_kind(facts, "project"), facts.projects.entries):
        for tool in [t.strip() for t in fact.tools.split(",") if t.strip()]:
            prominence = _prominence(tool)
            if prominence is not None:
                candidates.append((prominence, WORST_RANK, tool, proj_id))

    # Partition, not a nudge (same pattern _top_skill_groups uses above):
    # every non-table-stakes candidate sorts strictly ahead of every
    # table-stakes one, ties within each partition broken by prominence
    # then skill-group rank as before.
    candidates.sort(key=lambda c: (_is_headline_table_stakes(c[2]), c[0], c[1]))

    seen: set[str] = set()
    ranked_terms: list[tuple[str, str]] = []

    for _prominence, _rank, item, fact_id in candidates:
        key = item.strip().lower()

        if key in seen:
            continue

        seen.add(key)
        ranked_terms.append((item, fact_id))

    return _drop_less_specific_duplicates(ranked_terms)


def build_headline_strip(
    facts: CVFacts, selection: CVSelection, parsed_jd: ParsedJD, raw_jd_text: str = ""
) -> tuple[str | None, list[tuple[str, str]], str | None]:
    """
    Build the render-only headline strip under the candidate's name
    (Phase I item 1): "<positioning> | <term> · <term> · ...", capped to
    HEADLINE_MAX_ITEMS items and HEADLINE_MAX_CHARS, truncated by
    dropping the lowest-ranked items (never mid-token). Returns
    (rendered_strip_or_None, kept_terms_with_fact_ids, positioning).

    This is deterministic, Python-only construction from real fact-base
    data -- no LLM call, no free text. It must never be fed to the
    cover-letter writer, the profile writer, or any parser whose output
    reaches them: this exact format (title, dash-separated tools) is what
    contaminated parsed_cv and caused the original employer/role
    fabrications. See claude/cover-letter-path-root-cause.md.
    """

    terms = headline_terms(facts, selection, parsed_jd, raw_jd_text)
    positioning = select_positioning_phrase(facts, parsed_jd, raw_jd_text)

    budget = HEADLINE_MAX_CHARS - len(selection.target_title) - len(" | ")

    if positioning:
        budget -= len(positioning) + len(" | ")

    kept: list[tuple[str, str]] = []
    running_len = 0

    for item, fact_id in terms:
        if len(kept) >= HEADLINE_MAX_ITEMS:
            break

        addition = len(item) + (len(" · ") if kept else 0)

        if running_len + addition > budget:
            break

        kept.append((item, fact_id))
        running_len += addition

    parts = []

    if positioning:
        parts.append(positioning)

    if kept:
        parts.append(" · ".join(item for item, _fact_id in kept))

    if not parts:
        return None, [], None

    return " | ".join(parts), kept, positioning


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


def _average_rank(ranks: list[ItemRank]) -> float | None:
    if not ranks:
        return None

    return sum(item.rank for item in ranks) / len(ranks)


def projects_outrank_experience(facts: CVFacts, selection: CVSelection) -> bool:
    """
    Average JD-relevance rank of ranked projects vs. the average rank of
    experience bullets. Experience entries themselves are never
    individually ranked -- only their bullets are -- so bullet rank is
    the closest available proxy for "how relevant is Experience overall"
    (item 2). Lower rank is stronger, so projects "outrank" only when
    their average is strictly lower.
    """

    project_average = _average_rank(selection.project_ranks)

    experience_bullet_ranks = [
        item
        for item in selection.bullet_ranks
        if (ref := facts.by_id(item.id)) is not None and ref.kind == "experience_bullet"
    ]
    experience_average = _average_rank(experience_bullet_ranks)

    if project_average is None or experience_average is None:
        return False

    return project_average < experience_average


def _jd_signals_builder_first_culture(parsed_jd: ParsedJD) -> bool:
    text = " ".join(
        [
            *parsed_jd.core_must_have_skills,
            *parsed_jd.supporting_skills,
            *parsed_jd.nice_to_have_skills,
            *parsed_jd.technical_skills,
            parsed_jd.core_mission_statement or "",
        ]
    ).lower()

    return any(keyword in text for keyword in BUILDER_FIRST_JD_KEYWORDS)


def _section_order_override(
    facts: CVFacts, selection: CVSelection, parsed_jd: ParsedJD
) -> tuple[bool, str | None]:
    """
    Item 2: a deterministic override of Projects-vs-Experience order,
    replacing reliance on the LLM's own section_order_reason (observed
    not to reliably justify, or even correctly describe, its own choice).
    Only ever promotes Projects ahead of Experience; never the reverse,
    and never touches Skills/Education.
    """

    relevance_signal = projects_outrank_experience(facts, selection)
    culture_signal = _jd_signals_builder_first_culture(parsed_jd)

    if not (relevance_signal or culture_signal):
        return False, None

    reasons = []

    if relevance_signal:
        reasons.append("projects rank higher than experience by JD relevance")

    if culture_signal:
        reasons.append("the JD signals builder-first hiring")

    reason = (
        "Deterministic override: Projects placed ahead of Experience because "
        + " and ".join(reasons)
        + "."
    )

    return True, reason


def section_order_override_reason(
    facts: CVFacts, selection: CVSelection, parsed_jd: ParsedJD
) -> str | None:
    _should_override, reason = _section_order_override(facts, selection, parsed_jd)
    return reason


def resolve_section_order(
    selection: CVSelection,
    facts: CVFacts | None = None,
    parsed_jd: ParsedJD | None = None,
) -> list[str]:
    middle_order = selection.section_order

    if facts is not None and parsed_jd is not None:
        should_override, _reason = _section_order_override(facts, selection, parsed_jd)

        if should_override:
            middle_order = list(DETERMINISTIC_BUILDER_FIRST_ORDER)

    full_order = [FIRST_SECTION, *middle_order, *LAST_SECTIONS]
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
    forced: bool = False,
    raw_jd_text: str = "",
) -> tuple[SelectionState, SelectionReport]:
    """
    Compute the starting budget: which projects and skill groups are
    included, and the bullet cap for every bullet-bearing entry. This is
    where inclusion/exclusion is decided; the page-fit loop only shrinks
    what this returns, and the density floor only swaps within it.

    forced widens the project and skill-group caps (item 7) so page-fit
    has more real material to choose from before trimming back to two
    pages; it does not change ranking or eligibility.

    raw_jd_text: the unparsed JD text, needed because parsed_jd's
    structured fields are LLM-merged capability labels that don't retain
    literal tool names (see the comment above
    DETERMINISTIC_BUILDER_FIRST_ORDER) -- skill-group JD-signal matching
    needs it. Optional; "" just means that matching source is unavailable.
    """

    project_ids, excluded_projects = _ranked_projects(
        facts, selection, parsed_jd, raw_jd_text=raw_jd_text, forced=forced
    )
    skill_group_ids, excluded_skill_groups = _top_skill_groups(
        facts, selection, parsed_jd, raw_jd_text=raw_jd_text, forced=forced
    )

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

    override_reason = section_order_override_reason(facts, selection, parsed_jd)
    section_order_reason = selection.section_order_reason

    if override_reason:
        section_order_reason = f"{section_order_reason} {override_reason}"

    report = SelectionReport(
        section_order=resolve_section_order(selection, facts, parsed_jd),
        section_order_reason=section_order_reason,
        excluded_projects=excluded_projects,
        excluded_skill_groups=excluded_skill_groups,
    )

    state = SelectionState(
        project_ids=project_ids,
        skill_group_ids=skill_group_ids,
        bullet_caps=bullet_caps,
    )

    return state, report


def _project_clears_quality_floor(fact) -> bool:
    """
    Cheap Python-only substance check (Phase F addendum 2): a project
    with at least PROJECT_QUALITY_MIN_BULLETS result bullets always
    clears it; below that, it only clears if at least one bullet carries
    a number -- otherwise it has nothing to distinguish it and shouldn't
    fill a slot just because the count cap has room.
    """

    if len(fact.bullets) >= PROJECT_QUALITY_MIN_BULLETS:
        return True

    return any(_has_digit(bullet) for bullet in fact.bullets)


def _project_exclusion_note(rank: float, project_id: str, fact, reason_suffix: str) -> ExclusionNote:
    reason = ("unranked, " if rank == WORST_RANK else f"rank {int(rank)}, ") + reason_suffix

    return ExclusionNote(
        kind="project",
        id=project_id,
        label=fact.name,
        reason=reason,
        rank=None if rank == WORST_RANK else rank,
    )


def _ranked_projects(
    facts: CVFacts,
    selection: CVSelection,
    parsed_jd: ParsedJD,
    raw_jd_text: str = "",
    forced: bool = False,
) -> tuple[list[str], list[ExclusionNote]]:
    """
    Rank all projects by JD relevance, boosted by a JD-requirement-match
    partition (Phase G item 1 -- same mechanism as skill groups: every
    matching project sorts strictly ahead of every non-matching one).
    Keep between MIN_PROJECTS and MAX_PROJECTS (or MAX_PROJECTS_FORCED),
    then apply a quality floor on top of the count cap -- a project
    inside the cap's window still needs real content to earn its slot
    (see PROJECT_QUALITY_MIN_BULLETS), UNLESS it matches a JD requirement
    signal: the boost applies before the floor, so a project that's thin
    by raw content but is the sole evidence for a named requirement is
    exempt rather than cut by a heuristic with no visibility into
    requirement coverage. MIN_PROJECTS is still a hard floor either way:
    if too few clear (quality OR requirement-match), the best-ranked
    remaining ones backfill up to MIN_PROJECTS rather than
    under-provisioning the CV.

    The page budget (cv/page_fit.py) is what prevents bloat on the other
    end -- this rule only ever subtracts the weakest/thinnest projects,
    never excludes one for lack of a specific uncovered requirement.
    """

    max_projects = MAX_PROJECTS_FORCED if forced else MAX_PROJECTS

    project_ids = ids_by_kind(facts, "project")
    rank_map = _rank_map(selection.project_ranks)

    scored = []

    for project_id, fact in zip(project_ids, facts.projects.entries):
        ranked = rank_map.get(project_id)
        rank = ranked.rank if ranked is not None else WORST_RANK
        matches_requirement = _project_matches_jd_signal(fact, parsed_jd, raw_jd_text)
        sort_key = (0 if matches_requirement else 1, rank)
        scored.append((sort_key, rank, project_id, fact, matches_requirement))

    ordered = sorted(scored, key=lambda item: item[0])
    keep_count = min(max_projects, len(ordered))

    within_cap = ordered[:keep_count]
    beyond_cap = ordered[keep_count:]

    quality_pass = [
        item for item in within_cap
        if item[4] or _project_clears_quality_floor(item[3])
    ]
    quality_fail = [
        item for item in within_cap
        if not (item[4] or _project_clears_quality_floor(item[3]))
    ]

    if len(quality_pass) >= MIN_PROJECTS:
        kept = quality_pass
        cut_by_quality = quality_fail
    else:
        needed = MIN_PROJECTS - len(quality_pass)
        backfill = quality_fail[:needed]
        kept = sorted(quality_pass + backfill, key=lambda item: item[0])
        cut_by_quality = quality_fail[needed:]

    excluded = [
        _project_exclusion_note(rank, project_id, fact, f"cut by {max_projects}-project cap")
        for _sort_key, rank, project_id, fact, _matches in beyond_cap
    ] + [
        _project_exclusion_note(rank, project_id, fact, "cut by quality floor")
        for _sort_key, rank, project_id, fact, _matches in cut_by_quality
    ]

    return [project_id for _sort_key, _rank, project_id, _fact, _matches in kept], excluded


def _top_skill_groups(
    facts: CVFacts,
    selection: CVSelection,
    parsed_jd: ParsedJD,
    raw_jd_text: str = "",
    forced: bool = False,
) -> tuple[list[str], list[ExclusionNote]]:
    max_skill_groups = MAX_SKILL_GROUPS_FORCED if forced else MAX_SKILL_GROUPS

    group_ids = ids_by_kind(facts, "skill_group")
    rank_map = _rank_map(selection.skill_group_ranks)

    scored = []

    for group_id, group in zip(group_ids, facts.skills.groups):
        ranked = rank_map.get(group_id)
        rank = ranked.rank if ranked else WORST_RANK
        matches_jd_signal = _skill_group_matches_jd_signal(group, parsed_jd, raw_jd_text)
        # Partition, not a nudge: every matching group sorts strictly
        # ahead of every non-matching one (see the block comment above
        # DETERMINISTIC_BUILDER_FIRST_ORDER for why an additive bonus
        # wasn't strong enough in practice).
        sort_key = (0 if matches_jd_signal else 1, rank)
        scored.append((sort_key, rank, group_id, group))

    ordered = sorted(scored, key=lambda item: item[0])
    kept = ordered[:max_skill_groups]
    dropped = ordered[max_skill_groups:]

    excluded = [
        ExclusionNote(
            kind="skill_group",
            id=group_id,
            label=group.name,
            reason=f"cut by top-{max_skill_groups} cap",
            rank=None if rank == WORST_RANK else rank,
        )
        for _sort_key, rank, group_id, group in dropped
    ]

    return [group_id for _sort_key, _rank, group_id, _group in kept], excluded


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
    headline_strip: str | None = None,
) -> CVContent:
    """
    Pure: build the CVContent that a given SelectionState (and a given
    profile string) describes. Used for page-fit iterations, the density
    floor's trial renders, and the final render alike.

    headline_strip (Phase I item 1): computed once by
    build_headline_strip() and passed straight through here as plain
    data, same pattern as profile -- this function does not compute it
    itself, so page-fit/density-floor trial renders account for its
    height without duplicating the construction logic.
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
                repository_link=fact.links.repository,
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
        headline_strip=headline_strip,
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
        languages=_tier1_languages(facts),
        coursework=select_coursework(facts, parsed_jd),
    )


def _tier1_languages(facts: CVFacts) -> list[Language]:
    """
    Languages is tier 1: never silently cut. render.py's _render_languages
    still has its own `if not content.languages: return` guard as a
    defensive fallback, but that guard must never actually fire -- if it
    would, that means this invariant already failed and something
    upstream (the fact base itself) is broken.
    """

    languages = [
        Language(language=entry.language, level=entry.level)
        for entry in facts.languages.entries
    ]

    if not languages:
        raise ValueError(
            "languages is empty -- tier-1 content must never be silently cut. "
            "Check facts.languages.entries in the fact base."
        )

    return languages


def top_ranked_project_text(facts: CVFacts, selection: CVSelection) -> str | None:
    """
    The single rank-1 project as a plain evidence block (item 6) -- so the
    cover letter can be given the same strongest evidence the CV itself
    leads with, instead of choosing independently. None if no project was
    ranked #1 (e.g. an empty fact base, or a JD the selector found no
    standout project for).
    """

    project_ids = ids_by_kind(facts, "project")
    rank_map = _rank_map(selection.project_ranks)

    for project_id, fact in zip(project_ids, facts.projects.entries):
        ranked = rank_map.get(project_id)

        if ranked is not None and ranked.rank == 1:
            return f"{fact.name}: {fact.intro} " + " ".join(fact.bullets)

    return None


def top_ranked_project_name(facts: CVFacts, selection: CVSelection) -> str | None:
    """
    Just the rank-1 project's real name (Phase F addendum 3, item 1) --
    a clean, distinctive label to check the profile's opening sentence
    against (cv/checks.py's profile_opens_with), separate from
    top_ranked_project_text's full evidence block, which isn't a useful
    string to match verbatim.
    """

    project_ids = ids_by_kind(facts, "project")
    rank_map = _rank_map(selection.project_ranks)

    for project_id, fact in zip(project_ids, facts.projects.entries):
        ranked = rank_map.get(project_id)

        if ranked is not None and ranked.rank == 1:
            return fact.name

    return None


def top_ranked_experience_bullet_text(facts: CVFacts, selection: CVSelection) -> str | None:
    """
    The lowest-ranked (strongest) bullet among experience_bullet-kind IDs
    (Phase F item 1) -- bullet_ranks is one flat list spanning experience,
    education and project bullets together, so "rank 1 overall" could
    belong to a project; this finds the best bullet specifically FROM
    Experience, the closest available proxy for "how relevant is
    Experience's own content." None if no experience bullet was ranked.
    """

    best_id: str | None = None
    best_rank: int | None = None

    for bullet_id, ranked in _rank_map(selection.bullet_ranks).items():
        ref = facts.by_id(bullet_id)

        if ref is None or ref.kind != "experience_bullet":
            continue

        if best_rank is None or ranked.rank < best_rank:
            best_rank = ranked.rank
            best_id = bullet_id

    if best_id is None:
        return None

    return facts.by_id(best_id).text


def top_ranked_evidence_block(facts: CVFacts, selection: CVSelection) -> str | None:
    """
    Combines the rank-1 project and the top-ranked experience bullet into
    one block for the profile writer (Phase F item 1) -- the same
    underlying ranking signal write_cover_letter already receives via
    top_ranked_project_text, so the CV's own profile and the cover letter
    stop telling different stories about the candidate's strongest
    evidence.
    """

    parts = []

    project_text = top_ranked_project_text(facts, selection)

    if project_text:
        parts.append(f"Top-ranked project: {project_text}")

    bullet_text = top_ranked_experience_bullet_text(facts, selection)

    if bullet_text:
        parts.append(f"Top-ranked experience evidence: {bullet_text}")

    if not parts:
        return None

    return "\n".join(parts)


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
