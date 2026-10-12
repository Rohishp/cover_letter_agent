import json
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from models.jd_schema import ParsedJD
from models.match_schema import MatchAnalysis
from models.eval_schema import EvalResult, CoverLetterAttempt

from control_plane import storage

PipelineStatus = Literal[
    "created",
    "jd_loaded",
    "jd_parsed",
    "jd_validated",
    "matching",
    "match_complete",
    "writing_cover_letter",
    "cover_letter_ready",
    "evaluating_cover_letter",
    "evaluation_complete",
    "completed",
    "rejected",
    "failed",
]

class CoverLetterState(BaseModel):
    run_id: str = Field(
        default_factory=lambda: (
            f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_"
            f"{uuid.uuid4().hex[:6]}"
        )
    )

    status: PipelineStatus = "created"

    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )

    updated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )

    raw_jd_text: str | None = None

    jd_cache_hit: bool = False
    jd_cache_key: str | None = None

    parsed_jd: ParsedJD | None = None

    application_document_requirements: list[str] = Field(
        default_factory=list
    )

    match_analysis: MatchAnalysis | None = None

    cover_letter: str | None = None

    eval_result: EvalResult | None = None
    eval_score: int | None = None
    eval_feedback: str | None = None

    retry_count: int = 0

    forced: bool = False
    match_gate_result: Literal["passed", "would_have_rejected"] | None = None

    # Real, matcher-confirmed core-must-have evidence the current letter
    # never mentioned -- drives one retry (Phase G item 2), unlike the
    # containment warnings above. See control_plane/match_diagnostics.py.
    underrepresented_requirements: list[dict] = Field(default_factory=list)

    cover_letter_key: str | None = None

    cover_letter_attempts: list[CoverLetterAttempt] = Field(
        default_factory=list
    )

    warnings: list[str] = Field(default_factory=list)
    error: str | None = None

    def touch(self) -> None:
        self.updated_at = datetime.now().isoformat()

    def update_status(
        self,
        status: PipelineStatus,
    ) -> None:
        self.status = status
        self.touch()

    def add_warning(
        self,
        warning: str,
    ) -> None:
        if warning not in self.warnings:
            self.warnings.append(warning)
        self.touch()

    def set_error(
        self,
        error: str,
    ) -> None:
        self.status = "failed"
        self.error = error
        self.touch()


def save_state(state: CoverLetterState) -> str:
    """
    Save pipeline state through the storage layer.
    """
    state.touch()
    key = f"states/{state.run_id}.json"

    json_string = json.dumps(
        state.model_dump(),
        indent=2,
        ensure_ascii=False,
        default=str,
    )

    return storage.write_text(key, json_string)
