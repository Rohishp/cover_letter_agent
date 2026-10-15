"""
T07: apply.py --prepare / --finish. Only the OpenAI boundary is faked (the shared client's `parse`),
plus the CV renderer, which needs Word and is covered by its own tests.
"""

import json
from types import SimpleNamespace

import pytest

import apply
from agents.client import client
from control_plane.cover_letter_containment import check_ungrounded_figures
from control_plane.thresholds import MAX_COVER_LETTER_RETRIES
from cv.selector import CVSelection
from models.cover_letter_schema import CoverLetterDraft
from models.eval_schema import CriterionScore, EvalResult

from helpers import GOOD_LETTER
from verify_application import verify_application
from test_pipeline import GOOD, JD_TEXT, PARSED_JD, FakeOpenAI, _match

FAILING_EVAL = EvalResult(
    hook=CriterionScore(score=5, feedback="weak"), keyword_match=CriterionScore(score=5, feedback="weak"),
    proof_over_pitch=CriterionScore(score=5, feedback="weak"),
    zero_resume_duplication=CriterionScore(score=5, feedback="weak"),
    cta=CriterionScore(score=5, feedback="weak"), overall_score=25, feedback_text="Too generic.",
)
SELECTION = CVSelection(
    section_order_reason="x", section_order=[], bullet_ranks=[], project_ranks=[],
    skill_group_ranks=[], target_title="Backend Engineer",
)


@pytest.fixture(autouse=True)
def workspace(tmp_path, monkeypatch, facts):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOCAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(apply, "load_facts", lambda _path: facts)
    monkeypatch.setattr(apply, "select_cv_content", lambda *_: SELECTION)


@pytest.fixture
def fake_cv(monkeypatch):
    """generate_cv stand-in that writes the two files the real one does (Word is not needed here)."""

    def generate_cv(facts, parsed_jd, out_path, **_):
        out_path.write_bytes(b"docx")
        out_path.with_suffix(".pdf").write_bytes(b"%PDF-1.4 test")
        return SimpleNamespace(page_count=1, content=None)

    monkeypatch.setattr(apply, "generate_cv", generate_cv)
    monkeypatch.setattr(apply, "build_cv_run_summary", lambda _result: {})
    monkeypatch.setattr(apply, "underdescribed_requirements", lambda *_: [])
    monkeypatch.setattr(apply, "verify_application", lambda *_: [])


def _openai(monkeypatch, strength="strong", eval_result=None, drafts=(GOOD,)):
    fake = FakeOpenAI(PARSED_JD, _match(strength), list(drafts), *([eval_result] if eval_result else []))
    monkeypatch.setattr(client.beta.chat.completions, "parse", fake)
    return fake


def _prepare(monkeypatch, strength="strong", force=False, **kwargs):
    fake = _openai(monkeypatch, strength, **kwargs)
    code, folder = apply.prepare(JD_TEXT, force=force)
    return fake, code, folder


def _run_json(folder):
    return json.loads((folder / "run.json").read_text(encoding="utf-8"))


def test_prepare_writes_folder_with_brief_and_state_and_never_calls_the_writer(monkeypatch):
    fake, code, folder = _prepare(monkeypatch)

    assert code == 0
    assert sorted(p.name for p in folder.iterdir()) == ["brief.md", "jd.txt", "run.json", "state.json"]
    assert fake.of(CoverLetterDraft) == []
    assert _run_json(folder)["status"] == "prepared"
    assert _run_json(folder)["company_name"] == "Test Co"
    brief = (folder / "brief.md").read_text(encoding="utf-8")
    assert "exp.acme" in brief and "Test Co" in brief and "Best regards," in brief


def test_prepare_on_a_weak_match_leaves_nothing_in_output(monkeypatch, tmp_path):
    _, code, folder = _prepare(monkeypatch, strength="not_evidenced")

    assert (code, folder) == (apply.EXIT_REJECTED, None)
    assert not (tmp_path / "output").exists()


def test_prepare_with_force_passes_a_weak_match(monkeypatch):
    _, code, folder = _prepare(monkeypatch, strength="not_evidenced", force=True)

    assert code == 0 and _run_json(folder)["forced"] is True


def test_finish_with_a_draft_does_not_call_the_writer_or_rematch(monkeypatch, fake_cv):
    _, _, folder = _prepare(monkeypatch)
    fake = _openai(monkeypatch)
    draft = folder.parent / "draft.txt"
    draft.write_text(GOOD_LETTER, encoding="utf-8")

    code = apply.finish(folder, draft)

    assert code == 0
    assert fake.of(CoverLetterDraft) == []
    assert [c["response_format"].__name__ for c in fake.calls] == ["EvalResult"]  # evaluator only
    assert (folder / "cover_letter.txt").read_text(encoding="utf-8") == GOOD_LETTER
    assert _run_json(folder)["status"] == "completed"


