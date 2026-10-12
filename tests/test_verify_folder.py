import json

import pytest

from helpers import NAME, make_folder
from verify_application import verify_application


def test_good_application_has_no_failures(tmp_path, facts):
    assert verify_application(make_folder(tmp_path), facts) == []


def test_good_declined_jd_has_no_failures(tmp_path, facts):
    assert verify_application(make_folder(tmp_path, declined=True), facts) == []


@pytest.mark.parametrize("name", ["Acme_Engineer", "2026-13-40_Acme_Engineer", "2026-08-17_Acme"])
def test_bad_folder_name_fails(tmp_path, facts, name):
    failures = verify_application(make_folder(tmp_path, name=name), facts)

    assert any("folder name" in f for f in failures)


def test_collision_suffix_name_is_accepted(tmp_path, facts):
    assert verify_application(make_folder(tmp_path, name=NAME + "_2"), facts) == []


@pytest.mark.parametrize("filename", ["cover_letter.txt", "cv.docx", "jd.txt", "run.json"])
def test_missing_file_fails(tmp_path, facts, filename):
    folder = make_folder(tmp_path)
    (folder / filename).unlink()

    failures = verify_application(folder, facts)

    assert f"{filename} is missing" in failures


@pytest.mark.parametrize("filename", ["cover_letter.txt", "cv.docx", "jd.txt", "run.json"])
def test_empty_file_fails(tmp_path, facts, filename):
    folder = make_folder(tmp_path)
    (folder / filename).write_bytes(b"")

    failures = verify_application(folder, facts)

    assert any(filename in f and "empty" in f for f in failures)


def test_whitespace_only_jd_fails(tmp_path, facts):
    folder = make_folder(tmp_path)
    (folder / "jd.txt").write_text("  \n", encoding="utf-8")

    assert "jd.txt is empty" in verify_application(folder, facts)


def test_invalid_run_json_fails(tmp_path, facts):
    folder = make_folder(tmp_path)
    (folder / "run.json").write_text("{not json", encoding="utf-8")

    failures = verify_application(folder, facts)

    assert any("run.json is not valid JSON" in f for f in failures)


@pytest.mark.parametrize("status", ["failed", "rejected", None])
def test_non_completed_status_fails(tmp_path, facts, status):
    folder = make_folder(tmp_path)
    (folder / "run.json").write_text(
        json.dumps({} if status is None else {"status": status}), encoding="utf-8"
    )

    failures = verify_application(folder, facts)

    assert any("expected 'completed'" in f for f in failures)


def test_declined_jd_skips_letter_and_cv_checks(tmp_path, facts):
    folder = make_folder(tmp_path, declined=True)

    assert not (folder / "cover_letter.txt").exists()
    assert verify_application(folder, facts) == []


def test_declined_jd_still_requires_jd(tmp_path, facts):
    folder = make_folder(tmp_path, declined=True)
    (folder / "jd.txt").unlink()

    assert "jd.txt is missing" in verify_application(folder, facts)


def test_non_utf8_text_file_is_reported_not_raised(tmp_path, facts):
    folder = make_folder(tmp_path)
    (folder / "jd.txt").write_bytes(b"\xff\xfe\x00bad")

    assert "jd.txt is unreadable" in verify_application(folder, facts)


@pytest.mark.parametrize("content", ["[]", '{"status": 1}'])
def test_run_json_wrong_shape_fails(tmp_path, facts, content):
    folder = make_folder(tmp_path)
    (folder / "run.json").write_text(content, encoding="utf-8")

    failures = verify_application(folder, facts)

    assert any("not a JSON object" in f or "expected 'completed'" in f for f in failures)


def test_overlong_or_malformed_component_fails(tmp_path, facts):
    for name in ("2026-08-17_" + "A" * 41 + "_Engineer", "2026-08-17_-Acme_Engineer", "2026-08-17_Ac--me_Engineer"):
        failures = verify_application(make_folder(tmp_path, name=name), facts)

        assert any("folder name" in f for f in failures), name
