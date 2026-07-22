from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader
from io import BytesIO
import boto3
from models.cv_schema import ParsedCV

load_dotenv()
client = OpenAI()

S3_REGION = "eu-central-1"

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


def load_cv_from_s3(
    bucket: str,
    key: str,
) -> str:
    """
    Load CV PDF from S3 and return extracted text.

    Example:
        bucket = "cover-letter-agent"
        key = "resume/Rohish_Resume.pdf"
    """

    s3 = boto3.client(
        "s3",
        region_name=S3_REGION,
    )

    response = s3.get_object(
        Bucket=bucket,
        Key=key,
    )

    pdf_bytes = response["Body"].read()

    reader = PdfReader(
        BytesIO(pdf_bytes)
    )

    return extract_pdf_text(reader)


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