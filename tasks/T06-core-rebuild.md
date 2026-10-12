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
Done.
- `pipeline.py` (repo root) is a stage list: `parse_jd_stage, validate_jd, match, gate, write_and_evaluate`; each returns True to end the run, and `run_pipeline` keeps the same signature and catch-all error handling. Status values and `save_state` points match legacy. `_legacy/pipeline.py` deleted.
- `control_plane/state.py` slimmed (see DECISIONS T06). `agents/client.py` holds the one OpenAI client; the four agents and `cv/selector.py` import it.
- Legacy pipeline tests ported to `tests/test_pipeline.py` (8 tests), faking only `client.beta.chat.completions.parse`; the force-parity test now compares the writer's real request instead of mock kwargs. Added persistence and short-JD tests.
- Surprising: my first draft cited a non-existent fact ID (`exp.acme-corp`; real is `exp.acme`), and the real writer validation correctly failed the run, which is the benefit of not mocking the writer.
- Scoring weights and thresholds untouched.
