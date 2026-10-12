import json
import re
from datetime import datetime
from pathlib import Path

from agents.cover_letter_writer import _real_employers, _real_held_titles, _real_institutions
from control_plane.application_paths import MAX_COMPONENT_LENGTH
from control_plane.cover_letter_containment import (
    check_fabricated_employer,
    check_fabricated_role_claim,
    check_hedge_disclosure,
    check_letter_structure,
)
from cv.facts import CVFacts
from models.cover_letter_schema import CoverLetterDraft, CoverLetterParagraph


# Shape produced by control_plane/application_paths.py (slug + optional _N).
_WORD = r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*"
FOLDER_RE = re.compile(rf"^(\d{{4}}-\d{{2}}-\d{{2}})_({_WORD})_({_WORD})(_\d+)?$")

APPLICATION_FILES = ("cover_letter.txt", "cv.docx", "jd.txt", "run.json")
DECLINED_FILES = ("jd.txt", "run.json")

PLACEHOLDER_RE = re.compile(r"\[[^\]\n]*\]|\{\{|\bTODO\b|<[A-Za-z][^>\n]*>")


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


def _read_run_json(folder: Path) -> tuple[dict, list[str]]:
    """(data, failures) for run.json. A missing file is reported by _check_files."""

    path = folder / "run.json"

    if not path.is_file():
        return {}, []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, [f"run.json is not valid JSON: {exc}"]

    if not isinstance(data, dict):
        return {}, ["run.json is not a JSON object"]

    status = data.get("status")

    if status not in ("completed", "declined"):
        return data, [f"run.json status is {status!r}, expected 'completed'"]

    return data, []


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


def _check_letter(path: Path, facts: CVFacts, company: str | None) -> list[str]:
    """Letter checks on the final text. Missing/unreadable files are reported by _check_files."""

    try:
        letter = path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return []

    organisations = [*_real_employers(facts), *_real_institutions(facts), *([company] if company else [])]
    # Only the final text exists, so the "factual paragraph" rule is the writer's, not checked here.
    draft = CoverLetterDraft(paragraphs=[CoverLetterParagraph(kind="factual", text=letter)])
    violations = [
        *(f"placeholder {m!r}" for m in PLACEHOLDER_RE.findall(letter)),
        *check_letter_structure(letter, draft, facts),
        *(f"hedge phrase {v!r}" for v in check_hedge_disclosure(letter)),
        *(f"fabricated employer {v!r}" for v in check_fabricated_employer(letter, organisations)),
        *(f"fabricated role claim {v!r}" for v in check_fabricated_role_claim(letter, _real_held_titles(facts))),
    ]

    return [f"cover_letter.txt: {v}" for v in violations]


def verify_application(folder: Path, facts: CVFacts) -> list[str]:
    """Human-readable failures for one application folder; [] means verified."""

    folder = Path(folder)
    data, run_failures = _read_run_json(folder)
    declined = data.get("status") == "declined"
    company = data.get("company_name")
    failures = _check_name(folder) + run_failures
    failures += _check_files(folder, DECLINED_FILES if declined else APPLICATION_FILES)

    if not declined:
        failures += _check_letter(folder / "cover_letter.txt", facts, company if isinstance(company, str) else None)

    return failures
