from pydantic import BaseModel, Field


# Empirically calibrated (not guessed): profiles rendered at Calibri
# 10pt across the real column width reliably wrap to 3 lines up to
# ~353 characters and start spilling to 4 by ~378. 320 was tested
# against several realistic samples -- natural prose, dense technical
# vocabulary, short casual phrasing, and the actual selector output
# that once tripped a stale line-count heuristic -- and rendered in 3
# lines every time, with real margin to spare.
PROFILE_MAX_CHARS = 320


class BaseEntry(BaseModel):
    position: str
    organisation: str
    city: str
    dates: str
    tools: str | None = None
    topic: str | None = None          # rendered as its own bold line


class ExperienceEntry(BaseEntry):
    bullets: list[str] = Field(min_length=3, max_length=5)


class EducationEntry(BaseEntry):
    # A degree in progress legitimately has one line or none — forcing a
    # minimum would mean padding with invented content.
    bullets: list[str] = Field(min_length=0, max_length=4)


class ProjectEntry(BaseEntry):
    # bullets[0] is always the project's plain-language intro; the rest are
    # 1-4 result bullets, so 2-5 entries total.
    bullets: list[str] = Field(min_length=2, max_length=5)


class SkillGroup(BaseModel):
    name: str
    items: list[str]


class Certification(BaseModel):
    name: str
    issuer: str
    issued: str
    expires: str | None = None


class Language(BaseModel):
    language: str
    level: str


class CVContent(BaseModel):
    """
    The content of one rendered CV.

    Render order is passed to render_cv() as an explicit section_order,
    not implied by field order here. Nothing renders that is not in
    this model.
    """

    full_name: str
    target_title: str
    location: str
    contact_details: list[str] = Field(default_factory=list)   # plain text: email, phone
    contact_links: list[str] = Field(default_factory=list)     # full https:// URLs: linkedin, github
    profile: str = Field(max_length=PROFILE_MAX_CHARS)     # 2-3 lines
    skill_groups: list[SkillGroup]
    experience: list[ExperienceEntry]
    education: list[EducationEntry]
    projects: list[ProjectEntry]
    certifications: list[Certification]
    languages: list[Language]
    coursework: list[str] = []
