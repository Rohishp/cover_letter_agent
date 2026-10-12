"""Verify the application folders a sub-agent touched, when it tries to stop.

Two hook events share this script. PostToolUse (Write/Edit/Bash) records, per agent_id, each folder under
output/applications that a call names. SubagentStop runs verify_application on the recorded folders: exit 0 lets the
sub-agent stop, exit 2 keeps it working with the failures on stderr. (The sub-agent transcript is not written yet when
SubagentStop fires, so it cannot be used to find the folders.) A hook error never blocks, and a second pass
(stop_hook_active) never blocks, so an unfixable failure cannot loop. Only sees Claude's own tool calls.
"""
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

APPLICATIONS = ROOT / "output" / "applications"
STATE_DIR = Path(tempfile.gettempdir()) / "cover_letter_agent_touched"
_BASH_PATH_RE = re.compile(r"output[\\/]+applications[\\/]+([^\\/\s\"'`;|&<>]+)", re.I)


def _folder_of(path: Path) -> Path | None:
    try:
        relative = path.resolve().relative_to(APPLICATIONS.resolve())
    except (ValueError, OSError):
        return None

    return APPLICATIONS / relative.parts[0] if len(relative.parts) > 1 else None


def touched_folder(payload: dict) -> Path | None:
    """The application folder a Write/Edit/Bash tool call names, if any."""

    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    file_path, command = tool_input.get("file_path"), tool_input.get("command")

    if isinstance(file_path, str) and payload.get("tool_name") in ("Write", "Edit"):
        path = Path(file_path)
        cwd = payload.get("cwd")

        return _folder_of(path if path.is_absolute() else Path(cwd if isinstance(cwd, str) else ROOT) / path)

    if isinstance(command, str) and payload.get("tool_name") == "Bash":
        names = _BASH_PATH_RE.findall(command)

        return APPLICATIONS / names[0] if names else None

    return None


def _state_file(agent_id: str) -> Path:
    return STATE_DIR / (re.sub(r"[^A-Za-z0-9_-]", "_", agent_id) + ".txt")


def record(payload: dict) -> None:
    """PostToolUse: remember the folder this sub-agent touched. Main-session calls have no agent_id and are skipped."""

    agent_id, folder = payload.get("agent_id"), touched_folder(payload)

    if isinstance(agent_id, str) and agent_id and folder is not None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)

        with open(_state_file(agent_id), "a", encoding="utf-8") as handle:
            handle.write(folder.name + "\n")


def decide(payload: dict, verify) -> list[str]:
    """SubagentStop: failures to hand back to the sub-agent; [] lets it stop. `verify(folder) -> list[str]`."""

    agent_id = payload.get("agent_id")

    if payload.get("stop_hook_active") or not isinstance(agent_id, str) or not _state_file(agent_id).is_file():
        return []

    names = dict.fromkeys(_state_file(agent_id).read_text(encoding="utf-8").split())
    failures = []

    for name in names:
        folder = APPLICATIONS / name

        if folder.is_dir():
            failures += [f"{name}: {f}" for f in verify(folder)]

    return failures


def main() -> int:
    try:
        payload = json.load(sys.stdin)

        if payload.get("hook_event_name") == "PostToolUse":
            record(payload)

            return 0

        from cv.facts import load_facts
        from verify_application import FACTS_PATH, verify_application

        facts = load_facts(FACTS_PATH)
        failures = decide(payload, lambda folder: verify_application(folder, facts))
    except Exception as exc:  # a hook that cannot run must not trap the sub-agent
        print(f"verify hook could not run: {type(exc).__name__}", file=sys.stderr)
        return 0

    if failures:
        print("verify_application failed; fix these before finishing:\n" + "\n".join(failures), file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
