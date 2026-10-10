# T04: PreToolUse hook on writes

Spec: Phase 2. Depends on: T02.

## Start of session
Read `CLAUDE.md`, `SPEC.md`, `DECISIONS.md`, then this file. Do only this task.

## Scope
Hook script + `.claude/settings.json` entry: on Write/Edit under `output/applications/**`, run the cheap letter checks on the new content; exit 2 with the failures on a bad write. Load the `update-config` skill for settings.

## Done when
- A deliberately bad write is blocked in a real session; a clean write is not. Unit test the script's decision function.
- Full test suite green (`OPENAI_API_KEY=test pytest --ignore=_legacy`).
- Committed with a message naming this task.
- A "Result" note appended below (what was built, anything surprising).

## Out of scope
Everything not listed above; protected areas in `CLAUDE.md` (scoring weights, thresholds, `cv/` unless named).

## Result
(not started)
