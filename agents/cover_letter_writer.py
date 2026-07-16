from dotenv import load_dotenv
from openai import OpenAI

from models.cv_schema import ParsedCV
from models.jd_schema import ParsedJD
from models.match_schema import MatchAnalysis


load_dotenv()
client = OpenAI()


def write_cover_letter(
    parsed_cv: ParsedCV,
    parsed_jd: ParsedJD,
    match_analysis: MatchAnalysis,
    eval_feedback: str | None = None,
) -> str:
    """
    Generate or revise a cover letter using approved evidence only.
    """

    feedback_block = ""

    if eval_feedback:
        feedback_block = (
            "\nEvaluator feedback from the previous attempt:\n"
            f"{eval_feedback}\n"
            "Revise the new letter to fix these issues.\n"
        )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "Write a concise, specific, professional cover letter. "
                    "Use only evidence present in the parsed CV, parsed JD, and match analysis. "
                    "Do not invent experience, achievements, availability, language ability, "
                    "work authorization, education, or company facts.\n\n"

                    "Do not begin with generic wording such as:\n"
                    "- I am writing to apply\n"
                    "- I am writing to express my interest\n"
                    "- I am excited to apply\n\n"

                    "Begin with a role-specific, evidence-based connection between the "
                    "candidate and the role's mission."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Parsed CV:\n"
                    f"{parsed_cv.model_dump_json(indent=2)}\n\n"
                    "Parsed Job Description:\n"
                    f"{parsed_jd.model_dump_json(indent=2)}\n\n"
                    "Match Analysis:\n"
                    f"{match_analysis.model_dump_json(indent=2)}\n"
                    f"{feedback_block}\n"

                    "Requirements:\n"
                    "- Use a strong role-specific hook.\n"
                    "- Naturally reflect important JD concepts.\n"
                    "- Use concrete proof instead of unsupported claims.\n"
                    "- Interpret CV evidence rather than copying resume bullets.\n"
                    "- End with a concise professional CTA.\n"
                    "- Do not mention weaknesses or missing evidence.\n"
                    "- If the company name is missing, use 'Dear Hiring Team,'.\n"
                    "- Keep the letter approximately 250-350 words."
                ),
            },
        ],
    )

    content = response.choices[0].message.content

    if not content or not content.strip():
        raise ValueError("Cover-letter writer returned empty output.")

    return content.strip()