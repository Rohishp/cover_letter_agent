import json

import pytest

from tests.test_verify_folder import GOOD_LETTER, make_folder
from verify_application import verify_application


def letter_failures(tmp_path, facts, letter, **run):
    folder = make_folder(tmp_path)
    (folder / "cover_letter.txt").write_text(letter, encoding="utf-8")

    if run:
        (folder / "run.json").write_text(json.dumps({"status": "completed", **run}), encoding="utf-8")

    return verify_application(folder, facts)


def test_good_letter_has_no_failures(tmp_path, facts):
    assert letter_failures(tmp_path, facts, GOOD_LETTER) == []


@pytest.mark.parametrize("text", ["[Company]", "{{role}}", "TODO", "<company>"])
def test_placeholder_fails(tmp_path, facts, text):
    letter = GOOD_LETTER.replace("thing one", f"thing one for {text}")

    assert any("placeholder" in f for f in letter_failures(tmp_path, facts, letter))


@pytest.mark.parametrize(
    "letter, expected",
    [
        (GOOD_LETTER.replace("Dear team,", "Hi team,"), "greeting"),
        (GOOD_LETTER.replace("Best regards,", "Cheers,"), "closing line"),
        (GOOD_LETTER.replace("Test Person", "Someone Else"), "exact name"),
    ],
)
def test_bad_structure_fails(tmp_path, facts, letter, expected):
    assert any(expected in f for f in letter_failures(tmp_path, facts, letter))


def test_hedge_disclosure_fails(tmp_path, facts):
    letter = GOOD_LETTER.replace("I did", "I don't have experience with X, but I did")

    assert any("hedge phrase" in f for f in letter_failures(tmp_path, facts, letter))


def test_fabricated_employer_fails(tmp_path, facts):
    letter = GOOD_LETTER.replace("I did thing one at Acme Corp.", "As Lead Engineer at Fakecorp, I did it.")

    assert any("fabricated employer" in f for f in letter_failures(tmp_path, facts, letter))


def test_target_company_from_run_json_is_allowed(tmp_path, facts):
    letter = GOOD_LETTER.replace("I did thing one at Acme Corp.", "At Newco, I would help.")

    assert letter_failures(tmp_path, facts, letter, company_name="Newco") == []


def test_fabricated_role_claim_fails(tmp_path, facts):
    letter = GOOD_LETTER.replace("I did thing one at Acme Corp.", "In my role as Chief Wizard, I did it.")

    assert any("fabricated role claim" in f for f in letter_failures(tmp_path, facts, letter))


def test_declined_jd_skips_letter_checks(tmp_path, facts):
    assert verify_application(make_folder(tmp_path, declined=True), facts) == []
