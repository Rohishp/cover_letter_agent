"""PreToolUse hook: block bad letter writes under output/applications, allow everything else."""
import io
import json

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


def edit(path, old, new, **extra):
    return {"tool_name": "Edit", "tool_input": {"file_path": str(path), "old_string": old, "new_string": new, **extra}}


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


def test_company_from_run_json_is_allowed_as_employer(apps, facts):
    folder = make_folder(apps)
    letter = GOOD_LETTER.replace("I did thing one at Acme Corp.", "I did thing one at Acme Corp.\n\nAt Newco, I would help.")
    path = folder / "cover_letter.txt"

    assert hook.decide(write(path, letter), facts)

    (folder / "run.json").write_text(json.dumps({"status": "completed", "company_name": "Newco"}), encoding="utf-8")

    assert hook.decide(write(path, letter), facts) == []


def test_edit_checks_resulting_text(apps, facts):
    folder = make_folder(apps)

    assert any("placeholder" in f for f in hook.decide(edit(folder / "cover_letter.txt", "thing one", "TODO"), facts))


def test_clean_edit_allowed(apps, facts):
    folder = make_folder(apps)

    assert hook.decide(edit(folder / "cover_letter.txt", "thing one", "thing two"), facts) == []


def test_edit_replace_all(apps, facts):
    folder = make_folder(apps)
    path = folder / "cover_letter.txt"
    path.write_text(GOOD_LETTER.replace("Dear team,", "Dear team, thing one"), encoding="utf-8")

    assert hook.decide(edit(path, "thing one", "TODO", replace_all=True), facts)
    assert hook.decide(edit(path, "nothing like this", "TODO", replace_all=True), facts) == []


def test_edit_on_crlf_file_matches_raw_text(apps, facts):
    folder = make_folder(apps)
    path = folder / "cover_letter.txt"
    path.write_bytes(GOOD_LETTER.replace("\n", "\r\n").encode())

    assert any("placeholder" in f for f in hook.decide(edit(path, "Acme Corp.\n\nBest", "TODO\n\nBest"), facts))


def test_edit_with_missing_old_string_left_to_the_tool(apps, facts):
    folder = make_folder(apps)

    assert hook.decide(edit(folder / "cover_letter.txt", "nope", "[x]"), facts) == []


@pytest.mark.parametrize("name", ["Cover_Letter.txt", "cover_letter.txt.", "cover_letter.txt::$DATA"])
def test_letter_name_variants_are_still_the_letter(apps, facts, name):
    folder = make_folder(apps)

    assert hook.decide(write(folder / name, "TODO [x]"), facts)


@pytest.mark.parametrize("name", ["jd.txt", "notes.txt"])
def test_other_files_in_application_ignored(apps, facts, name):
    folder = make_folder(apps)

    assert hook.decide(write(folder / name, "TODO [x]"), facts) == []


def test_run_json_write_blocked(apps, facts):
    folder = make_folder(apps)

    assert hook.decide(write(folder / "run.json", "{}"), facts)
    assert hook.decide(edit(folder / "RUN.JSON", "a", "b"), facts)


def test_letter_outside_applications_ignored(apps, facts, tmp_path):
    assert hook.decide(write(tmp_path / "cover_letter.txt", "TODO [x]"), facts) == []


def test_dotdot_traversal_out_of_applications_ignored(apps, facts, tmp_path):
    folder = make_folder(apps)

    assert hook.decide(write(folder / ".." / ".." / "cover_letter.txt", "TODO [x]"), facts) == []


def test_dotdot_traversal_into_applications_is_checked(apps, facts, tmp_path):
    folder = make_folder(apps)
    sneaky = tmp_path / "x" / ".." / "applications" / folder.name / "cover_letter.txt"

    assert hook.decide(write(sneaky, "TODO [x]"), facts)


def test_relative_path_resolved_against_payload_cwd(apps, facts, tmp_path):
    folder = make_folder(apps)
    payload = {"tool_name": "Write", "cwd": str(folder), "tool_input": {"file_path": "cover_letter.txt", "content": "TODO"}}

    assert hook.decide(payload, facts)


