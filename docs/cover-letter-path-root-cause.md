# Cover-letter path: root-cause diagnosis (Aug 2026)

## The symptom

The cover-letter writer repeatedly produced sentences like:

> "My role as an AI Engineer involved designing and deploying agentic AI systems using Python,
> OpenAI Agents SDK, and RAG architectures."

No such role, employer, or engagement ever existed. This is a fabrication, not a paraphrase --
CLAUDE.md invariant 3 ("the writer uses approved evidence only") was being violated.

## Root cause 1: the real resume's own headline

`resume/Rohish_Resume.pdf` renders its own headline, directly under the candidate's name, as:

    AI Engineer - Agentic AI | Python - OpenAI Agents SDK - LangGraph - RAG - Docker - AWS

This is a *title-plus-skills strip*, not a job title. But it sits exactly where a job title goes
on the page, and `agents/cv_parser.py`'s extraction pass -- reading the PDF the same way it reads
any other resume -- pulled it in as `parsed_cv`'s title-like field. From there, `parsed_cv` (full,
unstructured prose) was passed straight into `agents/cover_letter_writer.py`'s prompt as grounding
context. The writer, seeing "AI Engineer - Agentic AI" positioned like a held role, pattern-matched
it into "my role as an AI Engineer... agentic AI systems" -- inventing an employment claim out of
a formatting artifact.

## Root cause 2: architectural asymmetry with the CV path

The CV generation path (`cv/`) was already structured correctly: structured facts
(`cv_facts.yaml` via `CVFacts`) -> LLM ranks/selects only -> Python assembles/validates -> renderer
emits. Nothing in that path lets the LLM free-write from raw prose.

The cover-letter path did not mirror this. `write_cover_letter()` received `parsed_cv` -- an
LLM-parsed, free-form document -- and returned a single free-text string with no structural
citation requirement. There was no mechanism forcing every claim back to a real fact-base ID, so a
plausible-sounding but fabricated sentence had nothing to catch it before it reached a human.

## The fix (Phase H)

1. **Remove `parsed_cv` from the writer's inputs entirely.** `write_cover_letter()` now takes
   `facts: CVFacts` (the same closed fact base the CV path uses) and `applied_for_role`, never the
   candidate's own resume text. `known_organisations` and `real_held_titles` are computed from
   `facts` inside the writer, not passed in by the caller.
2. **Structured, cited output.** The writer returns a `CoverLetterDraft`: an ordered list of
   paragraphs, each tagged `kind: factual | connective` and `fact_ids: list[str]`. Every factual
   paragraph must cite >=1 real ID from `facts.by_id()`; Python validates this before accepting a
   draft, the same "ground first, write second" discipline the CV path already had.
2. **Structural backstops, not just prompt instructions.** `check_fabricated_employer` and
   `check_fabricated_role_claim` scan every paragraph -- regardless of kind or citation -- for a
   held-role or held-employer claim naming anything outside the closed, fact-base-derived lists.
   Deterministic checks beat prompt instructions (CLAUDE.md invariant 5): the prompt alone was not
   enough, in practice, to stop this pattern reliably.

## Why this file exists

Phase I reintroduces a headline-strip format on the *rendered CV* -- deliberately, this time, as a
readable "claim plus evidence" line under the candidate's name (see `cv/selection_rules.py`'s
`build_headline_strip()`). This is the exact shape that caused root cause 1 above.

The strip is safe **only** because it is render-only: built by deterministic Python from
`cv_facts.yaml`, consumed exclusively by `cv/render.py`, and never passed to `write_cover_letter()`,
`write_profile()`, or any parser whose output reaches either. If a future change threads
`content.headline_strip` (or anything derived from it) into an LLM prompt used for cover-letter or
profile generation, it reopens exactly the contamination path this document describes. Don't.
