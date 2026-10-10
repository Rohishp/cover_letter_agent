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
Built `verify_application.py` (folder-name pattern incl. real-date check, required files present and non-empty, `run.json` parses with `status == "completed"`, Declined JD via `status == "declined"` checks only `jd.txt` + `run.json`) and `tests/test_verify_folder.py` (21 tests, no LLM). Suite: 219 passed. `facts` is unused until T02.

Surprising: legacy `apply.py` writes `run.json` with no `status` key (only `rejection_reason`/`failure_reason`), so real legacy folders fail the status check until the T07 writer emits `status` (`completed` / `declined`). Owner chose this over inferring status.