def test_finish_without_a_draft_uses_the_openai_writer(monkeypatch, fake_cv):
    _, _, folder = _prepare(monkeypatch)
    fake = _openai(monkeypatch)

    assert apply.finish(folder) == 0
    # The letter never names Python/Kubernetes, so every attempt leaves a requirement unused and the
    # pipeline retries up to its cap, then accepts the last letter.
    assert len(fake.of(CoverLetterDraft)) == MAX_COVER_LETTER_RETRIES + 1
    assert (folder / "cover_letter.txt").read_text(encoding="utf-8").startswith("Dear Test Co team,")


def test_finish_writes_cv_docx_and_a_non_empty_cv_pdf(monkeypatch, fake_cv):
    _, _, folder = _prepare(monkeypatch)
    _openai(monkeypatch)
    apply.finish(folder)

    assert (folder / "cv.docx").stat().st_size > 0
    assert (folder / "cv.pdf").stat().st_size > 0


def test_finish_fails_loudly_when_the_pdf_cannot_be_made(monkeypatch, fake_cv):
    _, _, folder = _prepare(monkeypatch)
    _openai(monkeypatch)

    def no_converter(*_args, **_kwargs):
        raise RuntimeError("Cannot finalize CV -- no PDF converter available: none")

    monkeypatch.setattr(apply, "generate_cv", no_converter)

    assert apply.finish(folder) == apply.EXIT_FAILED
    assert _run_json(folder)["status"] == "failed"
    assert "no PDF converter" in _run_json(folder)["failure_reason"]
    assert not (folder / "cv.pdf").exists()


def test_a_draft_failing_evaluation_is_not_retried_and_leaves_no_letter_or_cv(monkeypatch, fake_cv):
    _, _, folder = _prepare(monkeypatch)
    fake = _openai(monkeypatch, eval_result=FAILING_EVAL)
    draft = folder.parent / "draft.txt"
    draft.write_text(GOOD_LETTER, encoding="utf-8")

    assert apply.finish(folder, draft) == apply.EXIT_FAILED
    assert len(fake.of(type(FAILING_EVAL))) == 1 and fake.of(CoverLetterDraft) == []
    assert _run_json(folder)["status"] == "failed"
    assert not (folder / "cover_letter.txt").exists() and not (folder / "cv.docx").exists()


def test_a_draft_with_a_placeholder_is_rejected_before_any_llm_call(monkeypatch, fake_cv):
    _, _, folder = _prepare(monkeypatch)
    fake = _openai(monkeypatch)
    draft = folder.parent / "draft.txt"
    draft.write_text(GOOD_LETTER.replace("Dear team", "Dear [Hiring Manager]"), encoding="utf-8")

    assert apply.finish(folder, draft) == apply.EXIT_UNVERIFIED
    assert fake.calls == []
    assert _run_json(folder)["status"] == "prepared"


def test_finish_returns_unverified_when_verification_fails(monkeypatch, fake_cv):
    _, _, folder = _prepare(monkeypatch)
    _openai(monkeypatch)
    monkeypatch.setattr(apply, "verify_application", lambda *_: ["cv.pdf is missing"])

    assert apply.finish(folder) == apply.EXIT_UNVERIFIED


def test_main_dispatch_and_usage(monkeypatch, tmp_path, fake_cv):
    jd = tmp_path / "jd.txt"
    jd.write_text(JD_TEXT, encoding="utf-8")
    _openai(monkeypatch)

    assert apply.main(["apply.py", "--prepare", str(jd)]) == 0
    folder = next((tmp_path / "output" / "applications").iterdir())
    assert apply.main(["apply.py", "--finish", str(folder)]) == 0
    assert apply.main(["apply.py"]) == apply.EXIT_FAILED
    assert apply.main(["apply.py", "--finish"]) == apply.EXIT_FAILED
    assert apply.main(["apply.py", "--draft"]) == apply.EXIT_FAILED
    assert apply.main(["apply.py", "--prepare", str(jd), "--draft", "x.txt"]) == apply.EXIT_FAILED
    assert apply.main(["apply.py", "--finish", str(folder), "--force"]) == apply.EXIT_FAILED


def test_a_missing_jd_file_exits_with_a_message_not_a_traceback(tmp_path):
    with pytest.raises(SystemExit) as exit_info:
        apply.main(["apply.py", "--prepare", str(tmp_path / "missing.txt")])

    assert "cannot read JD file" in str(exit_info.value)


def test_finish_with_the_real_verifier_fails_when_cv_pdf_is_missing(monkeypatch, fake_cv):
    _, _, folder = _prepare(monkeypatch)
    _openai(monkeypatch)

    def generate_cv_without_pdf(facts, parsed_jd, out_path, **_):
        out_path.write_bytes(b"docx")
        return SimpleNamespace(page_count=1, content=None)

    monkeypatch.setattr(apply, "generate_cv", generate_cv_without_pdf)
    monkeypatch.setattr(apply, "verify_application", lambda f, facts: verify_application(f, facts, check_pages=False))

    assert apply.finish(folder) == apply.EXIT_UNVERIFIED


def test_prepare_survives_a_cv_selection_failure_and_leaves_no_folder(monkeypatch, tmp_path):
    def boom(*_):
        raise RuntimeError("selector down")

    monkeypatch.setattr(apply, "select_cv_content", boom)
    _openai(monkeypatch)

    assert apply.prepare(JD_TEXT) == (apply.EXIT_FAILED, None)
    assert not (tmp_path / "output").exists()


