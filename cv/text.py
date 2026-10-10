import re


def collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
