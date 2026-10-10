from datetime import datetime

from pydantic import BaseModel, Field

from guidelines import GENERIC_HOOK_EXAMPLES


class CriterionScore(BaseModel):
    score: int = Field(
        ge=0,
        le=20,
    )

    feedback: str


class EvalResult(BaseModel):
    hook: CriterionScore = Field(
        description=(
            "Score the opening from 0 to 20. "
            "0-5: generic application boilerplate such as "
            f"{', '.join(repr(example) for example in GENERIC_HOOK_EXAMPLES)}, "
            "or equivalent wording. "
            "6-12: mentions the role but remains generic and reusable. "
            "13-17: connects specific candidate evidence to the role mission. "
            "18-20: distinctive, concise, evidence-based, and highly role-specific."
        )
    )

    keyword_match: CriterionScore = Field(
        description=(
            "Score JD alignment from 0 to 20. "
            "0-5: major role concepts are absent or misunderstood. "
            "6-12: some relevant terms appear, but important themes are missing or generic. "
            "13-17: most important JD concepts are used naturally and accurately. "
            "18-20: the most role-critical concepts are prioritized, integrated naturally, "
            "and demonstrate strong understanding without keyword stuffing."
        )
    )

    proof_over_pitch: CriterionScore = Field(
        description=(
            "Score concrete evidence from 0 to 20. "
            "0-5: mostly unsupported self-promotion and vague claims. "
            "6-12: some evidence exists but remains vague or weakly connected. "
            "13-17: major claims are supported by relevant projects, tools, experience, "
            "education, certifications, or outcomes. "
            "18-20: nearly every important claim is supported by concise, relevant, "
            "role-connected evidence."
        )
    )

    zero_resume_duplication: CriterionScore = Field(
        description=(
            "Compare the letter directly with the parsed CV. "
            "0-5: largely repeats CV bullets, lists tools, or follows resume sections. "
            "6-12: paraphrases the resume but still reads like a resume summary. "
            "13-17: selects relevant CV facts and explains why they matter for the JD. "
            "18-20: transforms CV evidence into a focused narrative of fit and contribution "
            "with minimal unnecessary repetition."
        )
    )

    cta: CriterionScore = Field(
        description=(
            "Score the closing from 0 to 20. "
            "0-5: absent, abrupt, passive, desperate, demanding, or inappropriate. "
            "6-12: polite but generic with no meaningful next step. "
            "13-17: concise, confident, professional, and invites discussion. "
            "18-20: natural, role-specific, confident without pressure, and establishes "
            "a clear credible next step."
        )
    )

    overall_score: int = Field(
        ge=0,
        le=100,
        description="Exact sum of all five criterion scores.",
    )

    feedback_text: str = Field(
        description=(
            "Concrete revision instructions focused on the weakest criteria."
        )
    )


class CoverLetterAttempt(BaseModel):
    """
    One generated cover letter and its evaluation.
    """

    attempt_number: int = Field(ge=1)
    cover_letter: str
    eval_result: EvalResult

    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )