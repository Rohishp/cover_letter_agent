"""PreToolUse hook decision function: block bad letter writes under output/applications, allow everything else."""
import pytest

from helpers import GOOD_LETTER, make_folder
from scripts import hook_check_letter as hook


@pytest.fixture
def apps(tmp_path, monkeypatch):
    root = tmp_path / "applications"
    root.mkdir()
    monkeypatch.setattr(hook, "APPLICATIONS", root)

    return root


def write(path, content):
    return {"tool_name": "Write", "tool_input": {"file_path": str(path), "content": content}}


def test_clean_letter_allowed(apps, facts):
    folder = make_folder(apps)

    assert hook.decide(write(folder / "cover_letter.txt", GOOD_LETTER), facts) == []


def test_bad_letter_blocked(apps, facts):
    folder = make_folder(apps)
    bad = GOOD_LETTER.replace("Acme Corp.", "Acme Corp. [insert company]")

    assert any("placeholder" in f for f in hook.decide(write(folder / "cover_letter.txt", bad), facts))


def test_fabricated_employer_blocked(apps, facts):
    folder = make_folder(apps)
    bad = GOOD_LETTER.replace("I did thing one at Acme Corp.", "At Fakecorp, I did it.")

    assert hook.decide(write(folder / "cover_letter.txt", bad), facts)


def test_edit_checks_resulting_text(apps, facts):
    folder = make_folder(apps)
    path = folder / "cover_letter.txt"
    edit = {"tool_name": "Edit", "tool_input": {"file_path": str(path), "old_string": "thing one", "new_string": "TODO"}}

    assert any("placeholder" in f for f in hook.decide(edit, facts))


def test_edit_with_missing_old_string_left_to_the_tool(apps, facts):
    folder = make_folder(apps)
    edit = {"tool_name": "Edit", "tool_input": {"file_path": str(folder / "cover_letter.txt"), "old_string": "nope", "new_string": "[x]"}}

    assert hook.decide(edit, facts) == []


@pytest.mark.parametrize("name", ["jd.txt", "run.json", "notes.txt"])
def test_other_files_in_application_ignored(apps, facts, name):
    folder = make_folder(apps)

    assert hook.decide(write(folder / name, "TODO [x]"), facts) == []


def test_letter_outside_applications_ignored(apps, facts, tmp_path):
    assert hook.decide(write(tmp_path / "cover_letter.txt", "TODO [x]"), facts) == []


def test_other_tools_ignored(apps, facts):
    folder = make_folder(apps)
    payload = {"tool_name": "Read", "tool_input": {"file_path": str(folder / "cover_letter.txt")}}

    assert hook.decide(payload, facts) == []


def test_malformed_payload_allowed(facts):
    assert hook.decide({}, facts) == []
    assert hook.decide({"tool_name": "Write", "tool_input": "x"}, facts) == []
