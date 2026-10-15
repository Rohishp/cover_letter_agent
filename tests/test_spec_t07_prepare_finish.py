"""
T07 spec tests (tasks/T07-prepare-finish.md), derived from its Scope and "Done when" lines.
Complements tests/test_apply_prepare_finish_t07.py without repeating it. Only the OpenAI boundary
(the shared client's `parse`) and the CV renderer (Word/PDF conversion) are faked.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document

import apply
from agents.client import client
from cv.selector import CVSelection
from models.cover_letter_schema import CoverLetterDraft
from verify_application import verify_application as real_verify

from helpers import GOOD_LETTER, make_folder
from test_pipeline import JD_TEXT, PARSED_JD, GOOD, FakeOpenAI, _match

ROOT = Path(__file__).resolve().parent.parent
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
    monkeypatch.setattr(apply, "build_cv_run_summary", lambda _result: {})
    monkeypatch.setattr(apply, "underdescribed_requirements", lambda *_: [])
    # Real verifier, minus the docx-to-PDF page render (needs Word or LibreOffice).
    monkeypatch.setattr(apply, "verify_application", lambda f, fb: real_verify(f, fb, check_pages=False))


def _openai(monkeypatch):
    fake = FakeOpenAI(PARSED_JD, _match("strong"), [GOOD])
    monkeypatch.setattr(client.beta.chat.completions, "parse", fake)
    return fake


def _cv_renderer(monkeypatch, pdf=b"%PDF-1.4 test"):
    """Stand-in for generate_cv: writes a valid docx and, if given, the PDF beside it."""

    def generate_cv(facts, parsed_jd, out_path, **_):
        Document().save(str(out_path))
        if pdf is not None:
            out_path.with_suffix(".pdf").write_bytes(pdf)
        return SimpleNamespace(page_count=1, content=None)

    monkeypatch.setattr(apply, "generate_cv", generate_cv)


def _prepared(monkeypatch):
    _openai(monkeypatch)
    code, folder = apply.prepare(JD_TEXT)
    assert code == 0
    return folder


def _draft(folder, text=GOOD_LETTER):
    path = folder.parent / "draft.txt"
    path.write_text(text, encoding="utf-8")
    return path


def _run_json(folder):
    return json.loads((folder / "run.json").read_text(encoding="utf-8"))


# Scope: "--prepare parses, matches, applies the gate and writes a brief file" -- and stops there.
def test_prepare_alone_produces_no_letter_or_cv_files(monkeypatch):
    folder = _prepared(monkeypatch)

    assert not any((folder / n).exists() for n in ("cover_letter.txt", "cv.docx", "cv.pdf"))
    assert (folder / "brief.md").stat().st_size > 0


# Done when: "Both steps testable independently" -- finish needs only the folder, no in-memory prepare state.
def test_finish_runs_from_the_folder_alone_in_a_fresh_client(monkeypatch):
    folder = _prepared(monkeypatch)
    _cv_renderer(monkeypatch)
    fake = _openai(monkeypatch)  # new fake: nothing carried over from prepare

    assert apply.finish(folder, _draft(folder)) == 0
    assert fake.of(CoverLetterDraft) == []


# Scope: "--finish ... Uses the OpenAI writer when no draft file is supplied" (and the draft path when supplied).
def test_finish_without_draft_calls_writer_and_with_draft_does_not(monkeypatch):
    folder = _prepared(monkeypatch)
    _cv_renderer(monkeypatch)
    fake = _openai(monkeypatch)
    assert apply.finish(folder) == 0
    assert len(fake.of(CoverLetterDraft)) >= 1


# Scope: a supplied draft file that cannot be read stops --finish loudly, before any LLM call.
def test_finish_with_a_missing_draft_file_fails_before_any_llm_call(monkeypatch, tmp_path):
    folder = _prepared(monkeypatch)
    _cv_renderer(monkeypatch)
    fake = _openai(monkeypatch)

    assert apply.finish(folder, tmp_path / "no_such_draft.txt") == apply.EXIT_FAILED
    assert fake.calls == []
    assert not (folder / "cv.pdf").exists()


# Done when: "cv.pdf is written next to cv.docx on a completed Application and is non-empty".
def test_completed_application_has_cv_pdf_next_to_cv_docx_and_verifies(monkeypatch, capsys):
    folder = _prepared(monkeypatch)
    _cv_renderer(monkeypatch)
    _openai(monkeypatch)

    assert apply.finish(folder, _draft(folder)) == 0

    assert _run_json(folder)["status"] == "completed"
    assert (folder / "cv.pdf").parent == (folder / "cv.docx").parent
    assert (folder / "cv.pdf").stat().st_size > 0
    assert real_verify(folder, apply.load_facts(None), check_pages=False) == []


# Scope: "if conversion fails, --finish fails loudly rather than leaving no PDF".
def test_conversion_failure_is_loud_and_the_application_is_not_verified(monkeypatch, capsys):
    folder = _prepared(monkeypatch)
    _openai(monkeypatch)

    def failing_conversion(*_a, **_k):
        raise RuntimeError("PDF conversion failed: no converter")

    monkeypatch.setattr(apply, "generate_cv", failing_conversion)

    assert apply.finish(folder, _draft(folder)) == apply.EXIT_FAILED
    assert "PDF conversion failed" in capsys.readouterr().out  # printed, not swallowed
    assert _run_json(folder)["status"] == "failed"
    assert not (folder / "cv.pdf").exists()
    assert real_verify(folder, apply.load_facts(None), check_pages=False) != []


# Done when: finish must not report success when the PDF is absent or empty.
@pytest.mark.parametrize("pdf", [None, b""], ids=["missing", "empty"])
def test_finish_is_not_ok_when_cv_pdf_is_missing_or_empty(monkeypatch, capsys, pdf):
    folder = _prepared(monkeypatch)
    _cv_renderer(monkeypatch, pdf=pdf)
    _openai(monkeypatch)

    assert apply.finish(folder, _draft(folder)) == apply.EXIT_UNVERIFIED
    assert "cv.pdf" in capsys.readouterr().out


# Done when: "verify_application check 1 ... include it, with a test that fails when it is missing".
def test_verify_application_fails_when_cv_pdf_is_missing(tmp_path, facts):
    folder = make_folder(tmp_path)
    assert real_verify(folder, facts, check_pages=False) == []

    (folder / "cv.pdf").unlink()

    assert "cv.pdf is missing" in real_verify(folder, facts, check_pages=False)


def test_verify_application_fails_when_cv_pdf_is_empty(tmp_path, facts):
    folder = make_folder(tmp_path)
    (folder / "cv.pdf").write_bytes(b"")

    assert any("cv.pdf" in f and "empty" in f for f in real_verify(folder, facts, check_pages=False))


# Done when: "SPEC.md (Application = four files) ... updated to include it" -- now five files.
def test_spec_md_lists_cv_pdf_and_says_five_files_not_four():
    text = (ROOT / "SPEC.md").read_text(encoding="utf-8")
    application_line = next(l for l in text.splitlines() if l.startswith("- **Application**"))

    assert "cv.pdf" in application_line
    assert "the five files exist" in text
    assert "four files" not in text
