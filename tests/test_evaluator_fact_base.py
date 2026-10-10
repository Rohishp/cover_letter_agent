from unittest.mock import MagicMock, patch

from agents import evaluator
from models.eval_schema import EvalResult
from models.jd_schema import ParsedJD


def test_evaluator_judges_against_the_fact_base(facts):
    create = MagicMock()
    create.return_value.choices = [MagicMock(message=MagicMock(parsed=EvalResult.model_construct()))]

    with patch.object(evaluator.client.beta.chat.completions, "parse", create):
        evaluator.evaluate_cover_letter("A letter.", facts, ParsedJD())

    content = create.call_args.kwargs["messages"][1]["content"]
    assert content.startswith("CV fact base:")
    assert facts.work_experience.entries[0].organisation in content
