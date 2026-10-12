"""Spec-derived tests for T02 (SPEC.md Phase 1, checks 3-4): letter checks in verify_application."""
import json

import pytest

from helpers import GOOD_LETTER, make_folder, verify_application

REALISTIC_LETTER = (
    "Dear team,\n\n"
    "I was a Senior Thing Doer at Acme Corp (2020-2022), where I did thing one -- "
    "and thing three with a 10x speedup; it taught me a lot.\n\n"
    "Earlier, at Beta Inc, I helped with thing A: a small, useful task.\n\n"
    "Best regards,\nTest Person"
)


def failures(tmp_path, facts, letter, **run):
    folder = make_folder(tmp_path)
    (folder / "cover_letter.txt").write_text(letter, encoding="utf-8")

    if run:
        (folder / "run.json").write_text(json.dumps({"status": "completed", **run}), encoding="utf-8")

    return verify_application(folder, facts)


def has(found, needle):
    return any(needle in f for f in found)


def test_realistic_punctuation_letter_is_clean(tmp_path, facts):
    assert failures(tmp_path, facts, REALISTIC_LETTER) == []


def test_good_letter_is_stable_across_runs(tmp_path, facts):
    folder = make_folder(tmp_path)

    assert verify_application(folder, facts) == verify_application(folder, facts) == []


@pytest.mark.parametrize("bad", ["[Hiring Manager]", "[insert date]", "{{company}}", "{{ role }}", "TODO: fix", "<company>"])
def test_placeholder_variants_fail_in_isolation(tmp_path, facts, bad):
    found = failures(tmp_path, facts, GOOD_LETTER.replace("thing one", f"thing one {bad}"))

    assert has(found, "placeholder")
    assert not has(found, "fabricated employer")
    assert not has(found, "fabricated role claim")


def test_placeholder_in_greeting_is_reported(tmp_path, facts):
    assert has(failures(tmp_path, facts, GOOD_LETTER.replace("Dear team,", "Dear [Name],")), "placeholder")


@pytest.mark.parametrize(
    "letter, expected",
    [
        (GOOD_LETTER.replace("Dear team,\n\n", ""), "greeting"),
        (GOOD_LETTER.replace("Dear team,", "Hello,"), "greeting"),
        (GOOD_LETTER.replace("Best regards,\n", ""), "closing line"),
        (GOOD_LETTER.replace("Best regards,", "Thanks,"), "closing line"),
        (GOOD_LETTER.replace("Test Person", "Test"), "exact name"),
        (GOOD_LETTER.replace("Test Person", "test person"), "exact name"),
    ],
)
def test_structure_variants_fail(tmp_path, facts, letter, expected):
    assert has(failures(tmp_path, facts, letter), expected)


@pytest.mark.parametrize("phrase", ["I don't have experience with", "I have no experience with"])
def test_hedge_variants_fail_or_are_documented(tmp_path, facts, phrase):
    # Only the first phrase is known from the spec'd behaviour; the second is an
    # open question, so only assert the known one.
    if phrase != "I don't have experience with":
        pytest.skip("hedge phrase list not stated in the spec")

    letter = GOOD_LETTER.replace("I did", f"{phrase} X, but I did")

    assert has(failures(tmp_path, facts, letter), "hedge phrase")


@pytest.mark.parametrize("employer", ["Fakecorp", "Globex Industries", "Initech"])
def test_fabricated_employer_variants_fail(tmp_path, facts, employer):
    letter = GOOD_LETTER.replace("I did thing one at Acme Corp.", f"As Lead Engineer at {employer}, I did it.")

    assert has(failures(tmp_path, facts, letter), "fabricated employer")


@pytest.mark.parametrize("title", ["Chief Wizard", "Principal Architect", "Head of Everything"])
def test_fabricated_role_variants_fail(tmp_path, facts, title):
    letter = GOOD_LETTER.replace("I did thing one at Acme Corp.", f"In my role as {title}, I did it.")

    assert has(failures(tmp_path, facts, letter), "fabricated role claim")


def test_real_employer_and_real_title_are_allowed(tmp_path, facts):
    letter = GOOD_LETTER.replace(
        "I did thing one at Acme Corp.", "In my role as Senior Thing Doer at Acme Corp, I did thing one."
    )

    assert failures(tmp_path, facts, letter) == []


def test_several_failures_are_reported_together(tmp_path, facts):
    letter = (
        "Hi team,\n\n"
        "In my role as Chief Wizard, I did [thing]. As Lead Engineer at Fakecorp, I did it. I don't have experience with X, but I did.\n\n"
        "Cheers,\nSomeone Else"
    )
    found = failures(tmp_path, facts, letter)

    for needle in ("placeholder", "greeting", "closing line", "hedge phrase", "fabricated employer", "fabricated role claim"):
        assert has(found, needle), needle


def test_two_independent_failures_do_not_mask_each_other(tmp_path, facts):
    letter = GOOD_LETTER.replace("Dear team,", "Hi team,").replace("thing one", "thing one [x]")
    found = failures(tmp_path, facts, letter)

    assert has(found, "greeting") and has(found, "placeholder")
    assert not has(found, "closing line")


def test_failures_are_human_readable_strings(tmp_path, facts):
    found = failures(tmp_path, facts, GOOD_LETTER.replace("thing one", "thing one [x]"))

    assert found and all(isinstance(f, str) and f.strip() for f in found)


def test_declined_folder_skips_every_letter_check(tmp_path, facts):
    folder = make_folder(tmp_path, declined=True)
    (folder / "cover_letter.txt").write_text(
        "Hi,\n\n[Company] TODO At Fakecorp, I don't have experience with X.\n\nCheers", encoding="utf-8"
    )

    assert verify_application(folder, facts) == []
