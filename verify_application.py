import json
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from pydantic import ValidationError

from control_plane.application_paths import MAX_COMPONENT_LENGTH
from control_plane.cover_letter_containment import (
    check_fabricated_employer,
    check_fabricated_role_claim,
    check_hedge_disclosure,
    check_letter_structure,
    known_organisations,
    real_held_titles,
)
from cv.checks import convert_to_pdf
from cv.facts import CVFacts, load_facts
from models.cover_letter_schema import CoverLetterDraft, CoverLetterParagraph


# Shape produced by control_plane/application_paths.py (slug + optional _N).
_WORD = r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*"
FOLDER_RE = re.compile(rf"^(\d{{4}}-\d{{2}}-\d{{2}})_({_WORD})_({_WORD})(_\d+)?$")

APPLICATION_FILES = ("cover_letter.txt", "cv.docx", "jd.txt", "run.json")
DECLINED_FILES = ("jd.txt", "run.json")

PLACEHOLDER_RE = re.compile(r"\[[^\]\n]*\]|\{\{|\bTODO\b|<[A-Za-z _-]+>")
MAX_CV_PAGES = 2
FACTS_PATH = Path(__file__).resolve().parent / "input" / "cv_facts.yaml"
MAX_FRAGMENT = 60  # failure strings carry letter text; keep it short


def _valid_date(text: str) -> bool:
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return False

    return True


def _regular(path: Path) -> bool:
    """A real file, not a symlink: the verifier only reads files that live in the folder."""

    return path.is_file() and not path.is_symlink()


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

    if not _regular(path):
        return {}, []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, [f"run.json is not valid JSON: {_clip(str(exc))}"]

    if not isinstance(data, dict):
        return {}, ["run.json is not a JSON object"]

    status = data.get("status")

    if status not in ("completed", "declined"):
        return data, [f"run.json status is {_clip(repr(status))}, expected 'completed'"]

    return data, []


def _check_files(folder: Path, names: tuple[str, ...]) -> list[str]:
    failures = []

    for name in names:
        path = folder / name

        if path.is_symlink():
            failures.append(f"{name} is a symlink")
            continue

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


def _clip(text: str) -> str:
    return text if len(text) <= MAX_FRAGMENT else text[:MAX_FRAGMENT] + "..."


def _check_letter(path: Path, facts: CVFacts, company: str | None) -> list[str]:
    """Letter checks on the final text. Missing/unreadable files are reported by _check_files."""

    if not _regular(path):
        return []

    try:
        letter = path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return []

    return check_letter_text(letter, facts, company)


def check_letter_text(letter: str, facts: CVFacts, company: str | None) -> list[str]:
    """Cheap letter checks (checks 3 and 4) on letter text; also used by the PreToolUse hook."""

    organisations = known_organisations(facts, company)
    titles = real_held_titles(facts)
    # Only the final text exists, so the "factual paragraph" rule is the writer's, not checked here.
    draft = CoverLetterDraft(paragraphs=[CoverLetterParagraph(kind="factual", text=letter)])
    violations = [
        *(f"placeholder {_clip(m)}" for m in PLACEHOLDER_RE.findall(letter)),
        *(_clip(v) for v in check_letter_structure(letter, draft, facts)),
        *(f"hedge phrase {_clip(v)}" for v in check_hedge_disclosure(letter)),
        *(f"fabricated employer {_clip(v)}" for v in check_fabricated_employer(letter, organisations)),
        *(f"fabricated role claim {_clip(v)}" for v in check_fabricated_role_claim(letter, titles)),
    ]

    return [f"cover_letter.txt: {v}" for v in violations]


def _docx_text(path: Path) -> str:
    """Text of every paragraph in the body (nested tables included) and in headers/footers."""

    doc = Document(str(path))
    roots = [doc.element.body, *(part._element for s in doc.sections for part in (s.header, s.footer))]
    paragraphs = (p for root in roots for p in root.iter(qn("w:p")))

    return "\n".join("".join(t.text or "" for t in p.iter(qn("w:t"))) for p in paragraphs)


def _page_count(path: Path) -> tuple[int | None, str]:
    """Pages of the rendered docx, or (None, reason). Converts a copy so no PDF is left in the folder."""

    import pymupdf

    try:
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "cv.docx"
            shutil.copy(path, copy)
            pdf, detail = convert_to_pdf(copy)

            if pdf is None:
                return None, detail

            with pymupdf.open(str(pdf)) as document:
                return (document.page_count or None), detail
    except Exception as exc:  # a render failure must fail the check, not crash the verifier
        return None, f"render failed ({type(exc).__name__})"


def _check_cv(path: Path, check_pages: bool) -> list[str]:
    """No placeholders and at most MAX_CV_PAGES pages. Missing/empty files are reported by _check_files."""

    if not _regular(path):
        return []

    try:
        text = _docx_text(path)
    except Exception:  # python-docx raises several unrelated types on a corrupt package
        return ["cv.docx is unreadable"]

    found = dict.fromkeys(PLACEHOLDER_RE.findall(text))  # linked headers repeat; report each once
    failures = [f"cv.docx: placeholder {_clip(m)}" for m in found]

    if check_pages:
        pages, detail = _page_count(path)

        if pages is None:
            failures.append(f"cv.docx: page count not checked, {detail}")
        elif pages > MAX_CV_PAGES:
            failures.append(f"cv.docx: renders to {pages} pages, expected at most {MAX_CV_PAGES}")

    return failures


def verify_application(folder: Path, facts: CVFacts, *, check_pages: bool = True) -> list[str]:
    """Human-readable failures for one application folder; [] means verified.
    check_pages=False skips the docx-to-PDF render (slow, needs Word or LibreOffice)."""

    folder = Path(folder)
    data, run_failures = _read_run_json(folder)
    declined = data.get("status") == "declined"
    company = data.get("company_name")
    company = company if isinstance(company, str) else None
    failures = _check_name(folder) + run_failures
    failures += _check_files(folder, DECLINED_FILES if declined else APPLICATION_FILES)

    if not declined:
        failures += _check_letter(folder / "cover_letter.txt", facts, company)
        failures += _check_cv(folder / "cv.docx", check_pages)

    return failures


def _load_error(exc: Exception) -> str:
    """Describe a fact-base load error without echoing field values (they are real CV data)."""

    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc']))} {e['type']}" for e in exc.errors())

    return type(exc).__name__


def main(argv: list[str]) -> int:
    """0 verified, 2 failures (so a hook can block on it), 1 could not run."""

    args = argv[1:]
    facts_path = FACTS_PATH

    if len(args) == 3 and args[1] == "--facts":
        facts_path = Path(args[2])
        args = args[:1]

    if len(args) != 1:
        print("usage: python verify_application.py <application_folder> [--facts <cv_facts.yaml>]", file=sys.stderr)
        return 1

    try:
        facts = load_facts(facts_path)
    except Exception as exc:  # missing or invalid fact base: report, do not trace
        print(f"cannot load {facts_path.name}: {_load_error(exc)}", file=sys.stderr)
        return 1

    failures = verify_application(Path(args[0]), facts)

    for failure in failures:
        print(failure)

    if failures:
        return 2

    print("OK")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
