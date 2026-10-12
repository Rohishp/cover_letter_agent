"""T04 spec tests: PreToolUse hook (Write|Edit|Bash) guarding output/applications/**; exit 2 with failures on stderr."""
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from helpers import GOOD_LETTER, make_folder
from scripts import hook_check_letter as hook

ROOT = Path(__file__).resolve().parent.parent
HOOK_ENTRY = "hook_check_letter.py"


@pytest.fixture
def apps(tmp_path, monkeypatch):
    root = tmp_path / "applications"
    root.mkdir()
    monkeypatch.setattr(hook, "APPLICATIONS", root)

    return root


@pytest.fixture
def facts_file(facts, tmp_path, monkeypatch):
    import verify_application

    path = tmp_path / "cv_facts.yaml"
    path.write_text(yaml.safe_dump(facts.model_dump(mode="json")), encoding="utf-8")
    monkeypatch.setattr(verify_application, "FACTS_PATH", path)

    return path


@pytest.fixture
def broken_facts(tmp_path, monkeypatch):
    """A facts file the hook cannot load, to force a hook error."""
    import verify_application

    path = tmp_path / "missing_facts.yaml"
    monkeypatch.setattr(verify_application, "FACTS_PATH", path)

    return path


def write(path, content):
    return {"tool_name": "Write", "tool_input": {"file_path": str(path), "content": content}}


def edit(path, old, new):
    return {"tool_name": "Edit", "tool_input": {"file_path": str(path), "old_string": old, "new_string": new}}


def bash(command):
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def run_main(monkeypatch, capsys, data):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(data)))
    code = hook.main()

    return code, capsys.readouterr().err


def swap(old, new):
    assert old in GOOD_LETTER
    return GOOD_LETTER.replace(old, new)


FIRST = "I did thing one at Acme Corp."
BAD_LETTERS = {
    "placeholder": swap(FIRST, FIRST + " TODO [insert company]"),
    "hedge": swap(FIRST, FIRST + " While I have not worked with Azure, I learn fast."),
    "fabricated employer": swap(FIRST, FIRST + "\n\nAt Fakecorp, I led the team."),
    "fabricated role": swap(FIRST, FIRST + "\n\nMy role as Quantum Wizard involved spells."),
}
STRUCTURE_BAD = {
    "no-greeting": swap("Dear team,\n\n", ""),
    "no-closing": swap("Best regards,\n", ""),
    "wrong-name": swap("Test Person", "Someone Else"),
}


# Scope: settings entry with matcher Write|Edit|Bash
def test_settings_registers_hook_with_write_edit_bash_matcher():
    entries = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    ours = [e for e in entries if any(HOOK_ENTRY in h.get("command", "") for h in e["hooks"])]

    assert ours and (ROOT / "scripts" / HOOK_ENTRY).is_file()
    assert any({"Write", "Edit", "Bash"} <= set(e["matcher"].split("|")) for e in ours)


# Scope: clean write not blocked
def test_clean_write_allowed(apps, facts):
    folder = make_folder(apps)

    assert hook.decide(write(folder / "cover_letter.txt", GOOD_LETTER), facts) == []


# Scope: each named cheap check blocks
@pytest.mark.parametrize("kind", list(BAD_LETTERS))
def test_cheap_check_blocks_write(apps, facts, kind):
    folder = make_folder(apps)
    failures = hook.decide(write(folder / "cover_letter.txt", BAD_LETTERS[kind]), facts)

    assert failures and kind in " ".join(failures).lower()


@pytest.mark.parametrize("kind", list(STRUCTURE_BAD))
def test_structure_check_blocks_write(apps, facts, kind):
    folder = make_folder(apps)

    assert hook.decide(write(folder / "cover_letter.txt", STRUCTURE_BAD[kind]), facts)


def test_real_employer_and_held_role_claims_allowed(apps, facts):
    folder = make_folder(apps)
    letter = swap(FIRST, FIRST + "\n\nAt Beta Inc, I helped.\n\nMy role as Senior Thing Doer involved things.")

    assert hook.decide(write(folder / "cover_letter.txt", letter), facts) == []


# Scope: for Edit, the text after the edit is checked
@pytest.mark.parametrize("new", ["TODO", "I lack Azure experience", "thing one at Acme Corp.\n\nAt Fakecorp, I led the team"])
def test_edit_that_makes_letter_bad_is_blocked(apps, facts, new):
    folder = make_folder(apps)
    path = folder / "cover_letter.txt"

    assert hook.decide(edit(path, "thing one", new), facts)


def test_clean_edit_allowed(apps, facts):
    folder = make_folder(apps)

    assert hook.decide(edit(folder / "cover_letter.txt", "thing one", "thing two"), facts) == []


def test_edit_checks_post_edit_text_not_the_file_on_disk(apps, facts):
    folder = make_folder(apps)
    path = folder / "cover_letter.txt"
    path.write_text(BAD_LETTERS["placeholder"], encoding="utf-8")

    # The edit removes the placeholder: the resulting text is clean, so it is allowed.
    assert hook.decide(edit(path, " TODO [insert company]", ""), facts) == []


