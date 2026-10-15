# Spec: JD in, verified Application out

Status: draft. Items marked **[assumed]** are my recommended defaults from the grilling round and need the owner's yes/no.

## Goal

Paste a job description into Claude Code. Get one folder, named from the JD, holding a tailored cover letter and CV that a machine has verified. The owner decides on weak matches; Python decides everything pass/fail.

## Terms

- **Fact base**: `input/cv_facts.yaml`, the only approved source of CV evidence.
- **Application**: the folder `output/applications/<YYYY-MM-DD>_<Company>_<Role>[_N]/` for one JD holding `cover_letter.txt`, `cv.docx`, `cv.pdf`, `jd.txt`, `run.json` (plus `brief.md` and `state.json` from `--prepare`, which the verifier ignores). Owner-confirmed.
- **Declined JD**: a folder for a JD the owner chose to stop at the match gate; holds only `jd.txt` and `run.json` (status `declined`), written by `apply.py --decline <jd_file>` when the owner stops. Owner-confirmed.
- **Fit band**: STRONG / BORDERLINE / WEAK from the deterministic score margin. Report-only.
- **Verified**: `verify_application` returns no failures.

## Invariants (carried from CLAUDE.md, not up for change)

1. The LLM never decides pass/fail; Python does.
2. Parsers extract, never infer.
3. The writer uses approved evidence only.
4. State is persisted after every stage transition.
5. A rule that can be checked in Python is checked in Python.

## Phases

### Phase 0: Foundation (carried over, done)
Kept modules and 198 tests pass in this folder. Done when `OPENAI_API_KEY=test pytest --ignore=_legacy` is green.

### Phase 1: `verify_application` (start here)
Interface: `verify_application(folder: Path, facts: CVFacts) -> list[str]` returns human-readable failures, empty means verified. CLI: `python verify_application.py <folder>` prints failures, exit 0 if none, 2 otherwise (so a hook can use it).

Checks, all deterministic, reusing existing check functions where they exist:
1. Folder name matches the pattern; the five files exist; none is empty.
2. `run.json` parses and `status == "completed"` (Application) or the folder is a Declined JD (skip checks 3-6).
3. Letter has no placeholders (`[...]`, `{{`, `TODO`, `<company>`) and passes `check_letter_structure`.
4. Letter passes hedge-disclosure, fabricated-employer and fabricated-role checks against the fact base.
5. `cv.docx` renders to at most 2 pages and has no placeholders.
6. `jd.txt` is non-empty.

Done when:
- A good Application from a real run verifies clean.
- Each check has a test that fails on a deliberately broken folder (one test per check, built in `tmp_path`).
- The CLI exit codes behave as above.
- No check calls an LLM.

### Phase 2: Hooks
- `PreToolUse` on Write, Edit and Bash blocks writes under `output/applications/**` that would break a guarded file. **[assumed]**
  - Guarded files: `cover_letter.txt` (content must pass the cheap letter checks: placeholders, structure, hedge disclosure, fabricated employer, fabricated role; for Edit, the text after the edit is checked) and `run.json` (written only by Python, so any Write/Edit is blocked). Other files in the folder are not checked.
  - Bash is blocked only when the command names `cover_letter.txt` together with a write operator (heuristic; `verify_application` is the backstop).
  - Letters are written whole with Write; an Edit that leaves a partial letter can be blocked until it is complete.
  - Once a call targets a guarded file, a hook error also blocks (fail closed); calls to other files are never blocked.
- `SubagentStop` runs `verify_application` on the folder the sub-agent touched. **[assumed]**
  - The folders come from a `PostToolUse` record per `agent_id` (Write/Edit `file_path`, or any Bash command naming `output/applications/<folder>`), because the sub-agent transcript does not exist yet when SubagentStop fires. The record is deleted when read.
  - Exit 2 with the failures keeps the sub-agent working. A second pass never blocks; a verifier error blocks once; a sub-agent that touched no application folder always passes.
- Hooks only fire on Claude's own tool calls, so they guard sub-agent writes, not files Python writes.

Done when a deliberately bad write is blocked in a real session, and a clean one is not.

### Phase 3: Sub-agents
- Letter sub-agent drafts `draft.txt` from a brief file; Python validators and the evaluator stay the gate; the OpenAI writer stays as fallback until the sub-agent passes several real runs. **[assumed]**
- CV sub-agent writes only the JD-tailored headline and profile; selection and rendering stay deterministic in `cv/`. **[assumed]**
- The owner writes both skills with `/writing-for-agents`. Rule text is imported from `guidelines.py`, never pasted.
- `/apply` drives: `apply --prepare` (parse, match, gate, brief) → sub-agent → `apply --finish` (validators, evaluator, CV, verify). Retries capped at 2, counted by Python in `run.json`. **[assumed]**

Done when `/apply` on three different real JDs produces verified Applications with no manual edits.

### Phase 4: Orchestration rebuild
A small stage list replaces `_legacy/pipeline.py`; slim `state.py`; one shared OpenAI client.

Done when behaviour matches the legacy pipeline on the same inputs, tested without mocks of internals.

## Known risks

- The matcher flips on vague requirements (core score moves up to 13 points); do not rebuild median voting.
- `EVAL_PASS_THRESHOLD` was tuned on the PDF-parsed CV; recalibrate against the fact base before trusting it.
- The new folder has never run against OpenAI.

## Non-goals

Auto-rejecting weak matches; URL fetching of JDs; any cloud storage; changing scoring weights or threshold values without the owner's approval.

## Open questions

1. Confirm the Application / Declined JD definitions.
2. Confirm the sub-agent replaces only the drafting call (Phase 3).
3. Confirm the file-based `--prepare` / `--finish` handoff.
4. CV sub-agent: headline and profile only, or not at all for now?
5. Hooks: cheap checks on write, full verify at stop.
