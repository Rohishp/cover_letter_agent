# T05: SubagentStop hook runs verify

Spec: Phase 2. Depends on: T03, T04.

## Start of session
Read `CLAUDE.md`, `SPEC.md`, `DECISIONS.md`, then this file. Do only this task.

## Scope
SubagentStop hook that runs `verify_application` on the application folder the sub-agent touched and reports failures back.

## Done when
- Demonstrated once with a deliberately broken folder and once with a clean one.
- Full test suite green (`OPENAI_API_KEY=test pytest --ignore=_legacy`).
- Committed with a message naming this task.
- A "Result" note appended below (what was built, anything surprising).

## Out of scope
Everything not listed above; protected areas in `CLAUDE.md` (scoring weights, thresholds, `cv/` unless named).

## Result
(not started)
