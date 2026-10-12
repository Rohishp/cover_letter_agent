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
Added to `verify_application.py`: `_check_cv` (placeholders in body, tables, headers and footers of `cv.docx`; page count via `cv.checks.convert_to_pdf` on a temp copy so no PDF lands in the folder; fails above 2 pages) and the CLI `python verify_application.py <folder>`: prints failures, exit 0 clean (prints `OK`), 2 failures, 1 could not run (bad usage or unloadable `input/cv_facts.yaml`). Tests: `tests/test_verify_cv.py`, `tests/test_verify_cli.py` (written by test-writer). Suite: 297 passed, 1 skipped.

Surprising / owner choices:
- No converter: owner chose fail closed (`cv.docx: page count not checked, ...`), so Applications fail verification on a machine without Word or LibreOffice.
- New `check_pages=True` keyword on `verify_application`. Tests for folder/letter checks use `tests/helpers.verify_application` (`check_pages=False`) so they do not render a docx; `make_folder` now writes a real empty docx.
- CLI also takes `--facts <path>` (tests use a temp copy of the fixture, so no private `input/cv_facts.yaml` is needed); a fact-base load error prints only field paths and error types, never values. A symlinked file in the folder is a failure. A render error fails closed (`render failed (<ErrName>)`).
- Page-count tests stand in for `convert_to_pdf` with a real N-page PDF; one smoke test uses the real converter and skips without one.
- Not fixed (review): `docx2pdf` has no timeout, but it lives in `cv/checks.py`, which is protected; and the CLI does not restrict the folder to `output/applications/` (it would break running on any folder).
- Word via docx2pdf is flaky here (a first probe returned no converter, and a fatal `0x800706ba` COM error shows in output while tests still pass). Running two pytest processes at once makes it worse.
- Not done: the run on one real old Application folder. `output/applications/` does not exist in this checkout; do it on the first real run (T08).
