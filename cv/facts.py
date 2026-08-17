import re
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field


TODO_SENTINEL = "TODO"

_LEGAL_SUFFIXES = {"gmbh", "ag", "inc", "llc", "ltd", "co", "corp", "plc", "sa"}

_DEGREE_ABBREVIATIONS = {
    "m.sc.": "msc",
    "b.sc.": "bsc",
    "ph.d.": "phd",
    "m.a.": "ma",
    "b.a.": "ba",
}

_STOPWORDS = {"of", "in", "and", "the", "for"}


def _slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _strip_legal_suffix(name: str) -> str:
    words = name.split()

    while words and _slugify(words[-1]) in _LEGAL_SUFFIXES:
        words.pop()

    return " ".join(words) or name


def _slug_for_organisation(name: str) -> str:
    return _slugify(_strip_legal_suffix(name))


def _slug_for_degree(degree: str) -> str:
    words = degree.split()

    if words:
        prefix = _DEGREE_ABBREVIATIONS.get(words[0].lower())

        if prefix:
            rest = [w for w in words[1:] if w.lower() not in _STOPWORDS]
            acronym = "".join(w[0].lower() for w in rest if w[:1].isalpha())

            if acronym:
                return f"{prefix}-{acronym}"

    return _slugify(degree)


def _dedupe_id(candidate_id: str, seen: dict[str, int]) -> str:
    count = seen.get(candidate_id, 0) + 1
    seen[candidate_id] = count
    return candidate_id if count == 1 else f"{candidate_id}-{count}"


class Meta(BaseModel):
    updated: date
    owner: str


class Personal(BaseModel):
    full_name: str
    location: str
    email: str
    phone: str
    linkedin: str
    github: str
    availability: str | None = None
    driving_licence: str | None = None
    photo: str


class LanguageFact(BaseModel):
    language: str
    level: str


class Languages(BaseModel):
    tier: int
    entries: list[LanguageFact]


class EducationFact(BaseModel):
    degree: str
    institution: str
    city: str
    dates: str
    overall_grade: str | None = None
    thesis_title: str | None = None
    thesis_grade: str | None = None
    bullets: list[str]


class Education(BaseModel):
    tier: int
    entries: list[EducationFact]


class WorkExperienceFact(BaseModel):
    position: str
    organisation: str
    city: str
    dates: str
    department: str | None = None
    tools: str | None = None
    topic: str | None = None
    bullets: list[str]


class WorkExperience(BaseModel):
    tier: int
    entries: list[WorkExperienceFact]


class ProjectLinks(BaseModel):
    repository: str | None = None
    live_endpoint: str | None = None
    demo_video: str | None = None


class ProjectFact(BaseModel):
    name: str
    dates: str
    status: str
    tools: str
    intro: str
    bullets: list[str]
    links: ProjectLinks = Field(default_factory=ProjectLinks)


class Projects(BaseModel):
    tier: int
    entries: list[ProjectFact]


class CertificationFact(BaseModel):
    name: str
    issuer: str
    issued: str
    expires: str | None = None
    credential_id: str | None = None


class Certifications(BaseModel):
    tier: int
    entries: list[CertificationFact]


class SkillGroupFact(BaseModel):
    name: str
    items: list[str]


class Skills(BaseModel):
    groups: list[SkillGroupFact]


class Coursework(BaseModel):
    tier: int
    include_when: str
    exclude_when: str
    render_as: str
    items: list[str]


class Extras(BaseModel):
    awards: list[str]
    volunteering: list[str]


class FactRef(BaseModel):
    """
    A resolved, stable-ID reference to one referenceable item in the fact
    base: an entry, a bullet within an entry, a skill group, coursework as
    a whole, a certification, or a language.
    """

    id: str
    kind: Literal[
        "experience",
        "experience_bullet",
        "education",
        "education_bullet",
        "project",
        "project_bullet",
        "skill_group",
        "coursework",
        "certification",
        "language",
    ]
    text: str
    parent_id: str | None = None


class CVFacts(BaseModel):
    meta: Meta
    personal: Personal
    languages: Languages
    education: Education
    work_experience: WorkExperience
    projects: Projects
    certifications: Certifications
    skills: Skills
    coursework: Coursework
    extras: Extras

    def by_id(self, item_id: str) -> FactRef | None:
        return build_id_index(self).get(item_id)

    def all_ids(self) -> list[str]:
        return list(build_id_index(self).keys())


