import json
import re
from datetime import datetime
from pathlib import Path

from control_plane.application_paths import MAX_COMPONENT_LENGTH
from cv.facts import CVFacts


# Shape produced by control_plane/application_paths.py (slug + optional _N).
_WORD = r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*"
FOLDER_RE = re.compile(rf"^(\d{{4}}-\d{{2}}-\d{{2}})_({_WORD})_({_WORD})(_\d+)?$")

APPLICATION_FILES = ("cover_letter.txt", "cv.docx", "jd.txt", "run.json")
DECLINED_FILES = ("jd.txt", "run.json")


def _valid_date(text: str) -> bool:
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return False

    return True


def _check_name(folder: Path) -> list[str]:
    match = FOLDER_RE.match(folder.name)

    if (
        match
        and _valid_date(match.group(1))
        and len(match.group(2)) <= MAX_COMPONENT_LENGTH
        and len(match.group(3)) <= MAX_COMPONENT_LENGTH
    ):
        return []

    return [f"folder name '{folder.name}' does not match <YYYY-MM-DD>_<Company>_<Role>[_N]"]


def _read_run_json(folder: Path) -> tuple[str | None, list[str]]:
    """(status, failures) for run.json. A missing file is reported by _check_files."""

    path = folder / "run.json"

    if not path.is_file():
        return None, []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, [f"run.json is not valid JSON: {exc}"]

    if not isinstance(data, dict):
        return None, ["run.json is not a JSON object"]

    status = data.get("status")
    status = status if isinstance(status, str) else None

    if status not in ("completed", "declined"):
        return status, [f"run.json status is {status!r}, expected 'completed'"]

    return status, []


def _check_files(folder: Path, names: tuple[str, ...]) -> list[str]:
    failures = []

    for name in names:
        path = folder / name

        if not path.is_file():
            failures.append(f"{name} is missing")
            continue

        try:
            if name.endswith((".txt", ".json")):
                empty = not path.read_text(encoding="utf-8").strip()
            else:
                empty = path.stat().st_size == 0
        except (OSError, ValueError):
            failures.append(f"{name} is unreadable")
            continue

        if empty:
            failures.append(f"{name} is empty")

    return failures


def verify_application(folder: Path, facts: CVFacts) -> list[str]:
    """Human-readable failures for one application folder; [] means verified.
    `facts` is unused until the letter checks (T02)."""

    folder = Path(folder)
    status, status_failures = _read_run_json(folder)
    names = DECLINED_FILES if status == "declined" else APPLICATION_FILES

    return _check_name(folder) + status_failures + _check_files(folder, names)
