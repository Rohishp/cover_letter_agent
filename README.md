# Job Application Agent

An agentic pipeline that takes a job description, compares it against a resume, and produces a tailored cover letter — only when the match is strong enough to justify one.

Built independently as a learning project: every core decision (architecture, schemas, gates, scoring) was designed and implemented from scratch, then iterated against real job postings.

## What it does

1. Parse a resume (PDF) into structured fields once at startup.
2. Take a job description via clipboard paste.
3. Parse the JD into structured requirements, classified into four buckets: **core must-have**, **supporting**, **eligibility constraints**, and **nice-to-have** — instead of one flat skill list.
4. Validate the parsed JD is usable (reject clearly incomplete pastes before wasting further calls).
5. Match the resume against the JD requirement-by-requirement, with the LLM judging evidence strength (`strong` / `partial` / `indirect` / `not_evidenced`) and Python deterministically aggregating those judgments into scores.
6. Gate on the deterministic scores — not on the LLM's own recommendation — before proceeding.
7. Draft a cover letter using only evidence from the parsed resume and JD.
8. Evaluate the letter against a 5-criteria rubric (hook, keyword match, proof-over-pitch, zero resume duplication, CTA), with a deterministic guardrail that caps the hook score if the letter opens with generic boilerplate regardless of what the LLM scores it.
9. Retry with evaluator feedback (max 2 retries) if the letter fails evaluation.
10. Save the accepted letter, and persist full run state to disk after every stage for crash recovery and inspection.

## Why it's built this way

The interesting engineering problem here wasn't "call an LLM" — it was **containing LLM non-determinism** so the pipeline behaves consistently on the same input:

- **Extraction vs. inference boundary.** The resume and JD parsers only record what's explicitly stated in the source text. Fields describing something the text doesn't say are left null rather than guessed — this was enforced by making every schema field's own docstring say so, and catching contradictions between the field type, its default, and its prompt instructions.
- **Deterministic gates around LLM judgment.** The LLM never decides whether the pipeline proceeds. It scores individual pieces of evidence; Python code aggregates those into thresholds and makes the pass/fail call. Early versions let the LLM's own `recommendation` field influence the gate — this caused the same JD to be accepted and rejected across identical re-runs. Removing that dependency, and computing `overall_score` in code from per-requirement evidence rather than asking the LLM for a single number, cut match-score variance roughly in half.
- **Caching the JD parse.** The requirement classification (which bucket a requirement lands in) turned out to be as noisy as the scoring itself — the same JD, parsed twice, produced different requirement splits. Caching the parsed JD (keyed by a hash of the JD text plus a parser version string) makes the requirement set stable across repeated runs on the same posting.
- **Evaluator leniency.** The evaluator initially passed cover letters with textbook-generic openings ("I am writing to express my interest in..."). Tightening the prompt alone wasn't reliable, so a deterministic check now detects known generic openings and hard-caps the hook score, independent of what the LLM scores it.
- **Nice-to-have skills as bonus-only.** Early scoring penalized missing nice-to-have requirements as if they were mandatory, which pushed genuinely strong matches under the acceptance threshold. Nice-to-have evidence now only adds to the score; it never subtracts.

## Architecture

State-centric, workflow-first pipeline with deterministic gates around LLM judgment calls:

```
parse resume (once, at startup)
        │
        ▼
paste JD → parse JD → cache → validate ──(fails)──▶ stop, report
        │
        ▼ (passes)
match resume to JD requirements → deterministic scoring
        │
        ▼
match gate ──(fails)──▶ reject, no letter generated
        │
        ▼ (passes)
draft cover letter → evaluate ──(fails, retries left)──▶ retry with feedback
        │
        ▼ (passes, or retries exhausted)
save letter + full run state
```

All state (`CoverLetterState`) is a single Pydantic object persisted to disk after every stage transition, keyed by `run_id` — so a run can be inspected or resumed after a crash.

## Project structure

```
main.py                      # orchestration: the gates live here as plain if/else logic
agents/
  cv_parser.py                # resume PDF -> ParsedCV (extraction only)
  jd_parser.py                 # JD text -> ParsedJD (extraction + requirement classification)
  matcher.py                   # ParsedCV + ParsedJD -> MatchAnalysis (evidence judgments only)
  cover_letter_writer.py        # writes/revises the letter from approved evidence
  evaluator.py                  # scores a letter against the 5-criteria rubric
models/
  cv_schema.py, jd_schema.py, match_schema.py, eval_schema.py   # Pydantic schemas
control_plane/
  state.py                      # CoverLetterState + save/load
  scoring.py                    # deterministic score aggregation from LLM evidence judgments
  match_validation.py            # enforces the matcher evaluated every requirement, unmodified
  quality_gates.py                # JD input-quality gate (fatal vs. warning)
  eval_validation.py               # deterministic guardrail on evaluator leniency
  jd_cache.py                       # content-hashed, versioned JD parse cache
```

## Current limitations

- JD input is paste-only (clipboard); URL fetching is deferred to a later phase, since real-world job pages are frequently behind login walls or JS-rendered — pasted text was the more reliable input to build against first.
- Match-score variance from LLM evidence judgments is reduced but not eliminated: identical JD/CV pairs typically land within an ~8-point band on the base score, down from ~33 points before deterministic scoring and requirement caching were introduced.
- Cover letter output is plain text; no `.docx` rendering yet.

## Stack

Python, OpenAI API (structured outputs via Pydantic schemas), Pydantic v2.

## Status

Actively developed. Next: deploying the pipeline's storage layer to AWS S3 and compute to AWS Lambda.
