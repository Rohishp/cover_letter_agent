---
name: apply
description: Build a tailored cover letter and CV for a pasted job description. Use when the user pastes a JD or runs /apply. Runs apply.py --prepare then --finish and reports the application folder.
disable-model-invocation: true
---

# Apply

Turn a pasted job description into a verified application folder: `cover_letter.txt`, `cv.docx`, `cv.pdf`, `jd.txt`, `run.json`.

## Steps

1. Take the JD from the argument or the user's message. If none was given, ask the user to paste it. Do not invent or shorten it.
2. Write it verbatim to `input/jd_current.txt` (gitignored). Never put a JD anywhere that is tracked.
3. Run `python apply.py --prepare input/jd_current.txt`. Exit 0 prints `Application folder:`; the folder now holds `brief.md` and `state.json`.
4. If it exits 3, the match gate rejected the JD and nothing was saved. The user decides, not the gate:
   - Show the match score and breakdown exactly as Python printed them, plus the threshold it fell short of. Add no scoring of your own.
   - Ask the user (AskUserQuestion) whether to continue anyway or stop.
   - On continue, rerun step 3 with `--force`. On stop, end there. Never choose for them.
5. Run `python apply.py --finish <Application folder>`. It writes the letter with the OpenAI writer, or from a draft when you pass `--draft <file>`, then runs the validators, evaluator, CV and PDF generation and `verify_application`. Exit 0 means verified; 1 means the run failed; 2 means a draft or the folder failed verification (the output lists why).
6. Read the output and report, in a few lines:
   - **Status**: completed, rejected (user stopped) or failed.
   - **Folder**: the `Application folder:` path.
   - **Match score**, **CV page count**, and any fact-base coverage gaps the run printed.
7. If the status is failed, give the reason from the output or `run.json` and stop. Do not edit the letter or work around the evaluation.

## Rules

- Python computes every score and threshold; the user makes the continue-or-stop call. Do not judge the match or the letter yourself.
- `--force` is used only after the user chose to continue.
- `python apply.py input/jd_current.txt [--force]` runs both steps with the OpenAI writer, if you need it in one go.
- Never print or open `.env`, and never paste JD or CV contents into the repo.
- Do not edit generated files. If the user wants changes, change the inputs or the pipeline.
