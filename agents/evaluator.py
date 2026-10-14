
from agents.client import client
from agents.fact_render import render_facts
from cv.facts import CVFacts
from guidelines import GENERIC_HOOK_RULE
from models.jd_schema import ParsedJD
from models.eval_schema import EvalResult


def evaluate_cover_letter(
    cover_letter: str,
    facts: CVFacts,
    parsed_jd: ParsedJD,
) -> EvalResult:
    """
    Evaluate one generated cover letter against the CV fact base and JD.
    """

    response = client.beta.chat.completions.parse(
        model="gpt-4o",
        temperature=0,
        seed=42,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict cover-letter evaluator. "
                    "Apply the score bands literally and conservatively.\n\n"

                    "Evaluate exactly five criteria:\n"
                    "1. Hook\n"
                    "2. Keyword match\n"
                    "3. Proof-over-pitch\n"
                    "4. Zero resume duplication\n"
                    "5. CTA\n\n"

                    f"{GENERIC_HOOK_RULE}\n\n"

                    "Use the CV fact base for proof-over-pitch and resume-duplication checks. "
                    "Use the parsed JD for hook relevance and keyword alignment. "
                    "Do not compensate for a failed criterion by inflating unrelated criteria. "
                    "The overall score must equal the mathematical sum of the five scores. "
                    "Give concrete revision instructions rather than vague praise."
                ),
            },
            {
                "role": "user",
                "content": (
                    "CV fact base:\n"
                    f"{render_facts(facts)}\n\n"
                    "Parsed Job Description:\n"
                    f"{parsed_jd.model_dump_json(indent=2)}\n\n"
                    "Cover Letter:\n"
                    f"{cover_letter}"
                ),
            },
        ],
        response_format=EvalResult,
    )

    result = response.choices[0].message.parsed

    if result is None:
        raise ValueError("Evaluator returned no structured EvalResult.")

    return result