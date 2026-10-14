"""
run_pipeline through its public interface. Only the OpenAI boundary is faked
(the one shared client's `parse`); the JD cache, storage (a tmp dir), scoring,
validators, writer checks and the stage loop all run for real.
"""

import json
from types import SimpleNamespace

import pytest

import pipeline
from agents.client import client
from cv.facts import (
    CVFacts, Certifications, Coursework, Education, Extras, LanguageFact,
    Languages, Meta, Personal, Projects, SkillGroupFact, Skills,
    WorkExperience, WorkExperienceFact,
)
from datetime import date
from models.cover_letter_schema import CoverLetterDraft, CoverLetterParagraph
from models.eval_schema import CriterionScore, EvalResult
from models.jd_schema import ParsedJD
from models.match_schema import MatchAnalysis, MatchEvidence


# validate_jd_input_quality requires >= 200 characters of raw JD text.
JD_TEXT = (
    "Backend Engineer at Test Co. We are looking for a backend engineer "
    "with strong Python and Kubernetes experience to join our platform "
    "team. You will own services end to end, from design through "
    "production operation, working closely with product and SRE."
)
APPLIED_FOR_ROLE = "Backend Engineer"

PARSED_JD = ParsedJD(
    job_title="Backend Engineer", company_name="Test Co",
    core_must_have_skills=["Python", "Kubernetes"],
)

PASSING_EVAL = EvalResult(
    hook=CriterionScore(score=15, feedback="ok"),
    keyword_match=CriterionScore(score=15, feedback="ok"),
    proof_over_pitch=CriterionScore(score=15, feedback="ok"),
    zero_resume_duplication=CriterionScore(score=15, feedback="ok"),
    cta=CriterionScore(score=15, feedback="ok"),
    overall_score=75,
    feedback_text="Looks good.",
)


def _match(strength: str) -> MatchAnalysis:
    return MatchAnalysis(
        core_must_have_matches=[
            MatchEvidence(
                requirement_id=f"core_{i}", jd_requirement=req, strength=strength,
                explanation="x", gap_note="missing" if strength == "not_evidenced" else None,
            )
            for i, req in enumerate(PARSED_JD.core_must_have_skills, start=1)
        ],
        match_summary="x",
    )


def _draft(text: str, fact_id: str) -> CoverLetterDraft:
    return CoverLetterDraft(paragraphs=[
        CoverLetterParagraph(kind="connective", text="Dear Test Co team,"),
        CoverLetterParagraph(kind="factual", fact_ids=[fact_id], text=text),
    ])


class FakeOpenAI:
    """Stands in for client.beta.chat.completions.parse, dispatching on response_format."""

    def __init__(self, parsed_jd, match, drafts, eval_result=PASSING_EVAL):
        self.replies = {ParsedJD: [parsed_jd], MatchAnalysis: [match], EvalResult: [eval_result]}
        self.drafts = list(drafts)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        kind = kwargs["response_format"]

        if kind is CoverLetterDraft:
            # Last draft repeats, so a run can exhaust its retries.
            parsed = self.drafts.pop(0) if len(self.drafts) > 1 else self.drafts[0]
        else:
            parsed = self.replies[kind][0]

        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))])

    def of(self, kind):
        return [c for c in self.calls if c["response_format"] is kind]


@pytest.fixture(autouse=True)
def local_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCAL_DATA_DIR", str(tmp_path / "data"))


def _run(monkeypatch, fake, facts, jd_text=JD_TEXT, **kwargs):
    monkeypatch.setattr(client.beta.chat.completions, "parse", fake)
    return pipeline.run_pipeline(
        jd_text=jd_text, facts=facts, applied_for_role=APPLIED_FOR_ROLE, **kwargs
    )


GOOD = _draft("At Acme Corp I did thing one with 42 widgets.", "exp.acme")


def test_force_false_on_rejecting_match_stays_rejected(monkeypatch, facts):
    fake = FakeOpenAI(PARSED_JD, _match("not_evidenced"), [GOOD])
    state = _run(monkeypatch, fake, facts, force=False)

    assert state.status == "rejected"
    assert state.cover_letter is None
    assert state.forced is False
    assert state.match_gate_result == "would_have_rejected"
    assert fake.of(CoverLetterDraft) == []


