from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


TODO_SENTINEL = "TODO"


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
