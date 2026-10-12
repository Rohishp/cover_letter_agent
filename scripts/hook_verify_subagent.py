"""Verify the application folders a sub-agent touched, when it tries to stop.

Two hook events share this script. PostToolUse (Write/Edit/Bash) records, per agent_id, each folder under
output/applications that a call names. SubagentStop runs verify_application on the recorded folders: exit 0 lets the
sub-agent stop, exit 2 keeps it working with the failures on stderr. (The sub-agent transcript is not written yet when
SubagentStop fires, so it cannot be used to find the folders.) The record is deleted once read. A second pass
(stop_hook_active) never blocks, so an unfixable failure cannot loop; a verifier error blocks once, so it is seen.
Only sees Claude's own tool calls.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.hook_check_letter import _redact, _target  # noqa: E402  (shared with the PreToolUse hook)

APPLICATIONS = ROOT / "output" / "applications"
STATE_DIR = ROOT / "output" / "hook_state"  # inside the gitignored, project-local output/
_BASH_PATH_RE = re.compile(r"output[\\/]+applications[\\/]+([^\\/\s\"'`;|&<>]+)", re.I)


def _folder_of(path: Path) -> Path | None:
    try:
        relative = path.resolve().relative_to(APPLICATIONS.resolve())
    except (ValueError, OSError):
        return None

    return APPLICATIONS / relative.parts[0] if len(relative.parts) > 1 else None


def touched_folders(payload: dict) -> list[Path]:
    """Application folders a Write/Edit/Bash tool call names."""

    tool_input = payload.get("tool_input")
    tool = payload.get("tool_name")

    if tool in ("Write", "Edit"):
        path = _target(payload)
        folder = _folder_of(path) if path else None

        return [folder] if folder else []

    command = tool_input.get("command") if isinstance(tool_input, dict) else None

    if tool == "Bash" and isinstance(command, str):
        names = dict.fromkeys(n for n in _BASH_PATH_RE.findall(command) if n not in (".", ".."))

        return [APPLICATIONS / n for n in names]

    return []


def _state_file(agent_id: str) -> Path:
    return STATE_DIR / (re.sub(r"[^A-Za-z0-9_-]", "_", agent_id) + ".txt")


def record(payload: dict) -> None:
    """PostToolUse: remember the folders this sub-agent touched. Main-session calls have no agent_id and are skipped."""

    agent_id, folders = payload.get("agent_id"), touched_folders(payload)

    if isinstance(agent_id, str) and agent_id and folders:
        STATE_DIR.mkdir(parents=True, exist_ok=True)

        with open(_state_file(agent_id), "a", encoding="utf-8") as handle:
            handle.writelines(folder.name + "\n" for folder in folders)


def decide(payload: dict, verify) -> list[str]:
    """SubagentStop: failures to hand back to the sub-agent; [] lets it stop. `verify(folder) -> list[str]`.
    Reads and deletes the agent's record, so a later or resumed run with the same id starts clean."""

    agent_id = payload.get("agent_id")
    state = _state_file(agent_id) if isinstance(agent_id, str) else None

    if state is None or not state.is_file():
        return []

    try:
        names = dict.fromkeys(state.read_text(encoding="utf-8").splitlines())
    finally:
        state.unlink(missing_ok=True)

    if payload.get("stop_hook_active"):
        return []

    failures = []

    for name in names:
        folder = APPLICATIONS / name

        if folder.is_dir():
            failures += [f"{name}: {f}" for f in verify(folder)]

    return failures


def _verify(folder: Path) -> list[str]:
    from cv.facts import load_facts
    from verify_application import FACTS_PATH, verify_application

    return verify_application(folder, load_facts(FACTS_PATH))


def main() -> int:
    try:
        payload = json.load(sys.stdin)

        if payload.get("hook_event_name") == "PostToolUse":
            record(payload)

            return 0
    except Exception as exc:  # unreadable payload or unwritable record: nothing to block on
        print(f"verify hook could not run: {type(exc).__name__}", file=sys.stderr)
        return 0

    try:
        failures = decide(payload, _verify)
    except Exception as exc:  # verifier or state error: block once so it is seen, never on the second pass
        if payload.get("stop_hook_active"):
            return 0

        failures = [f"verify hook failed ({type(exc).__name__}); report this instead of finishing"]

    if failures:
        print("verify_application failed; fix these before finishing:\n" + "\n".join(map(_redact, failures)), file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
