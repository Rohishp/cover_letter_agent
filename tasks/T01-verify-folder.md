# T01: verify_application: folder, files, run.json

Spec: Phase 1, checks 1, 2, 6. Depends on: none.

## Start of session
Read `CLAUDE.md`, `SPEC.md`, `DECISIONS.md`, then this file. Do only this task.

## Scope
`verify_application.py` with `verify_application(folder, facts) -> list[str]`. Implement ONLY: folder-name pattern, four files exist and are non-empty, `run.json` parses with `status == "completed"`, Declined JD detection (skip later checks).

## Done when
- One test per check in `tests/test_verify_folder.py`, each building a broken folder in `tmp_path`; a good folder returns `[]`; no LLM call.
- Full test suite green (`OPENAI_API_KEY=test pytest --ignore=_legacy`).
- Committed with a message naming this task.
- A "Result" note appended below (what was built, anything surprising).

## Out of scope
Everything not listed above; protected areas in `CLAUDE.md` (scoring weights, thresholds, `cv/` unless named).

## Result
(not started)
