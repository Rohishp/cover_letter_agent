# Decisions and history

What was decided, built and tried in the original `cover_letter_agent`, and why.

## Goal
Paste a JD into Claude Code CLI, get a tailored cover letter + CV in a folder named from the JD. Built in phases, one at a time (owner: "I don't want all of this done altogether").

## Decisions (owner's)
- Keep the Python pipeline; Claude Code CLI is the front door (`/apply`).
- A weak match is never auto-rejected: show score, band and gaps; the owner decides continue or stop (`--force`).
- Match against the fact base, not the PDF-parsed CV. Done.
- Retire AWS/Lambda/S3 entirely. Done.
- Keep the installed skills in the old repo for building; do not commit third-party skills.
- Restore the hedge-disclosure and generic-hook checks. Done.
- Phase 3 is option A: Claude Code sub-agents draft the letter and CV text, each with a specialised skill the owner writes with `/writing-for-agents`; Python validators remain the pass/fail gate.
- Hooks (PreToolUse before a write, verification after a sub-agent stops) are Claude-Code-only and fire only on Claude's own tool calls, not on files Python writes.
- Evaluator also reads the fact base; PDF parsing removed. Threshold value (70) unchanged but not recalibrated.
- Thresholds moved to `control_plane/thresholds.py`; values unchanged.
- Start over in `cover_letter_agent_v2`, carrying only the trusted parts (see MIGRATION.md).

## Tried and measured
- **Score variance.** The same JD gave different scores per run. Cause: gpt-4o at temperature 0 / seed 42 still flips the strength of vague core requirements ("product instincts", "UX taste") where evidence is tangential. Not the parser or the cache. Core score moved up to 13 points, base up to 8.
- **3-run median voting** (`match_consensus.py`): did not help (each call flips with p~0.4-0.5 independently). Switched to 1 run, then deleted. Do not rebuild.
- **Response:** report instead of hide. Fit band (margin to thresholds, noise margin 8), hard-gap list (core requirements not evidenced), shaky list (core requirements not judged strong).
- **Is it the smaller model?** Possibly part of it; a stronger model may reduce flips (untested). The main driver is vague requirements.
- **Fabricated employer "Agentic AI"** came from the PDF headline parsed as a title, then repeated at temperature 0.7. Fixed by grounding the writer in the fact base and running at temperature 0. See `docs/cover-letter-path-root-cause.md`.

## Rebuild log (v2, T01-T06)
Only what is not obvious from the code. Detail is in each `tasks/T0x-*.md` Result.
- **T01.** Legacy `apply.py` wrote `run.json` with no `status`, so old folders fail verification. Owner: fix at the source (T07 writer emits `completed` / `declined`), do not infer it.
- **T02.** A folder holds only the final letter text, so the "at least one factual paragraph" rule is not verified there; it stays in the writer. The allowed target company comes from `run.json` `company_name` (T07 must write it). Checked on a synthetic letter only; no real Application yet.
- **T03.** No Word/LibreOffice means the page check fails closed (owner choice). `docx2pdf` has no timeout, but `cv/checks.py` is protected. Word via docx2pdf is flaky on this machine; do not run two pytest processes at once.
- **T04.** The PreToolUse hook is fail-closed once a call targets the letter or `run.json`; its Bash rule is a heuristic (false positives when a command merely mentions the letter name), with `verify_application` as the backstop.
- **T05.** The sub-agent transcript does not exist yet when `SubagentStop` fires, so touched folders are recorded by a `PostToolUse` hook per `agent_id`. A second pass never blocks (no loops); a verifier error blocks once. In an interactive session background sub-agents hand back before the block lands, so it is only observable in a headless foreground run (`claude -p --include-hook-events`). A new hook event needs a fresh session to load.
- **T06.** `pipeline.py` is now at the repo root as a stage list. Ported tests fake only the shared OpenAI client's `parse` (dispatching on `response_format`), not pipeline internals; this needed one client in `agents/client.py`, which `cv/selector.py` now imports too (one-line change in a protected folder, behaviour-neutral). `PipelineStatus` values and persist points are unchanged. Dropped from `state.py`: `load_state`, `list_states`, `summary`, `is_terminal`, `jd_source`. `storage.read_bytes` / `list_keys` are now unused but left alone. Review follow-up: `run_pipeline` redacts `sk-...` from `state.error` (SDK errors can echo a masked key). Word/PDF: the `Windows fatal exception 0x800706ba/be` lines are pytest's faulthandler reporting COM cleanup after `word.Quit()` (conversion already succeeded); `tests/conftest.py` pauses faulthandler only around the `docx2pdf` call, so real crashes elsewhere still dump. The rare real failure ("no PDF converter available" with Word installed) was not reproduced in 20 sequential conversions. `convert_to_pdf` (`cv/checks.py`, changed at the owner's request) now deletes any old PDF first, retries Word once, accepts a PDF Word wrote even if it then raised, and reports Word's and soffice's real errors (clipped to one line).
- **T07.** `--prepare` leaves nothing in `output/` on a weak match (owner choice); stop = nothing saved, continue = rerun with `--force`, so no Declined JD folder is written yet. The prepared run (state, CV selection) is saved as `state.json` in the folder so `--finish` does not re-run the flip-prone matcher. A `--draft` gets one evaluation and no retries in Python; the retry loop (cap 2, counted in `run.json`) is T09. `run.json` is `prepared` between the steps, so a half-done folder fails `verify_application`. `cv.pdf` is the PDF `generate_cv` already makes for the page check; `verify_application` now requires it (five files). `control_plane/reporting.py` moved back from `_legacy/`. Review follow-up: `state.json` is a file on disk, so `--finish` re-checks it in Python (status `match_complete`, gate recomputed, `forced` honoured only past a failed gate, folder under `output/applications`, `run.json` `prepared` or `failed`, never `completed`). A plain-text draft has no fact-ID citations, so it gets `check_letter_text` plus `check_ungrounded_figures` (every number must appear in the fact base or JD); other claims in a draft rest on the evaluator and the owner. `--finish` with `--force` is a usage error. If CV generation fails after the letter passed evaluation, the letter stays in the folder with `run.json` `failed` (a rerun replaces it); `state.json` is never rewritten by `--finish` (it is the snapshot each rerun restarts from), while the pipeline's per-transition record stays in `data/states/<run_id>.json`.

## Removed / retired
- AWS: `lambda_handler.py`, `invoke_pipeline.py`, S3/boto3 storage.
- `run_local.py`, `scripts/measure_variance.py` (could no longer write a letter).
- `match_consensus.py`, `cover_letter_storage.py`, `agents/cv_parser.py`, `models/cv_schema.py`, `state.storage_backend`.
- The owner's earlier refactor removed (not restored): advisory containment check, CV-profile banned-phrase list and its test.

## Known problems at handover
1. New pipeline never run against OpenAI end to end (only mocked tests).
2. Matcher noise near thresholds.
3. `EVAL_PASS_THRESHOLD` uncalibrated against the fact base; a gpt-4o judge grades gpt-4o output.
4. Post-run verification exists (`verify_application`, T01-T03) with hooks (T04-T05), but has only run on synthetic folders; first real run is T08.
5. (resolved in T06) dead `state.py` code and the separate OpenAI clients.

## Open questions
See SPEC.md "Open questions".
