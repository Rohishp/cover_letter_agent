"""
T06 acceptance: one shared OpenAI client, and run_pipeline's catch-all error path.
Behavioural parity with the legacy pipeline is in test_pipeline.py.
"""

import importlib
import json
import re
from pathlib import Path

import pytest

import pipeline
from agents.client import client
from control_plane.state import CoverLetterState

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    "module", ["agents.jd_parser", "agents.matcher", "agents.cover_letter_writer",
               "agents.evaluator", "cv.selector"],
)
def test_every_llm_caller_uses_the_one_shared_client(module):
    assert getattr(importlib.import_module(module), "client") is client


def test_only_agents_client_constructs_an_openai_client():
    """Catches a new module that builds its own client (how the repo once got six)."""
    files = [p for d in ("agents", "cv", "control_plane", "models", "scripts")
             for p in (ROOT / d).rglob("*.py")] + list(ROOT.glob("*.py"))
    offenders = [
        str(p.relative_to(ROOT)) for p in files
        if p.relative_to(ROOT).as_posix() != "agents/client.py"
        and re.search(r"\bOpenAI\s*\(", p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


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
