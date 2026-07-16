from pydantic import BaseModel, Field
from enum import Enum


class ParsedCV(BaseModel):
    """
    Structured fields extracted from the resume/CV.

    Important rule:
    Every field must be based only on evidence explicitly present in the CV.
    Do not infer, assume, or invent missing information.
    """

    candidate_name:str = Field(
        default_factory=list,
        description=(
            "Name of the candidate mentioned in the Resume"
        )
    )

    technical_skills: list[str] = Field(
        default_factory=list,
        description=(
            "Technical skills explicitly mentioned in the CV, including programming "
            "languages, frameworks, libraries, databases, cloud skills, data skills, "
            "AI/ML skills, software engineering skills, or other technical capabilities."
        )
    )

    projects: list[str] = Field(
        default_factory=list,
        description=(
            "Projects explicitly mentioned in the CV. Include project names, short "
            "descriptions, technologies used, responsibilities, outcomes, and measurable "
            "results when available."
        )
    )

    work_experience: list[str] = Field(
        default_factory=list,
        description=(
            "Professional work experience explicitly mentioned in the CV. Include job "
            "titles, employers, dates or duration if present, responsibilities, tools used, "
            "achievements, and measurable impact."
        )
    )

    education: list[str] = Field(
        default_factory=list,
        description=(
            "Education history explicitly mentioned in the CV. Include degrees, fields "
            "of study, universities or institutions, graduation dates if present, thesis "
            "topics, academic projects, and relevant coursework when listed."
        )
    )

    certifications: list[str] = Field(
        default_factory=list,
        description=(
            "Certifications, licenses, credentials, or completed professional courses "
            "explicitly mentioned in the CV. Include issuing organization and date if present."
        )
    )

    tools_and_platforms: list[str] = Field(
        default_factory=list,
        description=(
            "Tools, platforms, software, development environments, operating systems, "
            "cloud platforms, DevOps tools, analytics platforms, version control systems, "
            "or productivity tools explicitly mentioned in the CV."
        )
    )

    domain_experience: list[str] = Field(
        default_factory=list,
        description=(
            "Industries, business domains, or application areas explicitly shown in the CV. "
            "Examples include automotive, HR IT, logistics, e-commerce, finance, healthcare, "
            "computer vision, embedded systems, data engineering, or process optimization."
        )
    )

    soft_skills: list[str] = Field(
        default_factory=list,
        description=(
            "Soft skills explicitly mentioned or directly evidenced in the CV text. "
            "Examples include communication, leadership, stakeholder management, teamwork, "
            "problem-solving, mentoring, analytical thinking, ownership, or adaptability. "
            "Do not infer soft skills unless the CV directly states or strongly evidences them."
        )
    )

    

    location_work_authorization_availability_language_fit: list[str] = Field(
        default_factory=list,
        description=(
            "Location, relocation preference, work authorization, visa status, availability, "
            "notice period, and language skills explicitly mentioned in the CV."
        )
    )