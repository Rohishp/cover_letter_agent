# T10: CV headline/profile sub-agent

Spec: Phase 3. Depends on: T09.

## Start of session
Read `CLAUDE.md`, `SPEC.md`, `DECISIONS.md`, then this file. Do only this task.

## Scope
Only after SPEC open question 4 is answered. Sub-agent writes headline and profile only; `cv/` checks validate; Python renders.

## Done when
- Three real JDs verified; `cv/` selection and rendering untouched.
- Full test suite green (`OPENAI_API_KEY=test pytest --ignore=_legacy`).
- Committed with a message naming this task.
- `DECISIONS.md` updated: one bullet under "Rebuild log" for anything the code or git history does not show, or "no new decisions" in the Result.
- A "Result" note appended below (what was built, anything surprising).

## Out of scope
Everything not listed above; protected areas in `CLAUDE.md` (scoring weights, thresholds, `cv/` unless named).

## Result
(not started)
