# cover_letter_agent

Personal tool. Takes a job description, matches it against a parsed CV, and writes a tailored
cover letter only when the match is strong enough. Runs locally and on AWS Lambda.

## Architecture

`run_pipeline(cv_path, jd_text) -> CoverLetterState` in `pipeline.py` holds all business logic
and knows nothing about its caller. `lambda_handler.py` and `invoke_pipeline.py` are thin
wrappers around it.

```
agents/          one function per LLM call (cv_parser, jd_parser, matcher,
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
  parsers) run at `temperature=0`; only the writer may run higher.
- Rule text lives in one place and is imported. Do not paste a rule into a prompt string.
- Keep new code compact. The existing `pipeline.py` is unusually spread out; do not copy that
  style into new files.

## Do not touch without asking

- Scoring weights and strength points in `control_plane/scoring.py`
- Thresholds: `MATCH_BASE_THRESHOLD`, `MATCH_CORE_THRESHOLD`, `EVAL_PASS_THRESHOLD`
- The S3 / Lambda deployment path
- Anything CV-generation related (not built yet, separate project)

## Running it

```
python invoke_pipeline.py          # reads the JD from the clipboard, invokes Lambda
```

Requires `.env` with `OPENAI_API_KEY` and working AWS credentials.

## Secrets

`.env` is gitignored and must stay that way. Never print, echo, commit or include the API key
in any output. Never add real job descriptions or CV content to the repo — `input/` and
`output/` are gitignored for that reason.
