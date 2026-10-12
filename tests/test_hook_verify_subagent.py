"""Sub-agent verify hook: PostToolUse records touched folders, SubagentStop verifies them."""
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


def test_nothing_recorded_allows(apps, facts):
    assert stop(facts) == []
    assert hook.decide({}, lambda folder: ["never called"]) == []
