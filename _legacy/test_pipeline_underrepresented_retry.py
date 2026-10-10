# Phase G item 2, corrected by Phase H item 3: a core-must-have the
# matcher scored strong/partial but the letter never mentioned must
# trigger a retry through the real pipeline loop -- with the SPECIFIC
# FACT ID(S) that evidence it fed back as guidance, never a bare term.
# A bare term with no grounded evidence is what caused the writer to
# fabricate a job role in Phase G's original version (see Phase H).

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

import pipeline
from cv.facts import (
    CVFacts,
    Certifications,
    Coursework,
    Education,
    Extras,
    LanguageFact,
    Languages,
    Meta,
    Personal,
    Projects,
    Skills,
    SkillGroupFact,
    WorkExperience,
    WorkExperienceFact,
)
from models.eval_schema import CriterionScore, EvalResult
from models.jd_schema import ParsedJD
from models.match_schema import MatchAnalysis, MatchEvidence


JD_TEXT = (
    "Data Engineer at Test Co. We are looking for a data engineer with "
    "strong SQL and Python experience to join our platform team. You "
    "will own data pipelines end to end, from design through production "
    "operation, working closely with product and analytics."
)

APPLIED_FOR_ROLE = "Data Engineer"

PARSED_JD = ParsedJD(
    job_title="Data Engineer",
    company_name="Test Co",
    core_must_have_skills=["SQL"],
)

PASSING_EVAL_RESULT = EvalResult(
    hook=CriterionScore(score=15, feedback="ok"),
    keyword_match=CriterionScore(score=15, feedback="ok"),
    proof_over_pitch=CriterionScore(score=15, feedback="ok"),
    zero_resume_duplication=CriterionScore(score=15, feedback="ok"),
    cta=CriterionScore(score=15, feedback="ok"),
    overall_score=75,
    feedback_text="Looks good.",
)


@pytest.fixture
def sql_facts() -> CVFacts:
    """
    Mirrors the real motivating case: SQL is real (a Data Science Intern
    tools line and an Engineering skill group), but demonstrated in no
    bullet -- exactly what should surface a fact_id, not a bare term.
    """

    return CVFacts(
        meta=Meta(updated=date(2026, 1, 1), owner="Test Person"),
        personal=Personal(
            full_name="Test Person", location="Testville", email="test@example.com",
            phone="+1 555 0000", linkedin="https://www.linkedin.com/in/testperson",
            github="https://github.com/testperson", photo="exclude",
        ),
        languages=Languages(tier=1, entries=[LanguageFact(language="English", level="C1")]),
        education=Education(tier=1, entries=[]),
        work_experience=WorkExperience(
            tier=1,
            entries=[
                WorkExperienceFact(
                    position="Data Science Intern", organisation="Test Co Predecessor",
                    city="Testville", dates="2022 - 2023", tools="Python, SQL, Hadoop",
                    bullets=["Built data-processing workflows on Hadoop."],
                ),
            ],
        ),
        projects=Projects(tier=2, entries=[]),
        certifications=Certifications(tier=1, entries=[]),
        skills=Skills(groups=[SkillGroupFact(name="Engineering", items=["Python", "SQL", "Git"])]),
        coursework=Coursework(tier=3, include_when="", exclude_when="", render_as="bullet_list", items=[]),
        extras=Extras(awards=[], volunteering=[]),
    )


def _match_with_strong_sql() -> MatchAnalysis:
    return MatchAnalysis(
        core_must_have_matches=[
            MatchEvidence(
                requirement_id="core_1",
                jd_requirement="SQL",
                cv_evidence="SQL used at Test Co Predecessor.",
                strength="strong",
                explanation="Direct SQL evidence.",
            ),
        ],
        match_summary="Strong match.",
    )


def _build_mocks(write_cover_letter_mock) -> dict:
    return {
        "parse_jd_cached": MagicMock(return_value=(PARSED_JD, True)),
        "compare_cv_to_jd": MagicMock(return_value=_match_with_strong_sql()),
        "write_cover_letter": write_cover_letter_mock,
        "evaluate_cover_letter": MagicMock(return_value=PASSING_EVAL_RESULT),
        "save_state": MagicMock(return_value=None),
        "storage": MagicMock(write_text=MagicMock(return_value="cover_letters/test.txt")),
    }


def _run(sql_facts, write_cover_letter_mock):
    mocks = _build_mocks(write_cover_letter_mock)

    with patch.multiple(pipeline, **mocks):
        state = pipeline.run_pipeline(
            jd_text=JD_TEXT, facts=sql_facts, applied_for_role=APPLIED_FOR_ROLE,
        )

    return state


def test_missing_strong_requirement_triggers_one_retry_with_a_fact_id_not_a_bare_term(sql_facts):
    letters = [
        "I'm excited to bring my data engineering and Python skills to Test Co.",
        "I have hands-on SQL experience from production data-engineering work at Test Co.",
    ]
    write_cover_letter_mock = MagicMock(side_effect=lambda **kwargs: letters.pop(0))

    state = _run(sql_facts, write_cover_letter_mock)

    assert state.status == "completed"
    assert write_cover_letter_mock.call_count == 2
    assert state.underrepresented_requirements == []

    second_call_hint = write_cover_letter_mock.call_args_list[1].kwargs[
        "underrepresented_requirements_hint"
    ]
    assert second_call_hint == [
        {"jd_requirement": "SQL", "fact_ids": ["skill.engineering", "exp.test-co-predecessor"]}
    ]

    first_call_hint = write_cover_letter_mock.call_args_list[0].kwargs[
        "underrepresented_requirements_hint"
    ]
    assert first_call_hint == []


def test_letter_already_covering_strong_requirements_does_not_retry(sql_facts):
    letters = [
        "I have hands-on SQL experience from production data-engineering work at Test Co.",
    ]
    write_cover_letter_mock = MagicMock(side_effect=lambda **kwargs: letters.pop(0))

    state = _run(sql_facts, write_cover_letter_mock)

    assert state.status == "completed"
    assert write_cover_letter_mock.call_count == 1
    assert state.underrepresented_requirements == []


def test_still_missing_after_max_retries_accepts_the_letter_anyway(sql_facts):
    """
    A residual underrepresented requirement must never itself hard-fail
    an otherwise-passing letter -- it's a missed-case risk, not a
    fabrication risk. The run still completes; the gap stays visible in
    state.underrepresented_requirements for a human to see.
    """

    letter = "I'm excited to bring my data engineering and Python skills to Test Co."
    write_cover_letter_mock = MagicMock(return_value=letter)

    state = _run(sql_facts, write_cover_letter_mock)

    assert state.status == "completed"
    assert state.underrepresented_requirements != []
    # MAX_COVER_LETTER_RETRIES = 2 -> 3 total attempts before falling back.
    assert write_cover_letter_mock.call_count == pipeline.MAX_COVER_LETTER_RETRIES + 1