# Scope: an Edit leaving a partial letter can be blocked
def test_edit_leaving_partial_letter_blocked(apps, facts):
    folder = make_folder(apps)
    path = folder / "cover_letter.txt"
    partial_old = "I did thing one at Acme Corp.\n\nBest regards,\nTest Person"

    assert partial_old in GOOD_LETTER
    assert hook.decide(edit(path, partial_old, "I did thing one."), facts)


# Scope: run.json Write/Edit blocked
@pytest.mark.parametrize("tool", ["Write", "Edit"])
def test_run_json_write_or_edit_blocked(apps, facts, tool):
    folder = make_folder(apps)
    path = folder / "run.json"
    data = write(path, "{}") if tool == "Write" else edit(path, "completed", "declined")

    assert hook.decide(data, facts)


def test_run_json_outside_applications_not_blocked(apps, facts, tmp_path):
    assert hook.decide(write(tmp_path / "run.json", "{}"), facts) == []


# Scope: Bash blocked only when naming cover_letter.txt with a write operator
@pytest.mark.parametrize(
    "command",
    [
        "echo hi > output/applications/2026-08-17_Acme_Engineer/cover_letter.txt",
        "echo hi >> output/applications/2026-08-17_Acme_Engineer/cover_letter.txt",
        "echo hi | tee output/applications/2026-08-17_Acme_Engineer/cover_letter.txt",
        "sed -i s/a/b/ output/applications/2026-08-17_Acme_Engineer/cover_letter.txt",
        "Set-Content output/applications/2026-08-17_Acme_Engineer/cover_letter.txt -Value hi",
    ],
)
def test_bash_write_to_letter_blocked(apps, facts, command):
    assert hook.decide(bash(command), facts)


@pytest.mark.parametrize(
    "command",
    [
        "cat output/applications/2026-08-17_Acme_Engineer/cover_letter.txt",
        "echo hi > notes.txt",
        "ls output/applications",
        "python apply.py input/jd_current.txt",
    ],
)
def test_bash_without_letter_and_write_operator_not_blocked(apps, facts, command):
    assert hook.decide(bash(command), facts) == []


# Scope: other files, and paths outside output/applications, are not checked
@pytest.mark.parametrize("name", ["jd.txt", "notes.txt", "cv.docx"])
def test_other_files_in_application_folder_unchecked(apps, facts, name):
    folder = make_folder(apps)

    assert hook.decide(write(folder / name, "TODO [insert company] I lack everything"), facts) == []


def test_letter_outside_applications_unchecked(apps, facts, tmp_path):
    assert hook.decide(write(tmp_path / "cover_letter.txt", "TODO [x]"), facts) == []


def test_other_tools_not_blocked(apps, facts):
    folder = make_folder(apps)

    assert hook.decide({"tool_name": "Read", "tool_input": {"file_path": str(folder / "cover_letter.txt")}}, facts) == []


# Scope: exit 2 with the failures on stderr
def test_main_exit_2_failures_on_stderr_for_bad_letter(apps, facts_file, monkeypatch, capsys):
    folder = make_folder(apps)
    code, err = run_main(monkeypatch, capsys, write(folder / "cover_letter.txt", BAD_LETTERS["placeholder"]))

    assert code == 2 and "placeholder" in err.lower()


def test_main_exit_2_for_run_json_and_bash_writes(apps, facts_file, monkeypatch, capsys):
    folder = make_folder(apps)

    assert run_main(monkeypatch, capsys, write(folder / "run.json", "{}"))[0] == 2
    assert run_main(monkeypatch, capsys, bash("echo hi > cover_letter.txt"))[0] == 2


def test_main_exit_0_for_clean_write(apps, facts_file, monkeypatch, capsys):
    folder = make_folder(apps)

    assert run_main(monkeypatch, capsys, write(folder / "cover_letter.txt", GOOD_LETTER)) == (0, "")


# Scope: a hook error on a guarded call blocks; other calls are never blocked
def test_hook_error_on_guarded_letter_write_fails_closed(apps, broken_facts, monkeypatch, capsys):
    folder = make_folder(apps)
    code, err = run_main(monkeypatch, capsys, write(folder / "cover_letter.txt", GOOD_LETTER))

    assert code == 2 and err.strip()


def test_hook_error_never_blocks_unguarded_calls(apps, broken_facts, monkeypatch, capsys):
    folder = make_folder(apps)

    assert run_main(monkeypatch, capsys, write(folder / "notes.txt", "TODO"))[0] == 0
    assert run_main(monkeypatch, capsys, bash("ls"))[0] == 0
    assert run_main(monkeypatch, capsys, {"tool_name": "Read", "tool_input": {"file_path": "x"}})[0] == 0


# Real-process check: stdin JSON in, exit code out
def run_script(data):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / HOOK_ENTRY)],
        input=json.dumps(data), capture_output=True, text=True, timeout=60,
    )


def test_script_subprocess_blocks_bad_letter_with_exit_2_and_stderr():
    path = ROOT / "output" / "applications" / "2026-08-17_Acme_Engineer" / "cover_letter.txt"
    result = run_script(write(path, "TODO [insert company]"))

    assert result.returncode == 2 and result.stderr.strip()


def test_script_subprocess_allows_unguarded_calls():
    notes = ROOT / "output" / "applications" / "x" / "notes.txt"

    assert run_script(write(notes, "TODO [x]")).returncode == 0
    assert run_script(bash("ls")).returncode == 0
