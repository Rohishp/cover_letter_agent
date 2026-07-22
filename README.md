# Job Application Agent

An agentic pipeline that takes a job description, compares it against a resume, and produces a tailored cover letter — only when the match is strong enough to justify one.

Built independently as a learning project: every core decision (architecture, schemas, gates, scoring) was designed and implemented from scratch, then iterated against real job postings. Deployed to AWS (S3 + Lambda) to make the pipeline callable outside a local machine.

## What it does

1. Parse a resume (PDF) into structured fields once at startup.
2. Take a job description via clipboard paste (read locally, passed into the pipeline as plain text).
3. Parse the JD into structured requirements, classified into four buckets: **core must-have**, **supporting**, **eligibility constraints**, and **nice-to-have** — instead of one flat skill list.
4. Validate the parsed JD is usable (reject clearly incomplete pastes before wasting further calls).
5. Match the resume against the JD requirement-by-requirement, with the LLM judging evidence strength (`strong` / `partial` / `indirect` / `not_evidenced`) and Python deterministically aggregating those judgments into scores.
6. Gate on the deterministic scores — not on the LLM's own recommendation — before proceeding.
7. Draft a cover letter using only evidence from the parsed resume and JD.
8. Evaluate the letter against a 5-criteria rubric (hook, keyword match, proof-over-pitch, zero resume duplication, CTA), with a deterministic guardrail that caps the hook score if the letter opens with generic boilerplate regardless of what the LLM scores it.
9. Retry with evaluator feedback (max 2 retries) if the letter fails evaluation.
10. Save the accepted letter and the full run state to S3 after every stage transition, for crash recovery and inspection.

## Why it's built this way

The interesting engineering problem here wasn't "call an LLM" — it was **containing LLM non-determinism** so the pipeline behaves consistently on the same input:

- **Extraction vs. inference boundary.** The resume and JD parsers only record what's explicitly stated in the source text. Fields describing something the text doesn't say are left null rather than guessed — enforced by making every schema field's own docstring say so, and catching contradictions between the field type, its default, and its prompt instructions.
- **Deterministic gates around LLM judgment.** The LLM never decides whether the pipeline proceeds. It scores individual pieces of evidence; Python code aggregates those into thresholds and makes the pass/fail call. Early versions let the LLM's own `recommendation` field influence the gate — this caused the same JD to be accepted and rejected across identical re-runs. Removing that dependency, and computing `overall_score` in code from per-requirement evidence rather than asking the LLM for a single number, cut match-score variance roughly in half.
- **Caching the JD parse.** The requirement classification (which bucket a requirement lands in) turned out to be as noisy as the scoring itself — the same JD, parsed twice, produced different requirement splits. Caching the parsed JD (keyed by a hash of the JD text plus a parser version string) makes the requirement set stable across repeated runs on the same posting.
- **Evaluator leniency.** The evaluator initially passed cover letters with textbook-generic openings ("I am writing to express my interest in..."). Tightening the prompt alone wasn't reliable, so a deterministic check now detects known generic openings and hard-caps the hook score, independent of what the LLM scores it.
- **Nice-to-have skills as bonus-only.** Early scoring penalized missing nice-to-have requirements as if they were mandatory, which pushed genuinely strong matches under the acceptance threshold. Nice-to-have evidence now only adds to the score; it never subtracts.
- **Interface-agnostic core.** All pipeline logic lives in one function, `run_pipeline()`, with no dependency on where it's called from. A thin Lambda handler and a thin local invoker both call the same function — the business logic doesn't know or care whether it's running on a laptop or in the cloud.

## Architecture

State-centric, workflow-first pipeline with deterministic gates around LLM judgment calls:

```
parse resume (once, per run, from S3)
        │
        ▼
paste JD locally → invoke pipeline → parse JD → cache → validate ──(fails)──▶ stop, report
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
save letter to S3 + full run state to S3
```

