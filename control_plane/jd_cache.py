import hashlib
import json

import boto3
from botocore.exceptions import ClientError

from models.jd_schema import ParsedJD


S3_BUCKET = "cover-letter-agent"
S3_REGION = "eu-central-1"

JD_CACHE_PREFIX = "jd_cache"

JD_PARSER_VERSION = "v2_application_documents"


def get_s3():
    return boto3.client(
        "s3",
        region_name=S3_REGION,
    )


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
    Load a parsed JD from S3 cache.

    Returns None if no cache exists or the parser version changed.
    """

    s3 = get_s3()

    key = get_jd_cache_key(raw_jd)

    try:
        response = s3.get_object(
            Bucket=S3_BUCKET,
            Key=key,
        )

    except ClientError as e:

        error_code = e.response["Error"]["Code"]

        if error_code in (
            "NoSuchKey",
            "404",
        ):
            return None

        raise

    payload = json.loads(
        response["Body"]
        .read()
        .decode("utf-8")
    )

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
    Save parsed JD into S3 cache.
    """

    s3 = get_s3()

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

    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json_string.encode("utf-8"),
    )

    return key