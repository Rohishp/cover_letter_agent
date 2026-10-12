"""PreToolUse hook: guard output/applications/** against bad cover letters.

Blocks a Write/Edit of cover_letter.txt that fails the cheap letter checks, any Write/Edit of run.json (Python owns
it), and Bash commands that write cover_letter.txt (heuristic). Reads the hook JSON on stdin. Exit 0 allows, 2 blocks
(reason on stderr). Once a call targets a guarded file, any hook error also blocks (fail closed); for other calls
the hook never blocks. Only guards Claude's own tool calls, not files Python writes.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

APPLICATIONS = ROOT / "output" / "applications"
LETTER = "cover_letter.txt"
# Bash is only judged when the command names the letter and does something that can write it.
_BASH_WRITE_RE = re.compile(r">|\b(tee|sed\s+-\S*i|cp|mv|dd|install|Set-Content|Add-Content|Out-File)\b|\bpython\S*\s+-c\b", re.I)


def _canonical_name(name: str) -> str:
    """Lower-case, without NTFS alternate-stream suffix or trailing dots/spaces (all name the same file)."""

    return name.split(":")[0].rstrip(". ").lower()


def _target(payload: dict) -> Path | None:
    tool_input = payload.get("tool_input")
    file_path = tool_input.get("file_path") if isinstance(tool_input, dict) else None

    if not isinstance(file_path, str):
        return None

    path = Path(file_path)

    if not path.is_absolute():
        cwd = payload.get("cwd")
        path = Path(cwd if isinstance(cwd, str) else ROOT) / path

    return path.resolve()


def guarded_kind(payload: dict) -> str | None:
    """'letter', 'run_json', 'bash' or None for what this call touches."""

    tool = payload.get("tool_name")

    if tool == "Bash":
        command = (payload.get("tool_input") or {}).get("command")

        if isinstance(command, str) and LETTER in command.lower() and _BASH_WRITE_RE.search(command):
            return "bash"

        return None

    if tool not in ("Write", "Edit"):
        return None

    path = _target(payload)

    if path is None or not path.is_relative_to(APPLICATIONS.resolve()):
        return None

    name = _canonical_name(path.name)

    return "letter" if name == LETTER else "run_json" if name == "run.json" else None


def _new_text(tool_name: str, tool_input: dict, path: Path) -> str | None:
    """The full letter text after the tool call, or None when it cannot be known (let the tool decide)."""

    if tool_name == "Write":
        content = tool_input.get("content")

        return content if isinstance(content, str) else None

    old, new = tool_input.get("old_string"), tool_input.get("new_string")

    if not isinstance(old, str) or not isinstance(new, str) or not old or not path.is_file():
        return None

    try:
        with open(path, encoding="utf-8", newline="") as handle:  # newline="" keeps CRLF so old_string matches raw
            current = handle.read()
    except (OSError, ValueError):
        return None

    if old not in current and "\r\n" in current:
        old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")

    if old not in current:
        return None

    return current.replace(old, new) if tool_input.get("replace_all") else current.replace(old, new, 1)


def _company(folder: Path) -> str | None:
    run_json = folder / "run.json"

    try:
        if run_json.is_symlink():
            return None

        company = json.loads(run_json.read_text(encoding="utf-8")).get("company_name")
    except (OSError, ValueError, AttributeError):
        return None

    return company if isinstance(company, str) else None


def decide(payload: dict, facts) -> list[str]:
    """Failures that should block this tool call; [] allows it. `facts` is a cv.facts.CVFacts."""

    kind = guarded_kind(payload)

    if kind == "run_json":
        return ["run.json is written by the pipeline, not by tool calls"]

    if kind == "bash":
        return [f"Bash command writes {LETTER}; write it with the Write tool so it is checked"]

    if kind != "letter":
        return []

    from verify_application import check_letter_text

    path = _target(payload)
    text = _new_text(payload["tool_name"], payload["tool_input"], path)

    return [] if text is None else check_letter_text(text, facts, _company(path.parent))


def _redact(failure: str) -> str:
    """The structure check quotes the candidate's full name; keep it out of hook output."""

    return re.sub(r"(exact name ).*", r"\1<hidden>", failure)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        kind = guarded_kind(payload)
    except Exception as exc:  # unreadable payload: cannot tell what is being touched
        print(f"letter hook could not run: {type(exc).__name__}", file=sys.stderr)
        return 1

    try:
        facts = None

        if kind == "letter":
            from verify_application import FACTS_PATH
            from cv.facts import load_facts

            facts = load_facts(FACTS_PATH)

        failures = decide(payload, facts)
    except Exception as exc:  # a guarded call must not slip through on a hook bug
        failures = [f"letter hook failed ({type(exc).__name__}); not writing unchecked"] if kind else []

    if failures:
        print(f"{payload['tool_name']} blocked:\n" + "\n".join(_redact(f) for f in failures), file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