def build_id_index(facts: CVFacts) -> dict[str, FactRef]:
    """
    Build every stable ID in the fact base.

    IDs are deterministic for unchanged data: derived from each item's
    position and a slug of its own text, not from any random or
    time-based value.
    """

    index: dict[str, FactRef] = {}
    seen: dict[str, int] = {}

    for fact in facts.work_experience.entries:
        entry_id = _dedupe_id(f"exp.{_slug_for_organisation(fact.organisation)}", seen)
        index[entry_id] = FactRef(id=entry_id, kind="experience", text=fact.position)

        for index_number, bullet in enumerate(fact.bullets, start=1):
            bullet_id = f"{entry_id}.b{index_number}"
            index[bullet_id] = FactRef(
                id=bullet_id, kind="experience_bullet", text=bullet, parent_id=entry_id
            )

    for fact in facts.education.entries:
        entry_id = _dedupe_id(f"edu.{_slug_for_degree(fact.degree)}", seen)
        index[entry_id] = FactRef(id=entry_id, kind="education", text=fact.degree)

        for index_number, bullet in enumerate(fact.bullets, start=1):
            bullet_id = f"{entry_id}.b{index_number}"
            index[bullet_id] = FactRef(
                id=bullet_id, kind="education_bullet", text=bullet, parent_id=entry_id
            )

    for fact in facts.projects.entries:
        entry_id = _dedupe_id(f"proj.{_slugify(fact.name)}", seen)
        index[entry_id] = FactRef(id=entry_id, kind="project", text=fact.name)

        for index_number, bullet in enumerate(fact.bullets, start=1):
            bullet_id = f"{entry_id}.b{index_number}"
            index[bullet_id] = FactRef(
                id=bullet_id, kind="project_bullet", text=bullet, parent_id=entry_id
            )

    for group in facts.skills.groups:
        group_id = _dedupe_id(f"skill.{_slugify(group.name)}", seen)
        index[group_id] = FactRef(id=group_id, kind="skill_group", text=group.name)

    if facts.coursework.items:
        index["coursework"] = FactRef(
            id="coursework",
            kind="coursework",
            text="; ".join(facts.coursework.items),
        )

    for cert in facts.certifications.entries:
        cert_id = _dedupe_id(f"cert.{_slugify(cert.name)}", seen)
        index[cert_id] = FactRef(id=cert_id, kind="certification", text=cert.name)

    for language_fact in facts.languages.entries:
        lang_id = _dedupe_id(f"lang.{_slugify(language_fact.language)}", seen)
        index[lang_id] = FactRef(
            id=lang_id,
            kind="language",
            text=f"{language_fact.language} ({language_fact.level})",
        )

    return index


def ids_by_kind(facts: CVFacts, kind: str) -> list[str]:
    """
    IDs of the given kind, in the same order as the underlying fact list
    (e.g. "experience" IDs in the same order as facts.work_experience.entries).
    """

    return [ref.id for ref in build_id_index(facts).values() if ref.kind == kind]


def _find_todo_paths(value: Any, path: str = "") -> list[str]:
    if isinstance(value, str):
        return [path or "<root>"] if value == TODO_SENTINEL else []

    if isinstance(value, dict):
        paths = []
        for key, sub_value in value.items():
            sub_path = f"{path}.{key}" if path else str(key)
            paths.extend(_find_todo_paths(sub_value, sub_path))
        return paths

    if isinstance(value, list):
        paths = []
        for index, item in enumerate(value):
            paths.extend(_find_todo_paths(item, f"{path}[{index}]"))
        return paths

    return []


def load_facts(path: Path | str) -> CVFacts:
    """
    Load and validate cv_facts.yaml.

    Raises ValueError listing every field path still holding the literal
    string TODO — a TODO reaching the renderer would print as body text
    on a real CV.
    """

    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))

    todo_paths = _find_todo_paths(raw)

    if todo_paths:
        raise ValueError(
            "cv_facts.yaml has unresolved TODO values at: "
            + ", ".join(todo_paths)
        )

    return CVFacts.model_validate(raw)
