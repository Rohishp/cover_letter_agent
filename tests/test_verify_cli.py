"""Spec-derived tests for T03 / SPEC.md Phase 1 CLI: `python verify_application.py <folder>`
prints failures; exit 0 when clean, 2 when there are failures, 1 when it cannot run.

The fact base is a temp copy of the `facts` fixture passed with --facts, so no private file is needed.
"""
import subprocess
import sys
from pathlib import Path

import pymupdf
import pytest
import yaml

from helpers import make_folder
from verify_application import main

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def facts_file(tmp_path_factory, facts):
    path = tmp_path_factory.mktemp("facts") / "cv_facts.yaml"
    path.write_text(yaml.safe_dump(facts.model_dump(mode="json")), encoding="utf-8")

    return path


def run_cli(folder, facts_file):
    return subprocess.run(
        [sys.executable, "verify_application.py", str(folder), "--facts", str(facts_file)],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
    )


def run_main(capsys, *args):
    code = main(["verify_application.py", *map(str, args)])
    captured = capsys.readouterr()

    return code, captured.out, captured.err


@pytest.fixture
def one_page_render(monkeypatch):
    def convert(docx_path):
        pdf = docx_path.with_suffix(".pdf")
        document = pymupdf.open()
        document.new_page()
        document.save(str(pdf))
        document.close()

        return pdf, "fake"

    monkeypatch.setattr("verify_application.convert_to_pdf", convert)


def test_clean_declined_folder_exits_0(tmp_path, facts_file):
    result = run_cli(make_folder(tmp_path, declined=True), facts_file)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "OK"


def test_good_application_exits_0_and_prints_ok(tmp_path, facts_file, one_page_render, capsys):
    code, out, _err = run_main(capsys, make_folder(tmp_path), "--facts", facts_file)

    assert (code, out.strip()) == (0, "OK")


@pytest.mark.parametrize("name", ["not-a-valid-name", "2026-13-45_Acme_Engineer"])
def test_bad_folder_name_exits_2_and_prints_failure(tmp_path, facts_file, name):
    result = run_cli(make_folder(tmp_path, name=name, declined=True), facts_file)

    assert result.returncode == 2
    assert name in result.stdout


def test_missing_file_exits_2_and_names_it(tmp_path, facts_file):
    folder = make_folder(tmp_path, declined=True)
    (folder / "jd.txt").unlink()
    result = run_cli(folder, facts_file)

    assert result.returncode == 2
    assert "jd.txt is missing" in result.stdout


def test_multiple_failures_are_all_printed_and_exit_2(tmp_path, facts_file, capsys):
    folder = make_folder(tmp_path, name="bad name", declined=True)
    (folder / "jd.txt").write_text("", encoding="utf-8")
    code, out, _err = run_main(capsys, folder, "--facts", facts_file)

    assert code == 2
    assert "folder name" in out and "jd.txt is empty" in out


def test_no_arguments_exits_1_with_usage(capsys):
    code, out, err = run_main(capsys)

    assert (code, out) == (1, "")
    assert "usage" in err


def test_missing_fact_base_exits_1(tmp_path, capsys):
    code, out, err = run_main(capsys, make_folder(tmp_path, declined=True), "--facts", tmp_path / "nope.yaml")

    assert (code, out) == (1, "")
    assert "cannot load" in err


def test_invalid_fact_base_error_does_not_echo_values(tmp_path, capsys):
    facts_file = tmp_path / "cv_facts.yaml"
    facts_file.write_text("meta:\n  owner: Secret Person\n  updated: not-a-date\n", encoding="utf-8")
    code, _out, err = run_main(capsys, make_folder(tmp_path / "app", declined=True), "--facts", facts_file)

    assert code == 1
    assert "Secret Person" not in err and "not-a-date" not in err
