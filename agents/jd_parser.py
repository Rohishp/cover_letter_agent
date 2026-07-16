import pyperclip

from dotenv import load_dotenv
from openai import OpenAI

from models.jd_schema import ParsedJD


load_dotenv()
client = OpenAI()


def read_clipboard_windows() -> str:
    """
    Read the copied job description from the Windows clipboard.
    """

    text = pyperclip.paste()

    if not text or not text.strip():
        raise ValueError(
            "Clipboard is empty. Copy the complete job description first."
        )

    return text.strip()


def parse_jd(raw_jd: str) -> ParsedJD:
    """
    Parse raw JD text into one structured ParsedJD object.
    """

    response = client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract structured facts from the job description. "
                    "Use only information explicitly present in the text. "
                    "Do not invent or assume missing facts.\n\n"

                    "Analyze the complete role rather than following bullet formatting "
                    "mechanically.\n\n"

                    "Classify requirements as follows:\n"
                    "- core_must_have_skills: the distinct capabilities on which the "
                    "main work depends and without which the role could not reasonably "
                    "be performed.\n"
                    "- supporting_skills: behavioral, communication, documentation, "
                    "research, testing, organization, presentation, or working-method "
                    "capabilities that support performance.\n"
                    "- eligibility_constraints: candidate conditions such as student "
                    "status, field of study, study duration remaining, availability, "
                    "language level, location, work authorization, travel, or clearance.\n"
                    "- nice_to_have_skills: explicitly optional, preferred, advantageous, "
                    "or ideal capabilities.\n"
                    "- application_document_requirements: documents or materials that "
                    "must be submitted with the application. These are not eligibility "
                    "evidence and must not be placed in eligibility_constraints.\n\n"

                    "Merge duplicate and overlapping capabilities. "
                    "Do not promote a tool to core must-have merely because it appears once. "
                    "When several tools are examples of a broader capability, retain the "
                    "broader capability unless each tool is independently mandatory.\n\n"

                    "Example distinction:\n"
                    "- 'At least 12 months of study remaining' is an eligibility constraint.\n"
                    "- 'Submit a current certificate of enrollment' is an application "
                    "document requirement."
                ),
            },
            {
                "role": "user",
                "content": raw_jd,
            },
        ],
        response_format=ParsedJD,
    )

    parsed = response.choices[0].message.parsed

    if parsed is None:
        raise ValueError("The JD parser returned no structured result.")

    return parsed