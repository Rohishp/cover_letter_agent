from typing import Literal

from pydantic import BaseModel, Field


EvidenceStrength = Literal[
    "strong",
    "partial",
    "indirect",
    "not_evidenced",
]


class MatchEvidence(BaseModel):
    """
    Evidence judgment for one fixed requirement from ParsedJD.
    """

    requirement_id: str = Field(
        description="Stable identifier supplied by deterministic code."
    )

    jd_requirement: str = Field(
        description=(
            "Exact requirement text supplied from ParsedJD. "
            "It must not be rewritten, split, merged, or reclassified."
        )
    )

    cv_evidence: str | None = Field(
        default=None,
        description=(
            "Strongest relevant CV evidence for this exact requirement. "
            "Return None when no relevant evidence exists."
        ),
    )

    strength: EvidenceStrength = Field(
        description=(
            "strong = direct and convincing evidence; "
            "partial = relevant but incomplete evidence; "
            "indirect = related evidence suggests the capability; "
            "not_evidenced = no relevant CV evidence."
        )
    )

    explanation: str = Field(
        description=(
            "Concise explanation grounded only in the supplied CV and requirement."
        )
    )


class MatchAnalysis(BaseModel):
    """
    Requirement-level comparison between ParsedCV and ParsedJD.

    The LLM judges evidence strength.
    Python calculates all scores.
    """

    core_must_have_matches: list[MatchEvidence] = Field(
        default_factory=list
    )

    supporting_matches: list[MatchEvidence] = Field(
        default_factory=list
    )

    eligibility_matches: list[MatchEvidence] = Field(
        default_factory=list
    )

    nice_to_have_matches: list[MatchEvidence] = Field(
        default_factory=list
    )

    relevant_technical_skills: list[str] = Field(default_factory=list)
    relevant_projects: list[str] = Field(default_factory=list)
    relevant_work_experience: list[str] = Field(default_factory=list)
    relevant_education: list[str] = Field(default_factory=list)
    relevant_certifications: list[str] = Field(default_factory=list)
    relevant_tools_and_platforms: list[str] = Field(default_factory=list)
    relevant_domain_experience: list[str] = Field(default_factory=list)
    relevant_soft_skills: list[str] = Field(default_factory=list)

    location_work_authorization_availability_language_fit: list[str] = Field(
        default_factory=list
    )

    missing_or_weak_evidence: list[str] = Field(default_factory=list)

    core_must_have_score: int | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    supporting_score: int | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    eligibility_score: int | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    nice_to_have_score: int | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    base_score: int | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    overall_score: int | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    recommendation: Literal[
        "generate_cover_letter",
        "manual_review",
        "reject",
    ] | None = Field(
        default=None,
        description="Informational LLM opinion only.",
    )

    match_summary: str