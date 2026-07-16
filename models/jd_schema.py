from enum import Enum

from pydantic import BaseModel, Field


class LocationStrategy(str, Enum):
    REMOTE = "Remote"
    HYBRID = "Hybrid"
    ONSITE = "Onsite"


class EmploymentType(str, Enum):
    MINIJOB = "Mini-job"
    WORKING_STUDENT = "Working Student"
    PART_TIME = "Part-time"
    FULL_TIME = "Full-time"
    INTERNSHIP = "Internship"
    TRAINEE = "Trainee"
    CONTRACT = "Contract"
    FREELANCE = "Freelance"


class SeniorityLevel(str, Enum):
    INTERN = "Intern"
    WERKSTUDENT = "Werkstudent"
    TRAINEE = "Trainee"
    ENTRY_LEVEL = "Entry Level"
    JUNIOR = "Junior"
    MID_LEVEL = "Mid-Level"
    SENIOR = "Senior"
    LEAD = "Lead"
    PRINCIPAL = "Principal"
    MANAGER = "Manager"


class ParsedJD(BaseModel):
    """
    Structured information extracted from one job description.

    Only explicitly stated information should be recorded.
    """

    job_title: str | None = Field(
        default=None,
        description="Exact job title stated in the job description.",
    )

    company_name: str | None = Field(
        default=None,
        description="Company or hiring organization explicitly stated in the JD.",
    )

    location: str | None = Field(
        default=None,
        description="City, country, office, or region stated for the role.",
    )

    employment_type: EmploymentType | None = Field(
        default=None,
        description="Employment type explicitly stated in the JD.",
    )

    seniority_level: SeniorityLevel | None = Field(
        default=None,
        description=(
            "Seniority or career stage explicitly stated or clearly contained "
            "in the job title, such as Werkstudent, Junior, Senior, or Lead."
        ),
    )

    required_experience: str | None = Field(
        default=None,
        description="Explicitly stated amount or level of required experience.",
    )

    core_mission_statement: str | None = Field(
        default=None,
        description="Concise summary of why the role exists.",
    )

    language_skills: list[str] = Field(
        default_factory=list,
        description=(
            "Required or preferred languages and proficiency levels explicitly "
            "stated in the JD."
        ),
    )

    technical_skills: list[str] = Field(
        default_factory=list,
        description=(
            "Technical skills, technologies, methods, frameworks, tools, and "
            "platforms explicitly mentioned anywhere in the JD."
        ),
    )

    location_strategy: LocationStrategy | None = Field(
        default=None,
        description="Remote, hybrid, or onsite arrangement when explicitly stated.",
    )

    location_strictness: bool | None = Field(
        default=None,
        description=(
            "True when a specific location is mandatory, False when explicitly "
            "flexible, and None when unclear."
        ),
    )

    legal_authorization_required: bool | None = Field(
        default=None,
        description=(
            "Whether the JD explicitly requires work authorization, citizenship, "
            "visa status, or security clearance."
        ),
    )

    core_must_have_skills: list[str] = Field(
        default_factory=list,
        description=(
            "The distinct capabilities most necessary to perform the role. "
            "Identify them from the complete JD, including the core mission, "
            "main responsibilities, and mandatory profile requirements. "
            "Prioritize capabilities on which multiple responsibilities depend. "
            "Merge overlapping requirements into one clear capability. "
            "Do not promote a technology merely because it appears once as an example."
        ),
    )

    supporting_skills: list[str] = Field(
        default_factory=list,
        description=(
            "Capabilities that support performance but should not dominate eligibility. "
            "Examples include structured working methods, documentation, communication, "
            "research, testing, stakeholder work, presentation, organization, ownership, "
            "and independent work."
        ),
    )

    eligibility_constraints: list[str] = Field(
        default_factory=list,
        description=(
            "Candidate conditions that determine eligibility, such as current student "
            "status, degree subject, remaining study duration, required availability, "
            "language level, location, work authorization, travel, or clearance."
        ),
    )

    nice_to_have_skills: list[str] = Field(
        default_factory=list,
        description=(
            "Optional or preferred skills that improve fit but are not required "
            "for base eligibility. Missing these must not reduce the base score."
        ),
    )

    application_document_requirements: list[str] = Field(
        default_factory=list,
        description=(
            "Documents or materials that must be submitted with the application, "
            "such as a certificate of enrollment, transcript, references, portfolio, "
            "work samples, or proof of qualifications. These must not be included "
            "in candidate-fit scoring."
        ),
    )