All state (`CoverLetterState`) is a single Pydantic object persisted to S3 after every stage transition, keyed by `run_id` — so a run can be inspected or resumed after a crash.

## Deployment (AWS)

The pipeline runs as an AWS Lambda function; all persistent storage (run state, JD cache, resume, generated letters) lives in a single S3 bucket under separate key prefixes (`states/`, `jd_cache/`, `resume/`, `cover_letters/`).

- **Trigger:** local invocation only, by design. A small script (`invoke_pipeline.py`) reads the job description from the local clipboard — the one piece of this pipeline that can only ever run on a personal machine — and invokes the Lambda function synchronously via `boto3`, waiting for and printing the result. No public endpoint, no API Gateway; this is a personal tool, not a service with other users.
- **Compute:** AWS Lambda, Python 3.10. A full run (parse → match → draft → evaluate, including a retry) takes well under a minute, comfortably inside Lambda's execution limits.
- **Storage:** S3, chosen because the access pattern is simple key → whole-object read/write with no need to query inside the contents — the same shape as the local file-based version it replaced.
- **IAM:** a dedicated execution role for the Lambda function (S3 access + CloudWatch logging), separate from the local-development IAM user used to build and test the S3 migration before Lambda existed.

One real deployment issue worth naming: `pydantic`'s compiled dependency (`pydantic_core`) is platform-specific. Installing dependencies on Windows and deploying to Lambda's Linux runtime produced a working local pipeline and a broken cloud one (`No module named 'pydantic_core._pydantic_core'`) until dependencies were installed explicitly for the target platform (`pip install --platform manylinux2014_x86_64 --only-binary=:all: ...`).

## Project structure

```
pipeline.py                   # run_pipeline(): all business logic, no knowledge of caller (CLI/Lambda/local)
lambda_handler.py              # thin AWS Lambda entry point — extracts event payload, calls run_pipeline()
invoke_pipeline.py               # local-only entry point — reads clipboard, invokes Lambda via boto3, prints result
agents/
  cv_parser.py                # resume PDF (from S3) -> ParsedCV (extraction only)
  jd_parser.py                 # JD text -> ParsedJD (extraction + requirement classification)
  matcher.py                   # ParsedCV + ParsedJD -> MatchAnalysis (evidence judgments only)
  cover_letter_writer.py        # writes/revises the letter from approved evidence
  evaluator.py                  # scores a letter against the 5-criteria rubric
models/
  cv_schema.py, jd_schema.py, match_schema.py, eval_schema.py   # Pydantic schemas
control_plane/
  state.py                      # CoverLetterState + save/load (S3-backed)
  scoring.py                    # deterministic score aggregation from LLM evidence judgments
  match_validation.py            # enforces the matcher evaluated every requirement, unmodified
  quality_gates.py                # JD input-quality gate (fatal vs. warning)
  eval_validation.py               # deterministic guardrail on evaluator leniency
  jd_cache.py                       # content-hashed, versioned JD parse cache (S3-backed)
  cover_letter_storage.py            # saves the accepted letter to S3
```

## Current limitations

- JD input is paste-only (clipboard); URL fetching is deferred to a later phase, since real-world job pages are frequently behind login walls or JS-rendered — pasted text was the more reliable input to build against first.
- Match-score variance from LLM evidence judgments is reduced but not eliminated: identical JD/CV pairs typically land within an ~8-point band on the base score, down from ~33 points before deterministic scoring and requirement caching were introduced.
- This is a personal-scale deployment, not a production one: the IAM policy is broader than least-privilege, infrastructure was configured manually rather than via IaC (Terraform/CDK), and there's no CI/CD or automated test suite. Reasonable trade-offs for a single-user tool; the first things that would change for a multi-user product.

## Stack

Python, OpenAI API (structured outputs via Pydantic schemas), Pydantic v2, AWS (S3, Lambda, IAM), boto3.

## Status

Deployed. Pipeline runs end-to-end on AWS Lambda with S3-backed state, JD cache, and cover-letter storage, triggered by local invocation.
