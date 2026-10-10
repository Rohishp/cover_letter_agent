import os
from pathlib import Path


def _local_root() -> Path:
    return Path(os.environ.get("LOCAL_DATA_DIR", "data"))


def _local_path(key: str) -> Path:
    return _local_root() / key


def read_bytes(key: str) -> bytes:
    return _local_path(key).read_bytes()


def read_text(key: str) -> str | None:
    path = _local_path(key)

    if not path.exists():
        return None

    return path.read_text(encoding="utf-8")


def write_text(key: str, text: str) -> str:
    path = _local_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return key


def list_keys(prefix: str) -> list[str]:
    root = _local_root()

    if not root.exists():
        return []

    return sorted(
        rel
        for path in root.rglob("*")
        if path.is_file() and (rel := path.relative_to(root).as_posix()).startswith(prefix)
    )
