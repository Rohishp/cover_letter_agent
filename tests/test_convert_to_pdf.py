import subprocess
import sys
import types

import pytest

from cv import checks

WRITE = "write"
WRITE_THEN_RAISE = "write then raise"
NOTHING = "nothing"


def _fake_word(monkeypatch, behaviours):
    """One behaviour per Word call (the last repeats): WRITE, WRITE_THEN_RAISE, NOTHING or an Exception."""
    calls = []

    def convert(src, dst):
        calls.append(src)
        behaviour = behaviours[min(len(calls), len(behaviours)) - 1]

        if isinstance(behaviour, Exception):
            raise behaviour
        if behaviour in (WRITE, WRITE_THEN_RAISE):
            open(dst, "wb").write(b"%PDF new")
        if behaviour == WRITE_THEN_RAISE:
            raise OSError("RPC server unavailable (COM cleanup)")

    monkeypatch.setitem(sys.modules, "docx2pdf", types.SimpleNamespace(convert=convert))
    monkeypatch.setattr(checks, "WORD_RETRY_PAUSE_SECONDS", 0)
    monkeypatch.setattr(checks.shutil, "which", lambda name: None)
    return calls


def _fake_soffice(monkeypatch, run):
    monkeypatch.setattr(checks.shutil, "which", lambda name: "soffice")
    monkeypatch.setattr(checks.subprocess, "run", run)


def test_retries_once_after_a_dropped_word_connection(monkeypatch, tmp_path):
    calls = _fake_word(monkeypatch, [OSError("RPC server unavailable"), WRITE])
    pdf, detail = checks.convert_to_pdf(tmp_path / "cv.docx")

    assert pdf == tmp_path / "cv.pdf" and "MS Word" in detail
    assert len(calls) == 2


def test_failure_message_names_the_real_word_error(monkeypatch, tmp_path):
    calls = _fake_word(monkeypatch, [OSError("RPC server unavailable")])
    pdf, detail = checks.convert_to_pdf(tmp_path / "cv.docx")

    assert pdf is None
    assert "OSError: RPC server unavailable" in detail
    assert "soffice is not installed" in detail
    assert len(calls) == checks.WORD_ATTEMPTS


def test_error_text_is_one_line_and_clipped(monkeypatch, tmp_path):
    _fake_word(monkeypatch, [OSError("line one\n" + "x" * 1000)])
    _, detail = checks.convert_to_pdf(tmp_path / "cv.docx")

    assert "\n" not in detail
    assert len(detail) < checks.ERROR_DETAIL_MAX_CHARS + 100


def test_a_pdf_written_before_word_raised_is_used(monkeypatch, tmp_path):
    calls = _fake_word(monkeypatch, [WRITE_THEN_RAISE])
    pdf, detail = checks.convert_to_pdf(tmp_path / "cv.docx")

    assert pdf == tmp_path / "cv.pdf" and "MS Word" in detail
    assert len(calls) == 1


def test_word_writing_no_pdf_is_a_failure(monkeypatch, tmp_path):
    _fake_word(monkeypatch, [NOTHING])
    pdf, detail = checks.convert_to_pdf(tmp_path / "cv.docx")

    assert pdf is None and "Word wrote no PDF" in detail


def test_a_stale_pdf_is_never_returned_as_output(monkeypatch, tmp_path):
    (tmp_path / "cv.pdf").write_bytes(b"%PDF stale")
    _fake_word(monkeypatch, [NOTHING])
    pdf, _ = checks.convert_to_pdf(tmp_path / "cv.docx")

    assert pdf is None
    assert not (tmp_path / "cv.pdf").exists()


def test_missing_docx2pdf_is_not_retried_and_falls_back_to_soffice(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "docx2pdf", None)  # makes `import docx2pdf` raise ImportError
    slept = []
    monkeypatch.setattr(checks.time, "sleep", slept.append)

    def run(argv, **kwargs):
        (tmp_path / "cv.pdf").write_bytes(b"%PDF soffice")

    _fake_soffice(monkeypatch, run)
    pdf, detail = checks.convert_to_pdf(tmp_path / "cv.docx")

    assert (pdf, detail) == (tmp_path / "cv.pdf", "soffice")
    assert slept == []


def test_soffice_exiting_without_a_pdf_does_not_return_a_stale_one(monkeypatch, tmp_path):
    (tmp_path / "cv.pdf").write_bytes(b"%PDF stale")
    _fake_word(monkeypatch, [NOTHING])
    _fake_soffice(monkeypatch, lambda argv, **kwargs: None)
    pdf, detail = checks.convert_to_pdf(tmp_path / "cv.docx")

    assert pdf is None and "soffice wrote no PDF" in detail


def test_soffice_failure_is_reported_alongside_the_word_error(monkeypatch, tmp_path):
    _fake_word(monkeypatch, [OSError("RPC server unavailable")])

    def run(argv, **kwargs):
        raise subprocess.CalledProcessError(1, argv)

    _fake_soffice(monkeypatch, run)
    pdf, detail = checks.convert_to_pdf(tmp_path / "cv.docx")

    assert pdf is None
    assert "RPC server unavailable" in detail and "soffice failed (CalledProcessError" in detail
