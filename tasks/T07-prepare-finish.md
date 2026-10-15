# T07: apply --prepare / --finish

Spec: Phase 3 seam. Depends on: T06, T03.

## Start of session
Read `CLAUDE.md`, `SPEC.md`, `DECISIONS.md`, then this file. Do only this task.

## Scope
`apply.py --prepare` parses, matches, applies the gate and writes a brief file; `--finish` runs validators, evaluator, CV generation and verify. Uses the OpenAI writer when no draft file is supplied. `--finish` also saves the finished CV as `cv.pdf` in the Application folder, using the PDF `convert_to_pdf` already produces for the page check (owner request); if conversion fails, `--finish` fails loudly rather than leaving no PDF.

## Done when
- Both steps testable independently; `/apply` skill updated to drive them.
- `cv.pdf` is written next to `cv.docx` on a completed Application and is non-empty. `SPEC.md` (Application = four files) and `verify_application` check 1 are updated to include it, with a test that fails when it is missing.
- Full test suite green (`OPENAI_API_KEY=test pytest --ignore=_legacy`).
- Committed with a message naming this task.
- `DECISIONS.md` updated: one bullet under "Rebuild log" for anything the code or git history does not show, or "no new decisions" in the Result.
- A "Result" note appended below (what was built, anything surprising).

## Out of scope
Everything not listed above; protected areas in `CLAUDE.md` (scoring weights, thresholds, `cv/` unless named).

## Result
Done.
- `apply.py` is back at the repo root: `--prepare <jd> [--force]`, `--finish <folder> [--draft <file>]`, and the bare `<jd>` form running both. Exit codes: 0 ok, 1 failed, 2 unverified/bad draft, 3 weak match.
- `pipeline.py` gained `run_prepare` / `run_finish` (stage list split; `run_pipeline` unchanged in behaviour). A draft is evaluated once and never retried there.
- `--prepare` writes `jd.txt`, `brief.md` (`control_plane/brief.py`, rules imported from `guidelines.py`), `state.json` and `run.json` (`prepared`). Weak match without `--force`: nothing in `output/`.
- `cv.pdf`: `generate_cv` already writes it next to `cv.docx`; `--finish` fails loudly (run.json `failed`) if it raises. `verify_application` and `SPEC.md` now require it; `tests/test_verify_folder.py` fails when it is missing.
- `/apply` skill and `CLAUDE.md` updated. 443 tests green.
- Surprising: the PreToolUse hook (T04) blocks shell commands that mention the letter filename next to a write operator, including my own edit scripts; used Write/Edit instead. The real CV render and a live OpenAI run are not exercised here (T08).
