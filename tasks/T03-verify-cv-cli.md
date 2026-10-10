# T03: verify_application: CV check and CLI

Spec: Phase 1, check 5 and CLI. Depends on: T02.

## Start of session
Read `CLAUDE.md`, `SPEC.md`, `DECISIONS.md`, then this file. Do only this task.

## Scope
CV check: render `cv.docx` to PDF with `cv.checks.convert_to_pdf`, require <= 2 pages and no placeholders. Add `python verify_application.py <folder>`: prints failures, exit 0 clean / 2 failures.

## Done when
- Tests for >2 pages, placeholder in CV, and both exit codes. Run it on one real old Application folder and record the result.
- Full test suite green (`OPENAI_API_KEY=test pytest --ignore=_legacy`).
- Committed with a message naming this task.
- A "Result" note appended below (what was built, anything surprising).

## Out of scope
Everything not listed above; protected areas in `CLAUDE.md` (scoring weights, thresholds, `cv/` unless named).

## Result
(not started)
