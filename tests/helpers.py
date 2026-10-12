import json


NAME = "2026-08-17_Acme_Engineer"
GOOD_LETTER = "Dear team,\n\nI did thing one at Acme Corp.\n\nBest regards,\nTest Person"


def make_folder(tmp_path, name=NAME, status="completed", declined=False):
    folder = tmp_path / name
    folder.mkdir()
    (folder / "jd.txt").write_text("A job description.", encoding="utf-8")
    (folder / "run.json").write_text(
        json.dumps({"status": "declined" if declined else status}), encoding="utf-8"
    )

    if not declined:
        (folder / "cover_letter.txt").write_text(GOOD_LETTER, encoding="utf-8")
        (folder / "cv.docx").write_bytes(b"PK fake docx")

    return folder
