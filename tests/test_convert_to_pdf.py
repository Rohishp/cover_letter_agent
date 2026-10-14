import sys
import types

from cv import checks


def _fake_docx2pdf(monkeypatch, behaviours):
    """behaviours: one per call; an Exception is raised, otherwise a PDF is written."""
    calls = []

    def convert(src, dst):
        calls.append(src)
        behaviour = behaviours[min(len(calls), len(behaviours)) - 1]
        if isinstance(behaviour, Exception):
            raise behaviour
        open(dst, "wb").write(b"%PDF")

    monkeypatch.setitem(sys.modules, "docx2pdf", types.SimpleNamespace(convert=convert))
    monkeypatch.setattr(checks, "WORD_RETRY_PAUSE_SECONDS", 0)
    monkeypatch.setattr(checks.shutil, "which", lambda name: None)
    return calls


def test_retries_once_after_a_dropped_word_connection(monkeypatch, tmp_path):
    calls = _fake_docx2pdf(monkeypatch, [OSError("RPC server unavailable"), "ok"])
    pdf, detail = checks.convert_to_pdf(tmp_path / "cv.docx")

    assert pdf == tmp_path / "cv.pdf" and "MS Word" in detail
    assert len(calls) == 2


def test_failure_message_names_the_real_word_error(monkeypatch, tmp_path):
    calls = _fake_docx2pdf(monkeypatch, [OSError("RPC server unavailable")])
    pdf, detail = checks.convert_to_pdf(tmp_path / "cv.docx")

    assert pdf is None
    assert "OSError: RPC server unavailable" in detail
    assert len(calls) == checks.WORD_ATTEMPTS