def test_prepare_removes_a_half_made_folder_when_a_write_fails(monkeypatch, tmp_path):
    def boom(*_):
        raise OSError("disk full")

    monkeypatch.setattr(apply, "build_brief", boom)
    _openai(monkeypatch)

    assert apply.prepare(JD_TEXT) == (apply.EXIT_FAILED, None)
    assert list((tmp_path / "output" / "applications").iterdir()) == []


def _edit_state(folder, change):
    path = folder / "state.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    change(saved["state"])
    path.write_text(json.dumps(saved), encoding="utf-8")


@pytest.mark.parametrize("change", [
    lambda s: s.update(status="rejected"),
    lambda s: s.update(status="failed"),
    lambda s: s.update(forced=True, match_gate_result="passed"),  # forced flag alone is not enough
    lambda s: s.update(parsed_jd=None),
])
def test_finish_refuses_a_tampered_state_before_any_llm_call(monkeypatch, fake_cv, change):
    _, _, folder = _prepare(monkeypatch)
    fake = _openai(monkeypatch)
    _edit_state(folder, lambda s: (s["match_analysis"].update(base_score=0, core_must_have_score=0), change(s)))

    assert apply.finish(folder) == apply.EXIT_FAILED
    assert fake.calls == []


def test_finish_accepts_a_forced_weak_match_it_prepared(monkeypatch, fake_cv):
    _, _, folder = _prepare(monkeypatch, strength="not_evidenced", force=True)
    _openai(monkeypatch, strength="not_evidenced")

    assert apply.finish(folder) == 0


def test_finish_refuses_a_completed_application_and_leaves_it_untouched(monkeypatch, fake_cv):
    _, _, folder = _prepare(monkeypatch)
    _openai(monkeypatch)
    assert apply.finish(folder) == 0
    letter = (folder / "cover_letter.txt").read_text(encoding="utf-8")
    fake = _openai(monkeypatch)

    assert apply.finish(folder) == apply.EXIT_FAILED
    assert fake.calls == []
    assert (folder / "cover_letter.txt").read_text(encoding="utf-8") == letter


def test_a_failed_run_can_be_finished_again_with_a_better_draft(monkeypatch, fake_cv):
    _, _, folder = _prepare(monkeypatch)
    draft = folder.parent / "draft.txt"
    draft.write_text(GOOD_LETTER, encoding="utf-8")
    _openai(monkeypatch, eval_result=FAILING_EVAL)
    assert apply.finish(folder, draft) == apply.EXIT_FAILED

    _openai(monkeypatch)

    assert apply.finish(folder, draft) == 0
    assert _run_json(folder)["status"] == "completed"


def test_finish_refuses_a_folder_outside_the_applications_root(monkeypatch, tmp_path, fake_cv):
    _, _, folder = _prepare(monkeypatch)
    elsewhere = tmp_path / "elsewhere"
    folder.rename(elsewhere)

    assert apply.finish(elsewhere) == apply.EXIT_FAILED


def test_finish_refuses_a_folder_without_state(tmp_path):
    folder = tmp_path / "output" / "applications" / "2026-01-01_Acme_Engineer"
    folder.mkdir(parents=True)

    assert apply.finish(folder) == apply.EXIT_FAILED


def test_a_draft_with_an_invented_figure_is_rejected_before_any_llm_call(monkeypatch, fake_cv):
    _, _, folder = _prepare(monkeypatch)
    fake = _openai(monkeypatch)
    draft = folder.parent / "draft.txt"
    draft.write_text(GOOD_LETTER.replace("thing one", "thing one for 9999 users"), encoding="utf-8")

    assert apply.finish(folder, draft) == apply.EXIT_UNVERIFIED
    assert fake.calls == []


def test_a_figure_from_the_fact_base_or_the_jd_is_grounded():
    assert check_ungrounded_figures("42 widgets, 10x, 3.5%", "Did 42 widgets. 10x faster. 3.5% lift.") == []
    assert check_ungrounded_figures("42 widgets in 2031.", "Did 42 widgets.") == [
        "figure '2031' is in neither the fact base nor the JD"
    ]


def test_a_draft_failure_message_reports_zero_retries(monkeypatch, fake_cv):
    _, _, folder = _prepare(monkeypatch)
    draft = folder.parent / "draft.txt"
    draft.write_text(GOOD_LETTER, encoding="utf-8")
    _openai(monkeypatch, eval_result=FAILING_EVAL)
    apply.finish(folder, draft)

    assert "after 0 retries" in _run_json(folder)["failure_reason"]


def test_an_api_key_in_a_cv_error_is_redacted(monkeypatch, fake_cv):
    _, _, folder = _prepare(monkeypatch)
    _openai(monkeypatch)

    def leaky(*_a, **_k):
        raise RuntimeError("auth failed for sk-abc123_DEF")

    monkeypatch.setattr(apply, "generate_cv", leaky)
    apply.finish(folder)

    assert "sk-abc123" not in _run_json(folder)["failure_reason"]
