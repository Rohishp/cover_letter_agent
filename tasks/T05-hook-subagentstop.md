# T05: SubagentStop hook runs verify

Spec: Phase 2. Depends on: T03, T04.

## Start of session
Read `CLAUDE.md`, `SPEC.md`, `DECISIONS.md`, then this file. Do only this task.

## Scope
SubagentStop hook that runs `verify_application` on the application folder the sub-agent touched and reports failures back.

Behaviour (amended after /test-feature):
- **Finding the folder:** the transcript is not written when SubagentStop fires, so a PostToolUse hook (Write|Edit|Bash, same script) records, per `agent_id`, every `output/applications/<folder>` a call names. A Write/Edit counts by `file_path`; a Bash command counts if it names the path at all (read-only commands included). Calls without an `agent_id` (main session) are not recorded; `.`/`..` names are ignored.
- **Verifying:** SubagentStop runs `verify_application` (page checks on) on each recorded folder that exists, then deletes the record, so a reused agent id starts clean. Exit 2 with the failures on stderr (candidate name redacted) keeps the sub-agent working; exit 0 otherwise. A sub-agent that touched no application folder always passes.
- **No loops:** a second pass (`stop_hook_active`) never blocks. A verifier error (e.g. missing fact base) blocks once with the error type, then passes; an unreadable payload or a record that cannot be written never blocks.
- Known limit: Bash folder names containing spaces are not recorded (real folder names never contain them).

## Done when
- Demonstrated once with a deliberately broken folder and once with a clean one.
- Full test suite green (`OPENAI_API_KEY=test pytest --ignore=_legacy`).
- Committed with a message naming this task.
- A "Result" note appended below (what was built, anything surprising).

## Out of scope
Everything not listed above; protected areas in `CLAUDE.md` (scoring weights, thresholds, `cv/` unless named).

## Result
Built `scripts/hook_verify_subagent.py` with two hook events sharing one script. PostToolUse (Write|Edit|Bash) records, per `agent_id`, each `output/applications/<folder>` a sub-agent's call names (state in the OS temp dir). SubagentStop runs `verify_application` on the recorded folders: exit 2 with the failures keeps the sub-agent working; never blocks on `stop_hook_active` or on a hook error. Both entries are in `.claude/settings.json`. 6 tests in `tests/test_hook_verify_subagent.py`; full suite 374 passed, 1 skipped.

Demonstrated in a real headless session (`claude -p`, foreground sub-agent, `--include-hook-events`): a sub-agent that wrote only `jd.txt` into a folder lacking the other files was blocked from finishing and received the three failures (exit 2, message quoted back verbatim); a sub-agent that touched a valid folder stopped with exit 0 and no message.

Surprising: (1) the sub-agent transcript (`agent_transcript_path`) does not exist yet when SubagentStop fires, so the first design (parse the transcript) found nothing; hence the PostToolUse recording. (2) In the interactive session, background sub-agents return a hand-back report before the block is delivered, so the block was invisible there; the headless foreground run is the evidence. (3) A new hook event in `settings.json` needed a fresh session to load.

### Review follow-up
Applied all nine /code-review-feature findings. Failure text is passed through the PreToolUse hook's `_redact`; `..` names from Bash are ignored; a Bash command naming several folders records all of them; a verifier error (e.g. missing facts file) blocks once so it is seen, then passes on `stop_hook_active`, and only when the sub-agent touched an application folder; the per-agent record is deleted when read, so a reused agent id starts clean; the record lives in the gitignored `output/hook_state/` instead of the shared temp dir; `_target` is reused from `hook_check_letter`. Tests: 15 in `tests/test_hook_verify_subagent.py` (adds `main()`, relative path, two-folder Bash, `..`, record deletion, redaction, error-then-pass). Full suite 383 passed, 1 skipped. The headless `claude -p` broken-folder demo was repeated and still blocks. Folder names with spaces are not handled for Bash paths (the regex stops at whitespace); real folder names are `[A-Za-z0-9-]` only.

### Spec amendment
Resolved the /test-feature open questions by amending Scope above and SPEC.md Phase 2: record-by-`agent_id` mechanism, any Bash command naming the path counts, record deleted on read, page checks on, verifier error blocks once, no-touch passes, exit 2 on stderr. `tests/test_hook_spec_t05.py` written by test-writer from the spec; its one failure was a test bug (it called `decide` once per expected failure, but `decide` consumes the record), fixed by calling it once. Full suite 400 passed, 1 skipped.
