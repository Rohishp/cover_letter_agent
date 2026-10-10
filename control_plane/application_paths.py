import re
import unicodedata
from datetime import date as date_type
from pathlib import Path


APPLICATIONS_ROOT = Path("output/applications")

MAX_COMPONENT_LENGTH = 40

_LEGAL_SUFFIXES = {"gmbh", "ag", "inc", "llc", "ltd", "co", "corp", "plc", "sa"}


def _strip_legal_suffix(name: str) -> str:
    words = name.split()

    while words and re.sub(r"[^a-z]", "", words[-1].lower()) in _LEGAL_SUFFIXES:
        words.pop()

    return " ".join(words) or name


def slugify_component(text: str, max_length: int = MAX_COMPONENT_LENGTH) -> str:
    """
    ASCII, case-preserving, punctuation/whitespace -> single hyphens,
    truncated to max_length. Case-preserving and separate from the
    lowercase fact-base IDs in cv/facts.py -- this is for human-readable
    folder names, not stable machine IDs.
    """

    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")

    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-")

    return slug[:max_length].strip("-")


def application_slug(
    company_name: str | None,
    job_title: str | None,
    run_date: date_type,
) -> str:
    """
    "<YYYY-MM-DD>_<Company>_<Role>", ASCII, hyphens within each
    component. Never raises -- falls back to unknown-company /
    unknown-role when the JD parser returned null for either.
    """

    company_slug = ""

    if company_name:
        company_slug = slugify_component(_strip_legal_suffix(company_name))

    if not company_slug:
        company_slug = "unknown-company"

    role_slug = slugify_component(job_title) if job_title else ""

    if not role_slug:
        role_slug = "unknown-role"

    return f"{run_date.strftime('%Y-%m-%d')}_{company_slug}_{role_slug}"


def resolve_application_dir(
    company_name: str | None,
    job_title: str | None,
    run_date: date_type,
    root: Path = APPLICATIONS_ROOT,
) -> Path:
    """
    A fresh, not-yet-existing directory for one application. Appends
    _2, _3, ... on collision rather than overwriting a prior run.
    """

    base_slug = application_slug(company_name, job_title, run_date)
    candidate = root / base_slug

    if not candidate.exists():
        return candidate

    suffix = 2

    while True:
        candidate = root / f"{base_slug}_{suffix}"

        if not candidate.exists():
            return candidate

        suffix += 1
