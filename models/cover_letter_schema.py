from typing import Literal

from pydantic import BaseModel, Field


class CoverLetterParagraph(BaseModel):
    """
    One paragraph of a generated cover letter.

    kind and fact_ids are set before text, so the model commits to what
    it is grounding a paragraph in before writing the prose (Phase H:
    ground first, write second -- the same ordering discipline
    CVSelection/ProfileSelection already use elsewhere in this codebase).

    kind="factual": the paragraph makes a claim about the candidate
    (a role held, a project, a skill, an outcome). fact_ids must name at
    least one real cv/facts.py ID this claim traces to; validated
    against facts.by_id() -- an empty or invalid list is a hard fail.

    kind="connective": purely rhetorical text with no factual claim
    about the candidate (greeting, closing, "I look forward to...").
    fact_ids stays empty and is not required.
    """

    kind: Literal["factual", "connective"]
    fact_ids: list[str] = Field(default_factory=list)
    text: str


class CoverLetterDraft(BaseModel):
    paragraphs: list[CoverLetterParagraph]
