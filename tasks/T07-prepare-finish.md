# T07: apply --prepare / --finish

Spec: Phase 3 seam. Depends on: T06, T03.

## Start of session
Read `CLAUDE.md`, `SPEC.md`, `DECISIONS.md`, then this file. Do only this task.

## Scope
`apply.py --prepare` parses, matches, applies the gate and writes a brief file; `--finish` runs validators, evaluator, CV generation and verify. Uses the OpenAI writer when no draft file is supplied.

## Done when
- Both steps testable independently; `/apply` skill updated to drive them.
- Full test suite green (`OPENAI_API_KEY=test pytest --ignore=_legacy`).
- Committed with a message naming this task.
- A "Result" note appended below (what was built, anything surprising).

## Out of scope
Everything not listed above; protected areas in `CLAUDE.md` (scoring weights, thresholds, `cv/` unless named).

## Result
(not started)
