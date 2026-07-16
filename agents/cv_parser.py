from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader

from models.cv_schema import ParsedCV


load_dotenv()
client = OpenAI()


def extract_pdf_text(pdf_path: str) -> str:
    path = Path(pdf_path)

    if not path.exists():
        raise FileNotFoundError(f"CV PDF not found: {path}")

    reader = PdfReader(str(path))

    all_text = ""

    for page_number, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        all_text += f"\n--- Page {page_number} ---\n{page_text}"

    if not all_text.strip():
        raise ValueError("No text could be extracted from the CV PDF.")

    return all_text


def parse_cv(text: str) -> ParsedCV:
    response = client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract only information explicitly present in the CV. "
                    "Do not infer, assume, or invent missing facts."
                ),
            },
            {
                "role": "user",
                "content": text,
            },
        ],
        response_format=ParsedCV,
    )

    return response.choices[0].message.parsed