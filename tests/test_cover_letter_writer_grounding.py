# Phase I item 2: a regression guard that the cover-letter writer stays
# grounded exclusively in the CV fact base (Phase H's root fix -- see
# claude/cover-letter-path-root-cause.md). parsed_cv contamination is
# what caused the original "AI Engineer at Agentic AI" fabrication, and
# Phase I introduces a headline-strip render format that looks exactly
# like what caused it -- this test exists so a future refactor cannot
# quietly reintroduce parsed_cv (or anything derived from it) as a
# writer input.

import inspect

import agents.cover_letter_writer as writer_module
from agents.cover_letter_writer import write_cover_letter


def test_write_cover_letter_signature_has_no_parsed_cv_parameter():
    params = inspect.signature(write_cover_letter).parameters
    assert "parsed_cv" not in params

    for name in params:
        assert "parsed_cv" not in name.lower()


def test_cover_letter_writer_module_does_not_reference_parsed_cv_type():
    assert not hasattr(writer_module, "ParsedCV")
    source = inspect.getsource(writer_module)
    assert "parsed_cv" not in source.lower()
    assert "models.cv_schema" not in source
