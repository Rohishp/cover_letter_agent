import json
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from models.cv_schema import ParsedCV
from models.jd_schema import ParsedJD
from models.match_schema import MatchAnalysis
from models.eval_schema import EvalResult, CoverLetterAttempt

from control_plane import storage

PipelineStatus = Literal[
    "created",
    "cv_loaded",
    "cv_parsed",
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

    cv_path: str | None = None
    storage_backend: str | None = None
    jd_source: Literal["clipboard", "argument"] | None = None

    raw_cv_text: str | None = None
    raw_jd_text: str | None = None

    jd_cache_hit: bool = False
    jd_cache_key: str | None = None

    parsed_cv: ParsedCV | None = None
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

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            "completed",
            "rejected",
            "failed",
        }

    @property
    def summary(self) -> dict:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "cv_path": self.cv_path,
            "jd_source": self.jd_source,
            "jd_cache_hit": self.jd_cache_hit,
            "job_title": (
                self.parsed_jd.job_title
                if self.parsed_jd
                else None
            ),
            "company_name": (
                self.parsed_jd.company_name
                if self.parsed_jd
                else None
            ),
            "core_must_have_score": (
                self.match_analysis.core_must_have_score
                if self.match_analysis
                else None
            ),
            "eligibility_score": (
                self.match_analysis.eligibility_score
                if self.match_analysis
                else None
            ),
            "supporting_score": (
                self.match_analysis.supporting_score
                if self.match_analysis
                else None
            ),
            "nice_to_have_score": (
                self.match_analysis.nice_to_have_score
                if self.match_analysis
                else None
            ),
            "base_score": (
                self.match_analysis.base_score
                if self.match_analysis
                else None
            ),
            "overall_score": (
                self.match_analysis.overall_score
                if self.match_analysis
                else None
            ),
            "match_recommendation": (
                self.match_analysis.recommendation
                if self.match_analysis
                else None
            ),
            "eval_score": self.eval_score,
            "cover_letter_key": self.cover_letter_key,
            "retry_count": self.retry_count,
            "attempt_count": len(self.cover_letter_attempts),
            "application_document_requirements": (
                self.application_document_requirements
            ),
            "warnings": self.warnings,
            "error": self.error,
        }



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


def load_state(run_id: str) -> CoverLetterState:
    """
    Load pipeline state through the storage layer.
    """

    key = f"states/{run_id}.json"

    json_string = storage.read_text(key)

    if json_string is None:
        raise FileNotFoundError(
            f"No saved state found for run_id: {run_id}"
        )

    data = json.loads(json_string)

    return CoverLetterState(**data)


def list_states() -> list[dict]:
    keys = storage.list_keys("states/")

    summaries = []

    # run_id embeds a sortable timestamp, so a reverse key sort gives the
    # same most-recent-first order the old LastModified sort gave.
    for key in sorted(keys, reverse=True):
        try:
            run_id = key.removeprefix("states/").removesuffix(".json")
            state = load_state(run_id)
            summaries.append(state.summary)
        except Exception:
            continue

    return summaries