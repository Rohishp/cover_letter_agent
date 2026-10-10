# T08: First live end-to-end run and evaluator calibration

Spec: Known risk. Depends on: T07.

## Start of session
Read `CLAUDE.md`, `SPEC.md`, `DECISIONS.md`, then this file. Do only this task.

## Scope
Owner copies `.env`. Run `/apply` on 3 real JDs. Record eval scores; decide whether `EVAL_PASS_THRESHOLD` (owner approval needed) still fits.

## Done when
- Three verified Applications; scores and the decision recorded in DECISIONS.md.
- Full test suite green (`OPENAI_API_KEY=test pytest --ignore=_legacy`).
- Committed with a message naming this task.
- A "Result" note appended below (what was built, anything surprising).

## Out of scope
Everything not listed above; protected areas in `CLAUDE.md` (scoring weights, thresholds, `cv/` unless named).

## Result
(not started)
