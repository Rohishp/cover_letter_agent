# cover_letter_agent

Personal tool. Takes a job description, matches it against a parsed CV, and writes a tailored
cover letter only when the match is strong enough. Runs locally.

## Architecture

`run_pipeline(jd_text, facts, applied_for_role) -> CoverLetterState` in `pipeline.py` holds all business logic
and knows nothing about its caller. `apply.py` is the thin
wrapper around it (the only entry point).

```
agents/          one function per LLM call (jd_parser, matcher,
                 cover_letter_writer, evaluator)
models/          Pydantic schemas for every structured output
control_plane/   deterministic code: scoring, gates, validation, caching, state, storage
```

## Invariants — do not break these

1. **The LLM never decides whether the pipeline proceeds.** It judges individual pieces of
   evidence; Python aggregates those into scores and makes every pass/fail call.
   `match.recommendation` is informational only and must never feed a gate.
2. **Parsers extract, they do not infer.** If the source text does not say it, the field is
   null. Never guess a value to fill a schema.
3. **The writer uses approved evidence only.** No invented experience, employers, numbers,
   availability, language ability or work authorisation.
4. **State is persisted after every stage transition.** Any new stage calls `save_state(state)`.
5. **Deterministic checks beat prompt instructions.** If a rule can be checked in Python,
   check it in Python — do not rely on the prompt alone. See `eval_validation.py` for the
   pattern to follow.

## Conventions

- Python 3.10, Pydantic v2, OpenAI structured outputs. No other frameworks.
- Set `temperature` explicitly on every OpenAI call. Judgment calls (matcher, evaluator,
  parsers) run at `temperature=0`; the writer is permitted to run higher but currently also
  runs at `temperature=0` -- it does not exercise that option. Changed after a real run at 0.7
  fabricated an employer ("Agentic AI"); grounding took priority over phrasing variety.
- Rule text lives in one place and is imported. Do not paste a rule into a prompt string.
- Keep new code compact. The existing `pipeline.py` is unusually spread out; do not copy that
  style into new files.

## Do not touch without asking

- Scoring weights and strength points in `control_plane/scoring.py`
- Thresholds in `control_plane/thresholds.py`: `MATCH_BASE_THRESHOLD`, `MATCH_CORE_THRESHOLD`, `EVAL_PASS_THRESHOLD`
- The existing CV generation (`cv/` and `apply.py`'s CV step): change it only when asked

## Running it

Main path: `/apply` in Claude Code. Paste the JD; it saves it to `input/jd_current.txt` and runs
`python apply.py --prepare input/jd_current.txt [--force]` then `python apply.py --finish <folder>
[--draft <file>]`, which together write `cover_letter.txt`, `cv.docx`, `cv.pdf`, `jd.txt` and `run.json`
(plus `brief.md` and `state.json` from `--prepare`) to `output/applications/<date>_<Company>_<Role>/`.
`apply.py` is the orchestrator: `--prepare` = JD parse, match, gate, CV selection, brief; `--finish` = letter
(draft, else the OpenAI writer), validators, evaluator, CV generation, `verify_application`.

```
python apply.py --prepare <jd_file> [--force]       # exit 3 = weak match, nothing saved
python apply.py --finish <folder> [--draft <file>]
python apply.py --decline <jd_file>                 # owner stopped at the gate: Declined JD folder
python apply.py <jd_file> [--force]                  # both steps, OpenAI writer
```

A weak match is the user's call: `/apply` shows the score and asks whether to continue (rerun with
`--force`) or stop. Python still computes the score and threshold; the gate is not removed.

Requires `.env` with `OPENAI_API_KEY`. Storage is the local filesystem (`data/`); AWS/Lambda/S3 was retired.

## Secrets

`.env` is gitignored and must stay that way. Never print, echo, commit or include the API key
in any output. Never add real job descriptions or CV content to the repo — `input/` and
`output/` are gitignored for that reason.
