# T09: Letter sub-agent

Spec: Phase 3. Depends on: T08.

## Start of session
Read `CLAUDE.md`, `SPEC.md`, `DECISIONS.md`, then this file. Do only this task.

## Scope
Owner writes the skill with `/writing-for-agents`. Create the agent definition, wire it into `/apply` between prepare and finish, retries capped at 2 and counted in `run.json`.

## Done when
- Three real JDs produce verified Applications with no manual edits; the OpenAI writer remains fallback.
- Full test suite green (`OPENAI_API_KEY=test pytest --ignore=_legacy`).
- Committed with a message naming this task.
- A "Result" note appended below (what was built, anything surprising).

## Out of scope
Everything not listed above; protected areas in `CLAUDE.md` (scoring weights, thresholds, `cv/` unless named).

## Result
(not started)
