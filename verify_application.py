import json
import re
from datetime import datetime
from pathlib import Path

from cv.facts import CVFacts


# Shape produced by control_plane/application_paths.py (slug + optional _N).
FOLDER_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_[A-Za-z0-9-]+_[A-Za-z0-9-]+(_\d+)?$")

APPLICATION_FILES = ("cover_letter.txt", "cv.docx", "jd.txt", "run.json")
DECLINED_FILES = ("jd.txt", "run.json")


def _check_name(folder: Path) -> list[str]:
    match = FOLDER_RE.match(folder.name)

    if match:
        try:
            datetime.strptime(match.group(1), "%Y-%m-%d")
            return []
        except ValueError:
            pass

    return [f"folder name '{folder.name}' does not match <YYYY-MM-DD>_<Company>_<Role>[_N]"]


def _read_status(folder: Path) -> tuple[str | None, list[str]]:
    path = folder / "run.json"

    if not path.is_file():
        return None, []  # reported by the file check

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, [f"run.json is not valid JSON: {exc}"]

    if not isinstance(data, dict):
        return None, ["run.json is not a JSON object"]

    status = data.get("status")

    return (status if isinstance(status, str) else None), []


def _check_files(folder: Path, names: tuple[str, ...]) -> list[str]:
    failures = []

    for name in names:
        path = folder / name

        if not path.is_file():
            failures.append(f"{name} is missing")
        elif path.stat().st_size == 0:
            failures.append(f"{name} is empty")
        elif name.endswith((".txt", ".json")) and not path.read_text(encoding="utf-8").strip():
            failures.append(f"{name} is empty")

    return failures


def verify_application(folder: Path, facts: CVFacts) -> list[str]:
    """Human-readable failures for one application folder; [] means verified.
    `facts` is unused until the letter checks (T02)."""

    folder = Path(folder)
    failures = _check_name(folder)
    status, status_failures = _read_status(folder)
    failures += status_failures

    if status == "declined":
        return failures + _check_files(folder, DECLINED_FILES)

    if not status_failures and (folder / "run.json").is_file() and status != "completed":
        failures.append(f"run.json status is {status!r}, expected 'completed'")

    return failures + _check_files(folder, APPLICATION_FILES)
