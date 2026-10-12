"""Sub-agent verify hook: PostToolUse records touched folders, SubagentStop verifies them."""
import io
import json

import pytest

from helpers import make_folder, verify_application
from scripts import hook_verify_subagent as hook


@pytest.fixture
def apps(tmp_path, monkeypatch):
    root = tmp_path / "applications"
    root.mkdir()
    monkeypatch.setattr(hook, "APPLICATIONS", root)
    monkeypatch.setattr(hook, "STATE_DIR", tmp_path / "state")

    return root


def call(agent_id="a1", tool="Write", **tool_input):
    return {"hook_event_name": "PostToolUse", "agent_id": agent_id, "tool_name": tool, "tool_input": tool_input}


def stop(facts, agent_id="a1", **extra):
    payload = {"hook_event_name": "SubagentStop", "agent_id": agent_id, **extra}

    return hook.decide(payload, lambda folder: verify_application(folder, facts))


def run_main(monkeypatch, capsys, payload, verify=None):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload) if isinstance(payload, dict) else payload))

    if verify:
        monkeypatch.setattr(hook, "_verify", verify)

    code = hook.main()

    return code, capsys.readouterr().err


def test_clean_folder_lets_subagent_stop(apps, facts):
    folder = make_folder(apps)
    hook.record(call(file_path=str(folder / "cover_letter.txt")))

    assert stop(facts) == []


def test_broken_folder_reports_failures(apps, facts):
    folder = make_folder(apps)
    (folder / "cover_letter.txt").write_text("TODO [insert company]", encoding="utf-8")
    hook.record(call(file_path=str(folder / "cover_letter.txt")))
    failures = stop(facts)

    assert failures and all(f.startswith(folder.name) for f in failures)
    assert any("placeholder" in f for f in failures)


def test_bash_path_counts_as_touched(apps, facts):
    folder = make_folder(apps)
    (folder / "jd.txt").write_text("", encoding="utf-8")
    hook.record(call(tool="Bash", command=f"cat > output/applications/{folder.name}/jd.txt"))

    assert any("jd.txt is empty" in f for f in stop(facts))


def test_bash_command_naming_two_folders_records_both(apps, facts):
    one, two = make_folder(apps, "2026-10-12_Acme_Dev"), make_folder(apps, "2026-10-13_Beta_Dev")
    (two / "jd.txt").write_text("", encoding="utf-8")
    hook.record(call(tool="Bash", command=f"cp output/applications/{one.name}/x output/applications/{two.name}/"))

    assert any(f.startswith(two.name) and "jd.txt is empty" in f for f in stop(facts))


def test_relative_path_resolves_against_cwd(tmp_path, apps, facts):
    folder = make_folder(apps)
    (folder / "jd.txt").write_text("", encoding="utf-8")
    hook.record(call(file_path=f"{folder.name}/jd.txt", cwd=str(apps)) | {"cwd": str(apps)})

    assert any("jd.txt is empty" in f for f in stop(facts))


def test_dotdot_from_bash_is_not_a_folder(apps, facts):
    hook.record(call(tool="Bash", command="ls output/applications/.."))

    assert not (hook.STATE_DIR / "a1.txt").exists()


def test_other_agents_and_unrelated_calls_ignored(tmp_path, apps, facts):
    broken = make_folder(apps)
    (broken / "jd.txt").write_text("", encoding="utf-8")
    hook.record(call(file_path=str(tmp_path / "notes.txt")))
    hook.record(call(tool="Read", file_path=str(broken / "jd.txt")))
    hook.record(call(agent_id="other", file_path=str(broken / "jd.txt")))
    hook.record({"tool_name": "Write", "tool_input": {"file_path": str(broken / "jd.txt")}})  # main session

    assert stop(facts) == []


def test_second_pass_never_blocks(apps, facts):
    folder = make_folder(apps)
    (folder / "jd.txt").write_text("", encoding="utf-8")
    hook.record(call(file_path=str(folder / "jd.txt")))

    assert stop(facts, stop_hook_active=True) == []


def test_record_is_deleted_after_stop_so_agent_id_reuse_starts_clean(apps, facts):
    folder = make_folder(apps)
    (folder / "jd.txt").write_text("", encoding="utf-8")
    hook.record(call(file_path=str(folder / "jd.txt")))

    assert stop(facts)
    assert stop(facts) == []


def test_nothing_recorded_allows(apps, facts):
    assert stop(facts) == []
    assert hook.decide({}, lambda folder: ["never called"]) == []


def test_main_post_tool_use_records_and_allows(apps, monkeypatch, capsys):
    folder = make_folder(apps)
    code, err = run_main(monkeypatch, capsys, call(file_path=str(folder / "jd.txt")))

    assert (code, err) == (0, "")
    assert (hook.STATE_DIR / "a1.txt").read_text(encoding="utf-8").split() == [folder.name]


def test_main_blocks_with_redacted_failures(apps, monkeypatch, capsys):
    folder = make_folder(apps)
    hook.record(call(file_path=str(folder / "jd.txt")))
    code, err = run_main(
        monkeypatch, capsys, {"hook_event_name": "SubagentStop", "agent_id": "a1"},
        verify=lambda f: ["cover_letter.txt: greeting is missing; exact name Jane Q Public"],
    )

    assert code == 2 and folder.name in err and "<hidden>" in err and "Jane" not in err


def test_main_verifier_error_blocks_once_then_allows(apps, monkeypatch, capsys):
    folder = make_folder(apps)

    def broken(_folder):
        raise FileNotFoundError("cv_facts.yaml")

    hook.record(call(file_path=str(folder / "jd.txt")))
    code, err = run_main(monkeypatch, capsys, {"hook_event_name": "SubagentStop", "agent_id": "a1"}, verify=broken)

    assert code == 2 and "FileNotFoundError" in err

    hook.record(call(file_path=str(folder / "jd.txt")))
    code, _ = run_main(
        monkeypatch, capsys, {"hook_event_name": "SubagentStop", "agent_id": "a1", "stop_hook_active": True}
    )

    assert code == 0


def test_main_verifier_error_ignored_when_nothing_touched(apps, monkeypatch, capsys):
    def broken(_folder):
        raise FileNotFoundError("cv_facts.yaml")

    code, _ = run_main(monkeypatch, capsys, {"hook_event_name": "SubagentStop", "agent_id": "a1"}, verify=broken)

    assert code == 0


def test_main_bad_payload_allows(apps, monkeypatch, capsys):
    code, err = run_main(monkeypatch, capsys, "not json")

    assert code == 0 and "could not run" in err
