# Phase I item 1: the JD-tailored headline strip under the candidate's
# name. Deterministic, Python-only construction -- these tests cover the
# truncation behaviour and the optional positioning phrase, the two
# behaviours the task explicitly requires tests for.

from datetime import date

from cv.facts import (
    CVFacts,
    Certifications,
    Coursework,
    Education,
    Extras,
    LanguageFact,
    Languages,
    Meta,
    Personal,
    Projects,
    SkillGroupFact,
    Skills,
    WorkExperience,
    WorkExperienceFact,
)
from cv.selection_rules import (
    HEADLINE_MAX_ITEMS,
    build_headline_strip,
    headline_terms,
    select_positioning_phrase,
)
from cv.selector import CVSelection, ItemRank
from models.jd_schema import ParsedJD


def _facts(positioning=None, skill_groups=None, work_experience=None) -> CVFacts:
    return CVFacts(
        meta=Meta(updated=date(2026, 1, 1), owner="Test Person"),
        personal=Personal(
            full_name="Test Person", location="Testville", email="test@example.com",
            phone="+1 555 0000", linkedin="https://www.linkedin.com/in/testperson",
            github="https://github.com/testperson", photo="exclude",
            positioning=positioning or [],
        ),
        languages=Languages(tier=1, entries=[LanguageFact(language="English", level="C1")]),
        education=Education(tier=1, entries=[]),
        work_experience=WorkExperience(tier=1, entries=work_experience or []),
        projects=Projects(tier=2, entries=[]),
        certifications=Certifications(tier=1, entries=[]),
        skills=Skills(groups=skill_groups or []),
        coursework=Coursework(tier=3, include_when="", exclude_when="", render_as="bullet_list", items=[]),
        extras=Extras(awards=[], volunteering=[]),
    )


def _selection(skill_group_ranks=None) -> CVSelection:
    return CVSelection(
        section_order_reason="test",
        section_order=["skills", "experience", "projects", "education"],
        bullet_ranks=[],
        project_ranks=[],
        skill_group_ranks=skill_group_ranks or [],
        target_title="AI Engineer",
    )


def test_many_matching_terms_are_truncated_to_one_line_dropping_lowest_ranked():
    # 8 real skill items across 2 groups, all JD-matching -- more than
    # HEADLINE_MAX_ITEMS (6). None are on HEADLINE_TABLE_STAKES_TERMS, so
    # this isolates truncation behaviour from the table-stakes demotion
    # covered separately below. Group A outranks group B, so truncation
    # must drop group B's LAST two items, never truncate an item
    # mid-token.
    facts = _facts(
        skill_groups=[
            SkillGroupFact(name="Languages", items=["Java", "Go", "Rust", "Kotlin"]),
            SkillGroupFact(name="Cloud", items=["AWS", "Terraform", "Kubernetes", "Redis"]),
        ]
    )
    selection = _selection(
        skill_group_ranks=[
            ItemRank(id="skill.languages", rank=1),
            ItemRank(id="skill.cloud", rank=2),
        ]
    )
    parsed_jd = ParsedJD(
        technical_skills=["Java", "Go", "Rust", "Kotlin", "AWS", "Terraform", "Kubernetes", "Redis"]
    )

    terms = headline_terms(facts, selection, parsed_jd)
    assert [item for item, _fact_id in terms] == [
        "Java", "Go", "Rust", "Kotlin", "AWS", "Terraform", "Kubernetes", "Redis",
    ]

    strip, kept, _positioning = build_headline_strip(facts, selection, parsed_jd)

    assert len(kept) <= HEADLINE_MAX_ITEMS
    kept_items = [item for item, _fact_id in kept]
    # Group A (better-ranked) survives in full; group B is truncated from
    # the bottom (its lowest-ranked/last items), not mid-token.
    assert kept_items == ["Java", "Go", "Rust", "Kotlin", "AWS", "Terraform"]
    assert "Kubernetes" not in kept_items
    assert "Redis" not in kept_items

    # Every kept item is traceable to a real fact-base ID.
    fact_ids = {fact_id for _item, fact_id in kept}
    assert fact_ids <= {"skill.languages", "skill.cloud"}

    assert strip is not None
    assert strip.count("·") == len(kept_items) - 1
    assert "Kubernetes" not in strip
    assert "Redis" not in strip


def test_no_positioning_field_renders_without_specialisation_phrase():
    facts = _facts(
        positioning=None,  # defaults to [] -- no candidates authored
        skill_groups=[SkillGroupFact(name="Programming", items=["Python"])],
    )
    selection = _selection(skill_group_ranks=[ItemRank(id="skill.programming", rank=1)])
    parsed_jd = ParsedJD(technical_skills=["Python"])

    strip, kept, positioning = build_headline_strip(facts, selection, parsed_jd)

    assert positioning is None
    assert strip == "Python"
    assert kept == [("Python", "skill.programming")]
    # Only the render-time join with target_title introduces " | " -- the
    # strip itself, with no positioning phrase, carries none.
    assert "|" not in strip


