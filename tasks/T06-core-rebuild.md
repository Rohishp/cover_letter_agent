# T06: Rebuild orchestration around kept modules

Spec: Phase 4. Depends on: T01.

## Start of session
Read `CLAUDE.md`, `SPEC.md`, `DECISIONS.md`, then this file. Do only this task.

## Scope
Replace `_legacy/pipeline.py` with a small stage list; slim `state.py` (drop dead functions); one shared OpenAI client. Behaviour must match legacy. Do not touch scoring weights or thresholds.

## Done when
- Legacy pipeline tests ported and green without mocking internals; `_legacy/pipeline.py` deleted.
- Full test suite green (`OPENAI_API_KEY=test pytest --ignore=_legacy`).
- Committed with a message naming this task.
- `DECISIONS.md` updated: one bullet under "Rebuild log" for anything the code or git history does not show, or "no new decisions" in the Result.
- A "Result" note appended below (what was built, anything surprising).

## Out of scope
Everything not listed above; protected areas in `CLAUDE.md` (scoring weights, thresholds, `cv/` unless named).

## Result
(not started)
