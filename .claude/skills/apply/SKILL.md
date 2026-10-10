---
name: apply
description: Build a tailored cover letter and CV for a pasted job description. Use when the user pastes a JD or runs /apply. Runs apply.py and reports the application folder.
disable-model-invocation: true
---

# Apply

Turn a pasted job description into `cover_letter.txt` and `cv.docx` in one application folder.

## Steps

1. Take the JD from the argument or the user's message. If none was given, ask the user to paste it. Do not invent or shorten it.
2. Write it verbatim to `input/jd_current.txt` (gitignored). Never put a JD anywhere that is tracked.
3. Run `python apply.py input/jd_current.txt`.
4. If the match gate rejects the JD, the user decides, not the gate:
   - Show the match score and breakdown exactly as Python printed them, plus the threshold it fell short of. Add no scoring of your own.
   - Ask the user (AskUserQuestion) whether to continue anyway or stop.
   - On continue, rerun `python apply.py input/jd_current.txt --force`. On stop, end there. Never choose for them.
5. Read the final output and report, in a few lines:
   - **Status**: completed, rejected (user stopped) or failed (evaluation never passed).
   - **Folder**: the `Application folder:` path, `output/applications/<date>_<Company>_<Role>/`.
   - **Match score**, **CV page count**, and any fact-base coverage gaps the run printed.
6. If the status is failed, give the reason from the output or `run.json` and stop. Do not edit the letter or work around the evaluation.

## Rules

- Python computes every score and threshold; the user makes the continue-or-stop call. Do not judge the match or the letter yourself.
- `--force` is used only after the user chose to continue.
- Never print or open `.env`, and never paste JD or CV contents into the repo.
- Do not edit generated files. If the user wants changes, change the inputs or the pipeline.
