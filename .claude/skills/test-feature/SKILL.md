---
name: test-feature
description: Write and run pytest tests for one feature from its spec, using test-writer then test-runner. Use when the user runs /test-feature <spec-name>.
disable-model-invocation: true
argument-hint: <spec-name, e.g. T02-verify-letter>
---

# Test feature

The argument is a spec name, e.g. `T02-verify-letter`, resolved to `tasks/<name>.md`.

1. If no argument was given, or `tasks/<name>.md` does not exist, say so, list the files in `tasks/`, and stop.
2. Launch `test-writer` (Agent tool) with the spec path. Wait for it to finish.
3. Check that the test files it reported exist. If none were written, show its open questions and stop; do not launch test-runner.
4. Launch `test-runner` with the test file paths and the spec name. It must only start after step 2 has completed, never in parallel.
5. Report to the user: tests written (with the spec line each covers), run results for the feature and the full suite, and each failure with its classification. Add no findings of your own.
6. Do not fix anything. Ask the user which failures to act on.
