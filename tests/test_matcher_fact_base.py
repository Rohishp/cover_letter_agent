from unittest.mock import MagicMock, patch

from agents import matcher
from agents.fact_render import render_facts
from agents.matcher import compare_cv_to_jd
from models.jd_schema import ParsedJD
from models.match_schema import MatchAnalysis


def test_render_includes_every_evidence_section(facts):
    text = render_facts(facts)

    for section in ("WORK EXPERIENCE", "EDUCATION", "PROJECTS", "SKILLS"):
        assert section in text

    first_job = facts.work_experience.entries[0]
    assert first_job.organisation in text
    assert first_job.bullets[0] in text
    assert facts.projects.entries[0].bullets[0] in text
    assert facts.languages.entries[0].language in text


def test_matcher_sends_the_fact_base(facts):
    create = MagicMock()
    create.return_value.choices = [MagicMock(message=MagicMock(parsed=MatchAnalysis(match_summary="t")))]

    with patch.object(matcher.client.beta.chat.completions, "parse", create):
        compare_cv_to_jd(ParsedJD(core_must_have_skills=["Python"]), facts)

    content = create.call_args.kwargs["messages"][1]["content"]
    assert content.startswith("CV fact base:")
    assert facts.work_experience.entries[0].organisation in content
