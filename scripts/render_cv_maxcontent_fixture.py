# This fixture deliberately includes EVERY fact from cv_facts.yaml —
# all tiers, all skill groups, all projects, coursework included
# unconditionally — as a worst-case layout stress test. It answers one
# question: how many pages does the maximum possible content take?
#
# It does not judge relevance to any job description. Real, JD-driven
# content selection (which facts actually belong on a given CV) is
# Phase B and does not happen here. No LLM call, no network call.

import sys
from pathlib import Path

from cv.checks import convert_to_pdf, extract_ordered_lines, run_checks
from cv.facts import CVFacts, load_facts
from cv.render import DEFAULT_SECTION_ORDER, SECTION_HEADINGS, render_cv
from cv.schema import (
    Certification,
    CVContent,
    EducationEntry,
    ExperienceEntry,
    Language,
    ProjectEntry,
    SkillGroup,
)


TARGET_TITLE_PLACEHOLDER = "AI / Software Engineer"

PROFILE_PLACEHOLDER = (
    "Placeholder profile for layout testing only. Real profile text is "
    "written per job description in Phase B, not generated here."
)

OUT_PATH = Path("output/_layout_test.docx")

# A single bullet reading exactly this is a status marker, not real content —
# render it on the dates line instead of as a bullet.
IN_PROGRESS_MARKER = "in progress."


def _build_experience(facts: CVFacts, notes: list[str]) -> list[ExperienceEntry]:
    entries = []

    for fact in facts.work_experience.entries:
        bullets = fact.bullets

        if len(bullets) > 5:
            kept = bullets[:5]
            notes.append(f"{fact.position}: {len(kept)} of {len(bullets)} bullets used (schema max)")
            bullets = kept

        entries.append(
            ExperienceEntry(
                position=fact.position,
                organisation=fact.organisation,
                city=fact.city,
                dates=fact.dates,
                tools=fact.tools,
                topic=fact.topic,
                bullets=bullets,
            )
        )

    return entries


def _build_education(facts: CVFacts, notes: list[str]) -> list[EducationEntry]:
    entries = []

    for fact in facts.education.entries:
        bullets = fact.bullets
        dates = fact.dates

        if len(bullets) == 1 and bullets[0].strip().lower() == IN_PROGRESS_MARKER:
            dates = f"{dates}, ongoing"
            bullets = []
        elif len(bullets) > 4:
            kept = bullets[:4]
            notes.append(f"{fact.degree}: {len(kept)} of {len(bullets)} bullets used (schema max)")
            bullets = kept

        entries.append(
            EducationEntry(
                position=fact.degree,
                organisation=fact.institution,
                city=fact.city,
                dates=dates,
                bullets=bullets,
            )
        )

    return entries


def _build_projects(facts: CVFacts, notes: list[str]) -> list[ProjectEntry]:
    entries = []

    for fact in facts.projects.entries:
        result_bullets = fact.bullets

        if len(result_bullets) > 4:
            kept = result_bullets[:4]
            notes.append(f"{fact.name}: {len(kept)} of {len(result_bullets)} result bullets used (schema max)")
            result_bullets = kept

        bullets = [fact.intro, *result_bullets]

        entries.append(
            ProjectEntry(
                position=fact.name,
                organisation="Personal project",
                city="",
                dates=fact.dates,
                tools=fact.tools,
                bullets=bullets,
            )
        )

    return entries


def build_maxcontent_cv(facts: CVFacts) -> tuple[CVContent, list[str]]:
    """
    Build a CVContent that includes every fact unconditionally.
    Returns the content plus any mechanical-truncation notes.
    """

    notes: list[str] = []

    content = CVContent(
        full_name=facts.personal.full_name,
        target_title=TARGET_TITLE_PLACEHOLDER,
        location=facts.personal.location,
        contact_details=[facts.personal.email, facts.personal.phone],
        contact_links=[facts.personal.linkedin, facts.personal.github],
        profile=PROFILE_PLACEHOLDER,
        skill_groups=[
            SkillGroup(name=group.name, items=group.items)
            for group in facts.skills.groups
        ],
        experience=_build_experience(facts, notes),
        education=_build_education(facts, notes),
        projects=_build_projects(facts, notes),
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
        coursework=list(facts.coursework.items),
    )

    return content, notes


def section_line_counts(pdf_path: Path) -> dict[str, int]:
    """
    Rendered body-line count per section (heading line not included).
    """

    lines = extract_ordered_lines(pdf_path)
    heading_texts = set(SECTION_HEADINGS.values())
    counts = {name: 0 for name in SECTION_HEADINGS}
    heading_to_section = {v: k for k, v in SECTION_HEADINGS.items()}
    current = None

    for line in lines:
        if line in heading_texts:
            current = heading_to_section[line]
            continue

        if current is not None:
            counts[current] += 1

    return counts


def main() -> None:
    facts = load_facts("input/cv_facts.yaml")

    content, truncation_notes = build_maxcontent_cv(facts)

    out_path = render_cv(content, OUT_PATH, section_order=DEFAULT_SECTION_ORDER)
    print(f"Rendered: {out_path}")

    if truncation_notes:
        print()
        print("Mechanical truncations applied (schema max exceeded):")
        for note in truncation_notes:
            print(f"- {note}")

    pdf_path, converter_used = convert_to_pdf(out_path)

    print()
    if pdf_path is None:
        print(f"PDF conversion unavailable ({converter_used}); page count and line breakdown skipped.")
    else:
        import pymupdf as fitz

        pdf = fitz.open(str(pdf_path))
        page_count = pdf.page_count
        pdf.close()

        print(f"Page count: {page_count} (via {converter_used})")

        print()
        print("Section budget (rendered content lines, and lines saved if the section were dropped entirely):")
        line_counts = section_line_counts(pdf_path)
        for section_name in DEFAULT_SECTION_ORDER:
            count = line_counts[section_name]
            # Dropping a section removes its heading line too, but only if
            # the section actually rendered one (render_cv skips empty
            # sections' headings entirely).
            saved = count + 1 if count > 0 else 0
            print(f"- {SECTION_HEADINGS[section_name]}: {count} lines (drop saves {saved})")

    print()
    print("Check results:")

    results = run_checks(out_path, content, facts, pdf_path=pdf_path)

    for check_id, passed, detail in results:
        status = "SKIP" if passed is None else ("PASS" if passed else "FAIL")
        print(f"[{status}] {check_id}: {detail}")

    failed = [r for r in results if r[1] is False]
    skipped = [r for r in results if r[1] is None]

    print()
    print(f"{len(results) - len(failed) - len(skipped)}/{len(results)} passed, "
          f"{len(failed)} failed, {len(skipped)} skipped.")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
