from cv.facts import CVFacts
from cv.selector import _render_facts_with_ids as render_facts_with_ids  # noqa: F401  (public name)


def render_facts(facts: CVFacts) -> str:
    """
    Plain-text view of the whole fact base for the matcher and evaluator: the same
    approved evidence the letter and CV are built from, so the score
    judges what will actually be presented.
    """

    p = facts.personal
    lines = [f"Location: {p.location}"]

    if p.availability:
        lines.append(f"Availability: {p.availability}")

    if p.driving_licence:
        lines.append(f"Driving licence: {p.driving_licence}")

    lines.append("Languages: " + "; ".join(f"{l.language} ({l.level})" for l in facts.languages.entries))

    lines += ["", "WORK EXPERIENCE"]
    for w in facts.work_experience.entries:
        lines.append(f"{w.position} -- {w.organisation}, {w.city} ({w.dates})")
        lines += [f"  Department: {w.department}"] if w.department else []
        lines += [f"  Tools: {w.tools}"] if w.tools else []
        lines += [f"  Topic: {w.topic}"] if w.topic else []
        lines += [f"  - {b}" for b in w.bullets]

    lines += ["", "EDUCATION"]
    for e in facts.education.entries:
        lines.append(f"{e.degree} -- {e.institution}, {e.city} ({e.dates})")
        lines += [f"  Overall grade: {e.overall_grade}"] if e.overall_grade else []
        lines += [f"  Thesis: {e.thesis_title} (grade {e.thesis_grade})"] if e.thesis_title else []
        lines += [f"  - {b}" for b in e.bullets]

    lines += ["", "PROJECTS"]
    for pr in facts.projects.entries:
        lines.append(f"{pr.name} ({pr.dates}, {pr.status}) -- {pr.intro}")
        lines.append(f"  Tools: {pr.tools}")
        lines += [f"  - {b}" for b in pr.bullets]

    lines += ["", "CERTIFICATIONS"]
    lines += [f"{c.name} -- {c.issuer} ({c.issued})" for c in facts.certifications.entries]

    lines += ["", "SKILLS"]
    lines += [f"{g.name}: {', '.join(g.items)}" for g in facts.skills.groups]

    if facts.coursework.items:
        lines += ["", "COURSEWORK: " + "; ".join(facts.coursework.items)]

    extras = facts.extras.awards + facts.extras.volunteering
    if extras:
        lines += ["", "AWARDS / VOLUNTEERING: " + "; ".join(extras)]

    return "\n".join(lines)
