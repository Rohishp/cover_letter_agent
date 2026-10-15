import json

from docx import Document

from verify_application import verify_application as _verify


NAME = "2026-08-17_Acme_Engineer"
GOOD_LETTER = "Dear team,\n\nI did thing one at Acme Corp.\n\nBest regards,\nTest Person"


def make_folder(tmp_path, name=NAME, status="completed", declined=False):
    folder = tmp_path / name
    folder.mkdir(parents=True)
    (folder / "jd.txt").write_text("A job description.", encoding="utf-8")
    (folder / "run.json").write_text(
        json.dumps({"status": "declined" if declined else status}), encoding="utf-8"
    )

    if not declined:
        (folder / "cover_letter.txt").write_text(GOOD_LETTER, encoding="utf-8")
        Document().save(str(folder / "cv.docx"))
        (folder / "cv.pdf").write_bytes(b"%PDF-1.4 test")

    return folder


def verify_application(folder, facts):
    """verify_application without the docx-to-PDF render, which needs Word or LibreOffice."""

    return _verify(folder, facts, check_pages=False)
