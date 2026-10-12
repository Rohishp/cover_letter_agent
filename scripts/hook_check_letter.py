"""PreToolUse hook: block a Write/Edit of output/applications/**/cover_letter.txt that fails the cheap letter checks.

Reads the hook JSON on stdin. Exit 0 allows, 2 blocks (failures on stderr), 1 means the hook itself could not run
(non-blocking). Only guards Claude's own tool calls, not files Python writes.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cv.facts import CVFacts, load_facts  # noqa: E402
from verify_application import FACTS_PATH, check_letter_text  # noqa: E402

APPLICATIONS = ROOT / "output" / "applications"


def _new_text(tool_name: str, tool_input: dict, path: Path) -> str | None:
    """The full letter text after the tool call, or None when it cannot be known (let the tool decide)."""

    if tool_name == "Write":
        content = tool_input.get("content")

        return content if isinstance(content, str) else None

    if tool_name == "Edit":
        old, new = tool_input.get("old_string"), tool_input.get("new_string")

        if not isinstance(old, str) or not isinstance(new, str) or not old or not path.is_file():
            return None

        try:
            current = path.read_text(encoding="utf-8")
        except (OSError, ValueError):
            return None

        if old not in current:
            return None

        return current.replace(old, new) if tool_input.get("replace_all") else current.replace(old, new, 1)

    return None


def _company(folder: Path) -> str | None:
    try:
        company = json.loads((folder / "run.json").read_text(encoding="utf-8")).get("company_name")
    except (OSError, ValueError, AttributeError):
        return None

    return company if isinstance(company, str) else None


def decide(payload: dict, facts: CVFacts) -> list[str]:
    """Failures that should block this tool call; [] allows it."""

    tool_input = payload.get("tool_input")
    file_path = tool_input.get("file_path") if isinstance(tool_input, dict) else None

    if payload.get("tool_name") not in ("Write", "Edit") or not isinstance(file_path, str):
        return []

    path = Path(file_path).resolve()

    if path.name != "cover_letter.txt" or not path.is_relative_to(APPLICATIONS.resolve()):
        return []

    text = _new_text(payload["tool_name"], tool_input, path)

    return [] if text is None else check_letter_text(text, facts, _company(path.parent))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        facts = load_facts(FACTS_PATH)
    except Exception as exc:  # no JSON or no fact base: report, do not block
        print(f"letter hook could not run: {type(exc).__name__}", file=sys.stderr)
        return 1

    failures = decide(payload, facts)

    if failures:
        print("Write blocked, cover letter fails checks:\n" + "\n".join(failures), file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