def test_force_true_on_rejecting_match_proceeds_and_writes(monkeypatch, facts):
    fake = FakeOpenAI(PARSED_JD, _match("not_evidenced"), [GOOD])
    state = _run(monkeypatch, fake, facts, force=True)

    assert state.status == "completed"
    assert state.forced is True
    assert state.match_gate_result == "would_have_rejected"
    assert state.cover_letter.startswith("Dear Test Co team,")
    assert len(fake.of(CoverLetterDraft)) == 1


def test_forced_writer_call_is_indistinguishable_from_a_normal_one(monkeypatch, facts):
    forced = FakeOpenAI(PARSED_JD, _match("not_evidenced"), [GOOD])
    _run(monkeypatch, forced, facts, force=True)
    normal = FakeOpenAI(PARSED_JD, _match("strong"), [GOOD])
    normal_state = _run(monkeypatch, normal, facts, force=False)

    forced_call, normal_call = forced.of(CoverLetterDraft)[0], normal.of(CoverLetterDraft)[0]

    assert normal_state.forced is False
    assert normal_state.match_gate_result == "passed"
    assert set(forced_call) == set(normal_call)
    assert [m["role"] for m in forced_call["messages"]] == [m["role"] for m in normal_call["messages"]]
    assert "force" not in " ".join(m["content"] for m in forced_call["messages"]).lower()
    assert "Evaluator feedback" not in forced_call["messages"][1]["content"]


@pytest.fixture
def saved_statuses(monkeypatch):
    """Records the status at every real save_state call (the save still happens)."""

    seen = []
    real = pipeline.save_state
    monkeypatch.setattr(pipeline, "save_state", lambda state: (seen.append(state.status), real(state))[1])
    return seen


def _in_order(seen, expected):
    positions = [seen.index(status) for status in expected]
    return positions == sorted(positions)


def test_state_is_persisted_on_every_transition(monkeypatch, facts, tmp_path, saved_statuses):
    fake = FakeOpenAI(PARSED_JD, _match("strong"), [GOOD])
    state = _run(monkeypatch, fake, facts)

    assert _in_order(saved_statuses, [
        "created", "jd_loaded", "jd_parsed", "jd_validated", "matching", "match_complete",
        "writing_cover_letter", "cover_letter_ready", "evaluating_cover_letter",
        "evaluation_complete", "completed",
    ])
    saved = json.loads((tmp_path / "data" / "states" / f"{state.run_id}.json").read_text(encoding="utf-8"))
    assert saved["status"] == "completed"
    assert (tmp_path / "data" / saved["cover_letter_key"]).read_text(encoding="utf-8") == state.cover_letter


def test_rejected_and_failed_runs_persist_their_terminal_state(monkeypatch, facts, saved_statuses):
    _run(monkeypatch, FakeOpenAI(PARSED_JD, _match("not_evidenced"), [GOOD]), facts)
    assert saved_statuses[-1] == "rejected"

    saved_statuses.clear()
    _run(monkeypatch, FakeOpenAI(PARSED_JD, _match("strong"), [GOOD]), facts, jd_text="Too short.")
    assert saved_statuses[-1] == "failed"


def test_failing_evaluation_retries_with_feedback_then_fails(monkeypatch, facts):
    weak = CriterionScore(score=5, feedback="weak")
    low = PASSING_EVAL.model_copy(update={
        "keyword_match": weak, "proof_over_pitch": weak, "zero_resume_duplication": weak,
        "cta": weak, "overall_score": 35, "feedback_text": "Make the hook sharper.",
    })
    fake = FakeOpenAI(PARSED_JD, _match("strong"), [GOOD], eval_result=low)
    state = _run(monkeypatch, fake, facts)
    requests = [c["messages"][1]["content"] for c in fake.of(CoverLetterDraft)]

    assert state.status == "failed"
    assert "after 2 retries. Final score: 35" in state.error
    assert len(requests) == pipeline.MAX_COVER_LETTER_RETRIES + 1
    assert "Make the hook sharper." not in requests[0]
    assert "Make the hook sharper." in requests[1]


def test_api_key_in_an_error_is_redacted(monkeypatch, facts):
    def boom(**kwargs):
        raise RuntimeError("Incorrect API key provided: sk-proj-abc123XYZ.")

    state = _run(monkeypatch, boom, facts)

    assert state.status == "failed"
    assert "sk-proj-abc123XYZ" not in state.error
    assert "sk-***" in state.error


