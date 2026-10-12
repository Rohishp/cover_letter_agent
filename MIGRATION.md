# Rebuild notes

Started from `cover_letter_agent` (commit c60105b). Only the parts that hold the
pipeline's trust were carried over. 198 tests pass here (`OPENAI_API_KEY=test pytest --ignore=_legacy`).

## Carried over, unchanged
- `cv/` (fact base, selector, rendering, page fit, containment) and `input/cv_facts.yaml` (personal, gitignored)
- `guidelines.py`, `models/`
- `agents/`: jd_parser, matcher, fact_render, cover_letter_writer (fallback until the sub-agent exists), evaluator
- `control_plane/`: scoring, thresholds, match_diagnostics, match_validation, quality_gates, jd_cache,
  eval_validation, cover_letter_containment, fact_base_coverage, application_paths, storage
- `.claude/skills/apply`, `CLAUDE.md` invariants, and the tests for all of the above

## In `_legacy/` for reference only (not imported)
`apply.py`, `control_plane/reporting.py`, their tests (`pipeline.py` was rebuilt in T06).

## Known facts worth keeping
- gpt-4o at temperature 0 still flips on vague core requirements (core score moves up to 13 points). A 3-run median did not help. Do not rebuild consensus matching; decompose vague requirements or let the user tag them.
- `EVAL_PASS_THRESHOLD` (70) was tuned on the PDF-parsed CV; recalibrate against the fact base.

## Next
1. `verify_application.py` and hooks.
2. Cover-letter and CV sub-agents; the user writes their skills with `/writing-for-agents`.
3. `apply.py` around the rebuilt `pipeline.py` (T07).