@pytest.mark.parametrize(
    "command, blocked",
    [
        ("echo hi > output/applications/x/cover_letter.txt", True),
        ("sed -i s/a/b/ output/applications/x/cover_letter.txt", True),
        ("Set-Content output/applications/x/cover_letter.txt hi", True),
        ("cat output/applications/x/cover_letter.txt", False),
        ("python verify_application.py output/applications/x 2>&1", False),
        ("echo hi > notes.txt", False),
    ],
)
def test_bash_writes_to_the_letter_blocked(apps, facts, command, blocked):
    assert bool(hook.decide({"tool_name": "Bash", "tool_input": {"command": command}}, facts)) is blocked


def test_other_tools_ignored(apps, facts):
    folder = make_folder(apps)
    payload = {"tool_name": "Read", "tool_input": {"file_path": str(folder / "cover_letter.txt")}}

    assert hook.decide(payload, facts) == []


def test_malformed_payload_allowed(facts):
    assert hook.decide({}, facts) == []
    assert hook.decide({"tool_name": "Write", "tool_input": "x"}, facts) == []
    assert hook.decide({"tool_name": "Bash", "tool_input": None}, facts) == []


def run_main(monkeypatch, capsys, payload):
    monkeypatch.setattr("sys.stdin", io.StringIO(payload if isinstance(payload, str) else json.dumps(payload)))
    code = hook.main()

    return code, capsys.readouterr().err


def test_main_exit_codes(apps, facts, monkeypatch, capsys, tmp_path):
    import verify_application
    import yaml

    facts_file = tmp_path / "cv_facts.yaml"
    facts_file.write_text(yaml.safe_dump(facts.model_dump(mode="json")), encoding="utf-8")
    monkeypatch.setattr(verify_application, "FACTS_PATH", facts_file)
    folder = make_folder(apps)
    path = folder / "cover_letter.txt"

    assert run_main(monkeypatch, capsys, write(path, GOOD_LETTER)) == (0, "")

    code, err = run_main(monkeypatch, capsys, write(path, "TODO"))
    assert code == 2 and err.startswith("Write blocked") and "placeholder" in err

    code, err = run_main(monkeypatch, capsys, edit(path, "thing one", "TODO"))
    assert code == 2 and err.startswith("Edit blocked")

    assert run_main(monkeypatch, capsys, write(folder / "jd.txt", "TODO"))[0] == 0
    assert run_main(monkeypatch, capsys, "not json")[0] == 1


def test_main_hides_candidate_name(apps, facts, monkeypatch, capsys, tmp_path):
    import verify_application
    import yaml

    facts_file = tmp_path / "cv_facts.yaml"
    facts_file.write_text(yaml.safe_dump(facts.model_dump(mode="json")), encoding="utf-8")
    monkeypatch.setattr(verify_application, "FACTS_PATH", facts_file)
    folder = make_folder(apps)
    code, err = run_main(monkeypatch, capsys, write(folder / "cover_letter.txt", GOOD_LETTER.replace("Test Person", "Someone Else")))

    assert code == 2 and "exact name" in err and facts.personal.full_name not in err


def test_main_fails_closed_for_guarded_file_when_facts_missing(apps, monkeypatch, capsys, tmp_path):
    import verify_application

    monkeypatch.setattr(verify_application, "FACTS_PATH", tmp_path / "missing.yaml")
    folder = make_folder(apps)
    code, err = run_main(monkeypatch, capsys, write(folder / "cover_letter.txt", GOOD_LETTER))

    assert code == 2 and "not writing unchecked" in err


def test_main_does_not_block_unguarded_call_on_hook_error(apps, monkeypatch, capsys, tmp_path):
    import verify_application

    monkeypatch.setattr(verify_application, "FACTS_PATH", tmp_path / "missing.yaml")
    folder = make_folder(apps)

    assert run_main(monkeypatch, capsys, write(folder / "jd.txt", "x"))[0] == 0
