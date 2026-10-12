"""T05 spec tests: SubagentStop hook runs verify_application on the application folder the sub-agent touched."""
import io
import json
from pathlib import Path

import pytest

from helpers import GOOD_LETTER, make_folder, verify_application
from scripts import hook_verify_subagent as hook

ROOT = Path(__file__).resolve().parent.parent
ENTRY = "hook_verify_subagent.py"


@pytest.fixture
def apps(tmp_path, monkeypatch):
    root = tmp_path / "applications"
    root.mkdir()
    monkeypatch.setattr(hook, "APPLICATIONS", root)
    monkeypatch.setattr(hook, "STATE_DIR", tmp_path / "state")

    return root


@pytest.fixture
def verify(facts):
    return lambda folder: verify_application(folder, facts)


def broken(apps, name="2026-08-17_Acme_Engineer"):
    folder = make_folder(apps, name)
    (folder / "cover_letter.txt").write_text("TODO [insert company]", encoding="utf-8")

    return folder


def post(agent_id, tool, folder_file, **extra):
    inp = {"command": f"echo hi > {folder_file}"} if tool == "Bash" else {"file_path": str(folder_file), "content": "x"}

    return {"hook_event_name": "PostToolUse", "agent_id": agent_id, "tool_name": tool, "tool_input": inp, **extra}


def stop(agent_id="a1", **extra):
    return {"hook_event_name": "SubagentStop", "agent_id": agent_id, **extra}


def touch(folder, agent_id="a1"):
    hook.record(post(agent_id, "Write", folder / "jd.txt"))


# Scope: hook registered for SubagentStop
def test_settings_registers_subagentstop_hook():
    hooks = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))["hooks"]
    entries = hooks["SubagentStop"]

    assert (ROOT / "scripts" / ENTRY).is_file()
    assert any(ENTRY in h.get("command", "") for e in entries for h in e["hooks"])


# Done when: clean folder is not blocked
def test_clean_folder_touched_lets_subagent_stop(apps, verify):
    touch(make_folder(apps))

    assert hook.decide(stop(), verify) == []


# Done when: broken folder yields failures; Scope: reports failures back
def test_broken_folder_touched_reports_failures(apps, verify):
    folder = broken(apps)
    touch(folder)
    failures = hook.decide(stop(), verify)

    assert failures and folder.name in " ".join(failures)


def test_failures_match_verify_application_for_the_folder(apps, verify):
    folder = broken(apps)
    touch(folder)
    expected = verify(folder)

    got = hook.decide(stop(), verify)  # decide consumes the agent's record, so call it once

    assert expected
    assert all(any(f in g for g in got) for f in expected)


# Scope: only the folder the sub-agent touched
def test_untouched_broken_folder_ignored(apps, verify):
    broken(apps, "2026-08-17_Bad_Engineer")
    touch(make_folder(apps, "2026-08-18_Good_Engineer"))

    assert hook.decide(stop(), verify) == []


def test_other_agents_touched_folder_ignored(apps, verify):
    touch(broken(apps), agent_id="other")

    assert hook.decide(stop("a1"), verify) == []


def test_subagent_that_touched_nothing_is_not_blocked(apps, verify):
    broken(apps)

    assert hook.decide(stop(), verify) == []


@pytest.mark.parametrize("tool", ["Write", "Edit", "Bash"])
def test_each_tool_kind_marks_folder_as_touched(apps, verify, tool):
    folder = broken(apps)
    target = folder / "jd.txt"
    hook.record(post("a1", tool, target if tool != "Bash" else f"output/applications/{folder.name}/jd.txt"))

    assert hook.decide(stop(), verify)


def test_touching_a_file_outside_applications_is_not_a_touch(apps, verify, tmp_path):
    broken(apps)
    hook.record(post("a1", "Write", tmp_path / "notes.txt"))

    assert hook.decide(stop(), verify) == []


def test_main_session_call_without_agent_id_not_recorded(apps, verify):
    folder = broken(apps)
    payload = post("a1", "Write", folder / "jd.txt")
    del payload["agent_id"]
    hook.record(payload)

    assert hook.decide(stop(), verify) == []


# Scope: never loop forever on an unfixable failure
def test_stop_hook_active_never_blocks(apps, verify):
    touch(broken(apps))

    assert hook.decide(stop(stop_hook_active=True), verify) == []


# Scope: main() exit codes (2 + failures on stderr, 0 otherwise)
def run_main(monkeypatch, capsys, data):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(data)))
    code = hook.main()

    return code, capsys.readouterr().err


@pytest.fixture
def stub_verifier(monkeypatch, verify):
    monkeypatch.setattr(hook, "_verify", verify)


def test_main_broken_folder_exit_2_with_failures_on_stderr(apps, stub_verifier, monkeypatch, capsys):
    folder = broken(apps)
    code, _ = run_main(monkeypatch, capsys, post("a1", "Write", folder / "jd.txt"))
    assert code == 0

    code, err = run_main(monkeypatch, capsys, stop())

    assert code == 2 and folder.name in err


def test_main_clean_folder_exit_0_and_silent(apps, stub_verifier, monkeypatch, capsys):
    folder = make_folder(apps)
    run_main(monkeypatch, capsys, post("a1", "Write", folder / "jd.txt"))

    assert run_main(monkeypatch, capsys, stop()) == (0, "")


def test_main_second_pass_exit_0_even_when_still_broken(apps, stub_verifier, monkeypatch, capsys):
    folder = broken(apps)
    run_main(monkeypatch, capsys, post("a1", "Write", folder / "jd.txt"))

    assert run_main(monkeypatch, capsys, stop(stop_hook_active=True))[0] == 0


def test_main_garbage_stdin_does_not_block(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))

    assert hook.main() == 0
