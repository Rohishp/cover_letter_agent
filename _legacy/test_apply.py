# apply.py's own logic (run_pipeline, generate_cv, load_facts,
# build_cv_run_summary) is mocked throughout -- this file tests only the
# CV-generation branch condition, not pipeline or CV-generation internals
# (those are covered in test_pipeline_force.py / test_selection_rules.py).

import json
from unittest.mock import MagicMock, patch

import apply
from control_plane.state import CoverLetterState
from models.jd_schema import ParsedJD


def _state(cover_letter, status, forced=False):
    return CoverLetterState(
        raw_jd_text="some jd text",
        parsed_jd=ParsedJD(job_title="Engineer", company_name="Acme"),
        status=status,
        cover_letter=cover_letter,
        forced=forced,
        match_gate_result="would_have_rejected" if forced else (
            "passed" if status != "rejected" else "would_have_rejected"
        ),
    )


def test_no_cv_generated_when_cover_letter_is_none(tmp_path):
    state = _state(cover_letter=None, status="rejected")
    out_dir = tmp_path / "app"

    with patch.object(apply, "run_pipeline", return_value=state), \
         patch.object(apply, "resolve_application_dir", return_value=out_dir), \
         patch.object(apply, "load_facts", return_value=MagicMock()), \
         patch.object(apply, "parse_jd_cached", return_value=(ParsedJD(), False)), \
         patch.object(apply, "select_cv_content", return_value=MagicMock()), \
         patch.object(apply, "top_ranked_project_text", return_value=None), \
         patch.object(apply, "generate_cv") as mock_generate_cv:
        result_dir = apply.apply("some jd text")

    assert result_dir == out_dir
    mock_generate_cv.assert_not_called()
    assert not (out_dir / "cv.docx").exists()
    assert not (out_dir / "cover_letter.txt").exists()

    summary = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
    assert "cv" not in summary
    assert "rejection_reason" in summary


def test_no_cover_letter_or_cv_when_eval_retries_exhausted(tmp_path):
    # status == "failed" with a REJECTED draft still sitting in
    # state.cover_letter -- exactly what run_pipeline leaves behind when
    # the evaluation loop exhausts MAX_COVER_LETTER_RETRIES. This is the
    # bug: state.cover_letter is not None here, so a check gating on that
    # alone would (and did) write it out as if it were accepted.
    state = _state(
        cover_letter="Dear Hiring Team, this is the last REJECTED draft...",
        status="failed",
    )
    state.eval_score = 63
    state.error = "Cover letter failed evaluation after 2 retries. Final score: 63."
    out_dir = tmp_path / "app"

    with patch.object(apply, "run_pipeline", return_value=state), \
         patch.object(apply, "resolve_application_dir", return_value=out_dir), \
         patch.object(apply, "load_facts", return_value=MagicMock()), \
         patch.object(apply, "parse_jd_cached", return_value=(ParsedJD(), False)), \
         patch.object(apply, "select_cv_content", return_value=MagicMock()), \
         patch.object(apply, "top_ranked_project_text", return_value=None), \
         patch.object(apply, "generate_cv") as mock_generate_cv:
        result_dir = apply.apply("some jd text")

    assert result_dir == out_dir
    mock_generate_cv.assert_not_called()
    assert not (out_dir / "cv.docx").exists()
    assert not (out_dir / "cv.pdf").exists()
    assert not (out_dir / "cover_letter.txt").exists()
    assert (out_dir / "jd.txt").exists()

    # The rejected draft is written for debugging, but only under a name
    # that cannot be mistaken for a sendable deliverable.
    debug_path = out_dir / "cover_letter.REJECTED.txt"
    assert debug_path.exists()
    assert debug_path.read_text(encoding="utf-8") == state.cover_letter

    summary = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
    assert "cv" not in summary
    assert summary["failure_reason"] == state.error
    assert summary["last_eval_score"] == 63
    assert summary["run_id"] == state.run_id


def test_cv_generated_when_cover_letter_present_even_if_forced(tmp_path):
    state = _state(cover_letter="Dear Hiring Team, ...", status="completed", forced=True)
    out_dir = tmp_path / "app"

    fake_cv_result = MagicMock()
    fake_cv_result.page_count = 2

    with patch.object(apply, "run_pipeline", return_value=state), \
         patch.object(apply, "resolve_application_dir", return_value=out_dir), \
         patch.object(apply, "load_facts", return_value=MagicMock()), \
         patch.object(apply, "parse_jd_cached", return_value=(ParsedJD(), False)), \
         patch.object(apply, "select_cv_content", return_value=MagicMock()), \
         patch.object(apply, "top_ranked_project_text", return_value=None), \
         patch.object(apply, "generate_cv", return_value=fake_cv_result) as mock_generate_cv, \
         patch.object(apply, "build_cv_run_summary", return_value={"fake": "cv-summary"}):
        result_dir = apply.apply("some jd text", force=True)

    assert result_dir == out_dir
    mock_generate_cv.assert_called_once()
    assert (out_dir / "cover_letter.txt").read_text(encoding="utf-8") == "Dear Hiring Team, ..."

    summary = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
    assert summary["cv"] == {"fake": "cv-summary", "underdescribed_requirements": []}
    assert summary["cover_letter"]["forced"] is True


def test_cv_generated_on_normal_unforced_pass(tmp_path):
    state = _state(cover_letter="Dear Hiring Team, ...", status="completed", forced=False)
    out_dir = tmp_path / "app"

    fake_cv_result = MagicMock()
    fake_cv_result.page_count = 2

    with patch.object(apply, "run_pipeline", return_value=state), \
         patch.object(apply, "resolve_application_dir", return_value=out_dir), \
         patch.object(apply, "load_facts", return_value=MagicMock()), \
         patch.object(apply, "parse_jd_cached", return_value=(ParsedJD(), False)), \
         patch.object(apply, "select_cv_content", return_value=MagicMock()), \
         patch.object(apply, "top_ranked_project_text", return_value=None), \
         patch.object(apply, "generate_cv", return_value=fake_cv_result) as mock_generate_cv, \
         patch.object(apply, "build_cv_run_summary", return_value={"fake": "cv-summary"}):
        apply.apply("some jd text", force=False)

    mock_generate_cv.assert_called_once()


def test_force_flag_parsed_from_argv(monkeypatch, tmp_path):
    jd_file = tmp_path / "jd.txt"
    jd_file.write_text("some jd text", encoding="utf-8")

    captured = {}

    def fake_apply(jd_text, force=False):
        captured["jd_text"] = jd_text
        captured["force"] = force
        return tmp_path

    monkeypatch.setattr(apply, "apply", fake_apply)
    monkeypatch.setattr("sys.argv", ["apply.py", str(jd_file), "--force"])

    apply.main()

    assert captured["force"] is True
    assert captured["jd_text"] == "some jd text"


def test_no_force_flag_defaults_to_false(monkeypatch, tmp_path):
    jd_file = tmp_path / "jd.txt"
    jd_file.write_text("some jd text", encoding="utf-8")

    captured = {}

    def fake_apply(jd_text, force=False):
        captured["force"] = force
        return tmp_path

    monkeypatch.setattr(apply, "apply", fake_apply)
    monkeypatch.setattr("sys.argv", ["apply.py", str(jd_file)])

    apply.main()

    assert captured["force"] is False
