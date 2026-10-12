import json

import pytest

from helpers import GOOD_LETTER, make_folder, verify_application


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


ORG_LED_LETTER = GOOD_LETTER.replace("I did thing one at Acme Corp.", "I did thing one at Acme Corp.\n\nAt Newco, I would help.")


def test_target_company_from_run_json_is_allowed(tmp_path, facts):
    assert letter_failures(tmp_path, facts, ORG_LED_LETTER, company_name="Newco") == []


@pytest.mark.parametrize("run", [{}, {"company_name": None}, {"company_name": 5}])
def test_org_led_clause_without_company_is_flagged(tmp_path, facts, run):
    assert any("fabricated employer" in f for f in letter_failures(tmp_path, facts, ORG_LED_LETTER, **run))


def test_org_led_clause_opening_a_paragraph_is_caught(tmp_path, facts):
    letter = GOOD_LETTER.replace("I did thing one at Acme Corp.", "At Fakecorp, I did it.")

    assert any("fabricated employer" in f for f in letter_failures(tmp_path, facts, letter))


def test_unreadable_letter_is_reported_once(tmp_path, facts):
    folder = make_folder(tmp_path)
    (folder / "cover_letter.txt").write_bytes(b"\xff\xfe\x00bad")

    assert verify_application(folder, facts) == ["cover_letter.txt is unreadable"]


def test_long_fragments_are_clipped(tmp_path, facts):
    letter = GOOD_LETTER.replace("thing one", "[" + "x" * 300 + "]")

    assert all(len(f) < 150 for f in letter_failures(tmp_path, facts, letter))


def test_fabricated_role_claim_fails(tmp_path, facts):
    letter = GOOD_LETTER.replace("I did thing one at Acme Corp.", "In my role as Chief Wizard, I did it.")

    assert any("fabricated role claim" in f for f in letter_failures(tmp_path, facts, letter))


def test_declined_jd_skips_letter_checks(tmp_path, facts):
    folder = make_folder(tmp_path, declined=True)
    (folder / "cover_letter.txt").write_text("[Company] TODO", encoding="utf-8")

    assert verify_application(folder, facts) == []


def test_email_in_angle_brackets_is_not_a_placeholder(tmp_path, facts):
    letter = GOOD_LETTER.replace("thing one", "thing one (reach me at <me@example.com>)")

    assert letter_failures(tmp_path, facts, letter) == []
