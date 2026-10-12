# T11: check_fabricated_employer misses lowercase role phrases

Spec: Phase 1, check 4 (hardening). Depends on: T02. Independent of T03 onward; can run at any point.

## Start of session
Read `CLAUDE.md`, `SPEC.md`, `DECISIONS.md`, then this file. Do only this task.

## Problem
Found by the T02 test run (`tests/test_verify_letter_spec.py`). `check_fabricated_employer` in `control_plane/cover_letter_containment.py` only matches two shapes: a capitalised role word before at/with/for (`Lead Engineer at X`), or a clause opening `At/With/For X, I`. These slip through with no failure:
- `As an engineer at Fakecorp, I did it.` (lowercase role word)
- `I worked as a developer for Initech.` (lowercase role word, other prepositions)

A fabricated employer behind a lowercase role is the same failure as the "Agentic AI" incident, so invariant 3 (approved evidence only) is not enforced for it.

## Scope
Extend the role-at-organisation detection to lowercase role words (the existing `_ROLE_WORD_PATTERN` list), in `control_plane/cover_letter_containment.py`. It is shared with the writer (`agents/cover_letter_writer.py`), so the writer gets stricter too.

## Done when
- Tests fail before and pass after for the two shapes above, written first.
- No new false positives: real employers and institutions, and the target company, are still allowed in those shapes; existing tests in `tests/test_fabricated_employer.py` stay green and gain a case for "an engineer at <real employer>".
- Decide and record how to avoid matching ordinary prose ("a team at the front", "engineer at heart"); capitalised-organisation matching must still be required.
- Full test suite green (`OPENAI_API_KEY=test pytest --ignore=_legacy`).
- Committed with a message naming this task.
- A "Result" note appended below.

## Out of scope
Extending the role-word list, other check functions, scoring weights, thresholds, `cv/`.

## Result
(not started)