def test_too_short_jd_fails_before_any_matching(monkeypatch, facts):
    fake = FakeOpenAI(PARSED_JD, _match("strong"), [GOOD])
    state = _run(monkeypatch, fake, facts, jd_text="Too short.")

    assert state.status == "failed"
    assert "too short" in state.error
    assert fake.of(MatchAnalysis) == []


# --- underrepresented-requirement retry (needs a fact base with SQL only in tools/skills) ---

SQL_JD_TEXT = (
    "Data Engineer at Test Co. We are looking for a data engineer with "
    "strong SQL and Python experience to join our platform team. You "
    "will own data pipelines end to end, from design through production "
    "operation, working closely with product and analytics."
)
SQL_JD = ParsedJD(job_title="Data Engineer", company_name="Test Co", core_must_have_skills=["SQL"])
SQL_MATCH = MatchAnalysis(
    core_must_have_matches=[MatchEvidence(
        requirement_id="core_1", jd_requirement="SQL",
        cv_evidence="SQL used at Test Co Predecessor.", strength="strong", explanation="Direct.",
    )],
    match_summary="Strong match.",
)
WITHOUT_SQL = _draft("My Python work on Hadoop data workflows is a direct fit.", "exp.test-co-predecessor")
WITH_SQL = _draft("My Python and SQL work on Hadoop data workflows is a direct fit.", "exp.test-co-predecessor")


@pytest.fixture
def sql_facts() -> CVFacts:
    return CVFacts(
        meta=Meta(updated=date(2026, 1, 1), owner="Test Person"),
        personal=Personal(
            full_name="Test Person", location="Testville", email="test@example.com",
            phone="+1 555 0000", linkedin="https://www.linkedin.com/in/testperson",
            github="https://github.com/testperson", photo="exclude",
        ),
        languages=Languages(tier=1, entries=[LanguageFact(language="English", level="C1")]),
        education=Education(tier=1, entries=[]),
        work_experience=WorkExperience(tier=1, entries=[WorkExperienceFact(
            position="Data Science Intern", organisation="Test Co Predecessor",
            city="Testville", dates="2022 - 2023", tools="Python, SQL, Hadoop",
            bullets=["Built data-processing workflows on Hadoop."],
        )]),
        projects=Projects(tier=2, entries=[]),
        certifications=Certifications(tier=1, entries=[]),
        skills=Skills(groups=[SkillGroupFact(name="Engineering", items=["Python", "SQL", "Git"])]),
        coursework=Coursework(tier=3, include_when="", exclude_when="", render_as="bullet_list", items=[]),
        extras=Extras(awards=[], volunteering=[]),
    )


def test_missing_strong_requirement_retries_once_with_fact_ids_not_a_bare_term(monkeypatch, sql_facts):
    fake = FakeOpenAI(SQL_JD, SQL_MATCH, [WITHOUT_SQL, WITH_SQL])
    state = _run(monkeypatch, fake, sql_facts, jd_text=SQL_JD_TEXT)
    first, second = (c["messages"][1]["content"] for c in fake.of(CoverLetterDraft))

    assert state.status == "completed"
    assert len(fake.of(CoverLetterDraft)) == 2
    assert state.underrepresented_requirements == []
    assert "left real, matcher-confirmed evidence unused" not in first
    assert "SQL -- cite skill.engineering, exp.test-co-predecessor to cover this" in second


def test_letter_already_covering_strong_requirements_does_not_retry(monkeypatch, sql_facts):
    fake = FakeOpenAI(SQL_JD, SQL_MATCH, [WITH_SQL])
    state = _run(monkeypatch, fake, sql_facts, jd_text=SQL_JD_TEXT)

    assert state.status == "completed"
    assert len(fake.of(CoverLetterDraft)) == 1


def test_still_missing_after_max_retries_accepts_the_letter_anyway(monkeypatch, sql_facts):
    fake = FakeOpenAI(SQL_JD, SQL_MATCH, [WITHOUT_SQL])
    state = _run(monkeypatch, fake, sql_facts, jd_text=SQL_JD_TEXT)

    assert state.status == "completed"
    assert state.underrepresented_requirements != []
    assert len(fake.of(CoverLetterDraft)) == pipeline.MAX_COVER_LETTER_RETRIES + 1
