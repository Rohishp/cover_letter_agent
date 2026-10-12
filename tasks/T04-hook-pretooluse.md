# T04: PreToolUse hook on writes

Spec: Phase 2. Depends on: T02.

## Start of session
Read `CLAUDE.md`, `SPEC.md`, `DECISIONS.md`, then this file. Do only this task.

## Scope
Hook script + `.claude/settings.json` entry: on Write/Edit under `output/applications/**`, run the cheap letter checks on the new content; exit 2 with the failures on a bad write. Load the `update-config` skill for settings.

## Done when
- A deliberately bad write is blocked in a real session; a clean write is not. Unit test the script's decision function.
- Full test suite green (`OPENAI_API_KEY=test pytest --ignore=_legacy`).
- Committed with a message naming this task.
- A "Result" note appended below (what was built, anything surprising).

## Out of scope
Everything not listed above; protected areas in `CLAUDE.md` (scoring weights, thresholds, `cv/` unless named).

## Result
Built `scripts/hook_check_letter.py` (pure `decide(payload, facts)` plus a thin stdin/exit-code `main`) and a project `.claude/settings.json` PreToolUse entry on `Write|Edit`. It only acts on `output/applications/**/cover_letter.txt`; for Edit it checks the text after applying the edit, and leaves unknowable cases (old_string missing) to the tool. To share the checks, I split `check_letter_text(letter, facts, company)` out of `verify_application._check_letter`; company comes from the folder's `run.json` if present.

Verified in a real session: a letter with `TODO [insert company]` was blocked (exit 2, failures shown); a valid letter in the same folder was written. 11 unit tests in `tests/test_hook_check_letter.py`; full suite 308 passed, 1 skipped.

Surprising: the settings file was picked up mid-session without a restart. A fresh letter must also pass the structure checks (greeting, closing line, exact name), so a draft written in pieces via Edit may be blocked until complete. Hook runs `python` from PATH (Python 3.10 here).

### Review follow-up
Applied the /code-review-feature findings: absolute hook command via `$CLAUDE_PROJECT_DIR` with `shell: bash`; fail closed once a call targets a guarded file (facts missing, import error, hook bug), never block unguarded calls; case/trailing-dot/`::$DATA` letter-name variants; relative `file_path` resolved against payload `cwd`; Write/Edit of `run.json` blocked; symlinked `run.json` ignored for `company_name`; Bash commands that name the letter file together with a write operator (redirect, `sed -i`, `Set-Content`, ...) are blocked (heuristic only, so a Bash command that merely mentions both can be a false positive); candidate name redacted from hook output; CRLF-aware Edit simulation; block message names the tool; `check_letter_text` moved above its caller. Tests: 31 in `tests/test_hook_check_letter.py`, full suite 328 passed, 1 skipped.