def test_positioning_phrase_selected_by_jd_relevance():
    facts = _facts(
        positioning=["Agentic AI Systems", "Data Platform Engineering"],
        skill_groups=[SkillGroupFact(name="Programming", items=["Python"])],
    )
    selection = _selection(skill_group_ranks=[ItemRank(id="skill.programming", rank=1)])
    parsed_jd = ParsedJD(technical_skills=["Python", "Agentic AI systems"])

    positioning = select_positioning_phrase(facts, parsed_jd)
    assert positioning == "Agentic AI Systems"

    strip, _kept, chosen = build_headline_strip(facts, selection, parsed_jd)
    assert chosen == "Agentic AI Systems"
    assert strip.startswith("Agentic AI Systems | ")


def test_positioning_never_invented_when_no_candidate_matches_jd():
    facts = _facts(
        positioning=["Data Platform Engineering"],
        skill_groups=[SkillGroupFact(name="Programming", items=["Python"])],
    )
    selection = _selection(skill_group_ranks=[ItemRank(id="skill.programming", rank=1)])
    parsed_jd = ParsedJD(technical_skills=["Python"])  # no overlap with the positioning phrase

    assert select_positioning_phrase(facts, parsed_jd) is None


def test_distinctive_terms_lead_table_stakes_fill_remaining_slots():
    # Table-stakes (Python, SQL, CI/CD) and distinctive (RAG, agent
    # orchestration signal, vector databases) terms all match the JD --
    # distinctive terms must occupy the leading slots regardless of
    # matching tier; table-stakes ones may only appear after them.
    facts = _facts(
        skill_groups=[
            SkillGroupFact(
                name="Agentic AI and GenAI",
                items=["RAG", "vector databases", "agent orchestration"],
            ),
            SkillGroupFact(name="Engineering", items=["Python", "SQL", "CI/CD"]),
        ]
    )
    selection = _selection(
        skill_group_ranks=[
            ItemRank(id="skill.agentic-ai-and-genai", rank=1),
            ItemRank(id="skill.engineering", rank=2),
        ]
    )
    parsed_jd = ParsedJD(
        core_must_have_skills=["Python", "SQL"],
        technical_skills=["RAG", "vector databases", "agent orchestration", "CI/CD"],
    )

    terms = headline_terms(facts, selection, parsed_jd)
    items = [item for item, _fact_id in terms]

    distinctive = {"RAG", "vector databases", "agent orchestration"}
    table_stakes = {"Python", "SQL", "CI/CD"}

    last_distinctive_index = max(items.index(term) for term in distinctive)
    first_table_stakes_index = min(items.index(term) for term in table_stakes)

    assert last_distinctive_index < first_table_stakes_index


def test_table_stakes_only_match_still_fills_a_full_strip():
    # Demotion, not exclusion: when nothing distinctive matches, the
    # table-stakes terms must still render rather than leaving the strip
    # near-empty.
    facts = _facts(
        skill_groups=[SkillGroupFact(name="Engineering", items=["Python", "SQL", "CI/CD"])]
    )
    selection = _selection(skill_group_ranks=[ItemRank(id="skill.engineering", rank=1)])
    parsed_jd = ParsedJD(technical_skills=["Python", "SQL", "CI/CD"])

    terms = headline_terms(facts, selection, parsed_jd)
    items = [item for item, _fact_id in terms]

    assert items == ["Python", "SQL", "CI/CD"]

    strip, kept, _positioning = build_headline_strip(facts, selection, parsed_jd)
    assert strip is not None
    assert len(kept) == 3


def test_specific_form_preferred_over_general_form():
    facts = _facts(
        skill_groups=[SkillGroupFact(name="Agentic AI and GenAI", items=["OpenAI Agents SDK"])],
        work_experience=[
            WorkExperienceFact(
                position="Engineer", organisation="Acme GmbH", city="Berlin", dates="2025",
                tools="OpenAI, Python", bullets=["Built an agent."],
            )
        ],
    )
    selection = _selection(skill_group_ranks=[ItemRank(id="skill.agentic-ai-and-genai", rank=1)])
    parsed_jd = ParsedJD(technical_skills=["OpenAI", "OpenAI Agents SDK"])

    terms = headline_terms(facts, selection, parsed_jd)
    items = [item for item, _fact_id in terms]

    assert "OpenAI Agents SDK" in items
    assert "OpenAI" not in items


def test_terms_not_named_in_the_jd_never_appear_on_the_strip():
    facts = _facts(
        skill_groups=[SkillGroupFact(name="Programming", items=["Python", "COBOL"])],
        work_experience=[
            WorkExperienceFact(
                position="Intern", organisation="Acme GmbH", city="Berlin", dates="2025",
                tools="Excel", bullets=["Did work."],
            )
        ],
    )
    selection = _selection(skill_group_ranks=[ItemRank(id="skill.programming", rank=1)])
    parsed_jd = ParsedJD(technical_skills=["Python"])  # neither COBOL nor Excel named

    terms = headline_terms(facts, selection, parsed_jd)
    items = [item for item, _fact_id in terms]

    assert items == ["Python"]
    assert "COBOL" not in items
    assert "Excel" not in items
