"""
T07: apply.py --prepare / --finish. Only the OpenAI boundary is faked (the shared client's `parse`),
plus the CV renderer, which needs Word and is covered by its own tests.
"""

import json
from types import SimpleNamespace

import pytest

import apply
from agents.client import client
from cv.selector import CVSelection
from models.cover_letter_schema import CoverLetterDraft
from models.eval_schema import CriterionScore, EvalResult

from helpers import GOOD_LETTER
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
    assert fake.of(CoverLetterDraft)  # the letter never names Python/Kubernetes, so the pipeline retries
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
