"""T06 spec lines not covered by test_pipeline.py / test_core_rebuild_t06.py."""

import ast
from pathlib import Path

import pipeline

ROOT = Path(__file__).resolve().parent.parent


def test_legacy_pipeline_is_deleted_and_not_imported():
    assert not (ROOT / "_legacy" / "pipeline.py").exists()
    live = [p for d in ("agents", "cv", "control_plane", "models", "scripts", "tests")
            for p in (ROOT / d).rglob("*.py") if p != Path(__file__).resolve()] + list(ROOT.glob("*.py"))
    offenders = [str(p.relative_to(ROOT)) for p in live if "_legacy.pipeline" in p.read_text(encoding="utf-8")
                 or "from _legacy import pipeline" in p.read_text(encoding="utf-8")]
    assert offenders == []


def test_pipeline_is_a_small_ordered_stage_list():
    names = [s.__name__ for s in pipeline.STAGES]
    assert names == ["parse_jd_stage", "validate_jd", "match_stage", "gate", "write_and_evaluate"]
    assert all(callable(s) for s in pipeline.STAGES)


def test_state_module_is_slimmed_to_model_and_save_state():
    tree = ast.parse((ROOT / "control_plane" / "state.py").read_text(encoding="utf-8"))
    funcs = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    assert funcs == ["save_state"]
