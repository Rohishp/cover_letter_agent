# T02: verify_application: letter checks

Spec: Phase 1, checks 3, 4. Depends on: T01.

## Start of session
Read `CLAUDE.md`, `SPEC.md`, `DECISIONS.md`, then this file. Do only this task.

## Scope
Extend `verify_application` with letter checks by calling existing functions: placeholder scan, `check_letter_structure`, `check_hedge_disclosure`, `check_fabricated_employer`, `check_fabricated_role_claim` against the fact base.

## Done when
- One failing-folder test per check in `tests/test_verify_letter.py`; a good real letter returns `[]`.
- Full test suite green (`OPENAI_API_KEY=test pytest --ignore=_legacy`).
- Committed with a message naming this task.
- A "Result" note appended below (what was built, anything surprising).

## Out of scope
Everything not listed above; protected areas in `CLAUDE.md` (scoring weights, thresholds, `cv/` unless named).

## Result
Added letter checks to `verify_application` (skipped for Declined JDs): placeholder scan (`[...]`, `{{`, `TODO`, `<...>`), `check_letter_structure`, `check_hedge_disclosure`, `check_fabricated_employer`, `check_fabricated_role_claim`. Tests in `tests/test_verify_letter.py`. Suite: 236 passed.

Surprising / owner choices:
- `check_letter_structure` needs a `CoverLetterDraft`, but a folder holds only the final text. Owner chose a split check: greeting, closing line and exact-name final line are checked here; the "at least one factual paragraph" rule is NOT checked (a one-paragraph factual draft is passed to satisfy the signature) and stays enforced in the writer.
- Target company allowed in "at <Company>" claims is read from `run.json` `company_name`; the T07 writer must emit it. Without it, such a line is flagged.
- Employer/title helpers are imported from `agents/cover_letter_writer.py` (private `_real_*` names).
- "A good real letter returns []" is covered by a synthetic letter only; not yet run on a real Application folder.
