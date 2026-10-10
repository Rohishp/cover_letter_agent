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

## Removed / retired
- AWS: `lambda_handler.py`, `invoke_pipeline.py`, S3/boto3 storage.
- `run_local.py`, `scripts/measure_variance.py` (could no longer write a letter).
- `match_consensus.py`, `cover_letter_storage.py`, `agents/cv_parser.py`, `models/cv_schema.py`, `state.storage_backend`.
- The owner's earlier refactor removed (not restored): advisory containment check, CV-profile banned-phrase list and its test.

## Known problems at handover
1. New pipeline never run against OpenAI end to end (only mocked tests).
2. Matcher noise near thresholds.
3. `EVAL_PASS_THRESHOLD` uncalibrated against the fact base; a gpt-4o judge grades gpt-4o output.
4. No post-run verification of the output folder yet.
5. Dead code left in old `state.py`; six separate OpenAI clients.

## Open questions
See SPEC.md "Open questions".
