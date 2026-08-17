import hashlib
import json

from control_plane import storage
from models.jd_schema import ParsedJD


JD_CACHE_PREFIX = "jd_cache"

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


def get_jd_cache_key(raw_jd: str) -> str:
    """
    S3 object key.
    """

    return (
        f"{JD_CACHE_PREFIX}/"
        f"{create_jd_cache_key(raw_jd)}.json"
    )


def load_cached_jd(raw_jd: str) -> ParsedJD | None:
    """
    Load a parsed JD from the cache.

    Returns None if no cache exists or the parser version changed.
    """

    key = get_jd_cache_key(raw_jd)

    json_string = storage.read_text(key)

    if json_string is None:
        return None

    payload = json.loads(json_string)

    if payload.get("parser_version") != JD_PARSER_VERSION:
        return None

    return ParsedJD(
        **payload["parsed_jd"]
    )


def save_cached_jd(
    raw_jd: str,
    parsed_jd: ParsedJD,
) -> str:
    """
    Save parsed JD into the cache.
    """

    key = get_jd_cache_key(raw_jd)

    payload = {
        "parser_version": JD_PARSER_VERSION,
        "cache_key": create_jd_cache_key(raw_jd),
        "parsed_jd": parsed_jd.model_dump(),
    }

    json_string = json.dumps(
        payload,
        indent=2,
        ensure_ascii=False,
        default=str,
    )

    return storage.write_text(key, json_string)