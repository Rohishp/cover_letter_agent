"""
T06 structural requirements: _legacy/pipeline.py gone, state.py slimmed, one shared
OpenAI client, run_pipeline's public contract. Behavioural parity is in test_pipeline.py.
"""

import importlib
import inspect
import json
import re
from pathlib import Path

import pytest

import pipeline
from agents.client import client
from control_plane import state as state_module
from control_plane.state import CoverLetterState, save_state

ROOT = Path(__file__).resolve().parent.parent


def test_legacy_pipeline_is_deleted():
    assert not (ROOT / "_legacy" / "pipeline.py").exists()


@pytest.mark.parametrize("name", ["load_state", "list_states"])
def test_dead_module_functions_removed_from_state(name):
    assert not hasattr(state_module, name)


@pytest.mark.parametrize("name", ["is_terminal", "summary"])
def test_dead_state_methods_removed(name):
    assert not hasattr(CoverLetterState, name)


@pytest.mark.parametrize("name", ["save_state", "PipelineStatus", "CoverLetterState"])
def test_live_state_api_kept(name):
    assert hasattr(state_module, name)


def test_state_methods_still_used_by_pipeline_and_gates_remain():
    for name in ("touch", "update_status", "add_warning", "set_error"):
        assert callable(getattr(CoverLetterState, name))


@pytest.mark.parametrize(
    "module", ["agents.jd_parser", "agents.matcher", "agents.cover_letter_writer",
               "agents.evaluator", "cv.selector"],
)
def test_every_llm_caller_uses_the_one_shared_client(module):
    assert getattr(importlib.import_module(module), "client") is client


def test_only_agents_client_constructs_an_openai_client():
    files = [p for d in ("agents", "cv", "control_plane", "models", "scripts")
             for p in (ROOT / d).rglob("*.py")] + list(ROOT.glob("*.py"))
    offenders = [
        str(p.relative_to(ROOT)) for p in files
        if p.relative_to(ROOT).as_posix() != "agents/client.py"
        and re.search(r"\bOpenAI\s*\(", p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_run_pipeline_signature_is_unchanged():
    params = inspect.signature(pipeline.run_pipeline).parameters

    assert list(params) == ["jd_text", "facts", "applied_for_role", "force", "strongest_evidence"]
    assert params["force"].default is False
    assert params["strongest_evidence"].default is None
    assert params["jd_text"].default is params["jd_text"].empty


def test_pipeline_is_a_stage_list_of_callables():
    assert isinstance(pipeline.STAGES, list) and len(pipeline.STAGES) >= 4
    assert all(callable(stage) for stage in pipeline.STAGES)


def test_run_pipeline_never_raises_and_persists_a_failed_state(monkeypatch, tmp_path, facts):
    monkeypatch.setenv("LOCAL_DATA_DIR", str(tmp_path / "data"))

    def boom(**kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(client.beta.chat.completions, "parse", boom)
    state = pipeline.run_pipeline(jd_text="  padded jd  \n", facts=facts, applied_for_role="Engineer")
    saved = json.loads((tmp_path / "data" / "states" / f"{state.run_id}.json").read_text(encoding="utf-8"))

    assert isinstance(state, CoverLetterState)
    assert state.status == "failed" and "network down" in state.error
    assert state.raw_jd_text == "padded jd"
    assert saved["status"] == "failed" and saved["error"] == state.error


def test_save_state_writes_json_under_states_key(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_DATA_DIR", str(tmp_path / "data"))
    state = CoverLetterState()
    state.update_status("jd_loaded")
    save_state(state)
    saved = json.loads((tmp_path / "data" / "states" / f"{state.run_id}.json").read_text(encoding="utf-8"))

    assert saved["run_id"] == state.run_id and saved["status"] == "jd_loaded"
