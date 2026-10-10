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
(not started)
