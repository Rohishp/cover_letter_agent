import hashlib
import json
from pathlib import Path

from models.jd_schema import ParsedJD


JD_CACHE_DIR = Path("output/jd_cache")

JD_PARSER_VERSION = "v2_application_documents"


def normalize_jd_text(raw_jd: str) -> str:
    """
    Normalize irrelevant whitespace before hashing.
    """

    return "\n".join(
        line.strip()
        for line in raw_jd.strip().splitlines()
        if line.strip()
    )


def create_jd_cache_key(raw_jd: str) -> str:
    normalized = normalize_jd_text(raw_jd)

    cache_input = (
        f"parser_version={JD_PARSER_VERSION}\n"
        f"{normalized}"
    )

    return hashlib.sha256(
        cache_input.encode("utf-8")
    ).hexdigest()


def get_jd_cache_path(raw_jd: str) -> Path:
    return JD_CACHE_DIR / f"{create_jd_cache_key(raw_jd)}.json"


def load_cached_jd(raw_jd: str) -> ParsedJD | None:
    path = get_jd_cache_path(raw_jd)

    if not path.exists():
        return None

    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)

    if data.get("parser_version") != JD_PARSER_VERSION:
        return None

    return ParsedJD(**data["parsed_jd"])


def save_cached_jd(
    raw_jd: str,
    parsed_jd: ParsedJD,
) -> Path:
    JD_CACHE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = get_jd_cache_path(raw_jd)

    payload = {
        "parser_version": JD_PARSER_VERSION,
        "cache_key": create_jd_cache_key(raw_jd),
        "parsed_jd": parsed_jd.model_dump(),
    }

    with open(path, "w", encoding="utf-8") as file:
        json.dump(
            payload,
            file,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    return path