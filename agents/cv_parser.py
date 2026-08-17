from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader
from io import BytesIO
from control_plane import storage
from models.cv_schema import ParsedCV

load_dotenv()
client = OpenAI()


def extract_pdf_text(
    reader: PdfReader,
) -> str:
    """
    Extract text from an already opened PDF reader.

    Works with:
    - local PDF files
    - PDFs loaded from S3
    """

    pages = []

    for page in reader.pages:
        text = page.extract_text()

        if text:
            pages.append(text)

    return "\n".join(pages)


def load_cv(
    key: str,
) -> str:
    """
    Load CV PDF through the storage layer and return extracted text.

    Example:
        key = "resume/Rohish_Resume.pdf"
    """

    pdf_bytes = storage.read_bytes(key)

    reader = PdfReader(
        BytesIO(pdf_bytes)
    )

    return extract_pdf_text(reader)


def parse_cv(text: str) -> ParsedCV:
    response = client.beta.chat.completions.parse(
        model="gpt-4o",
        temperature=0,
        seed=42,
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