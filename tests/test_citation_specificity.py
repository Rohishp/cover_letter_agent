# Phase K: citing a real fact proves a claim isn't invented; it doesn't
# prove the claim is useful. check_citation_specificity requires at
# least one distinguishing detail (a number, or a named method/
# technology) shared between the claim text and the bullet text of its
# own cited fact(s) -- reused identically for both the cover letter's
# paragraphs and the CV profile.

from cv.containment import check_citation_specificity


def test_generic_praise_with_a_real_citation_fails(facts):
    # Real-world shape: cites a genuine project ID but engages with none
    # of what's actually distinctive about it.
    text = "This exemplifies my ability to design and deploy AI solutions with precision."

    violations = check_citation_specificity(text, facts, ["proj.widget-analyzer"])

    assert violations != []


def test_shared_number_passes(facts):
    text = "I processed 1000 widgets per second in this project."

    assert check_citation_specificity(text, facts, ["proj.widget-analyzer"]) == []


def test_shared_named_technology_passes(facts):
    # "Analyzer" (from the project's own name) is a long, specific word,
    # not a generic connector -- sharing it counts as specific.
    text = "I built the Widget Analyzer end to end."

    assert check_citation_specificity(text, facts, ["proj.widget-analyzer"]) == []


def test_no_citations_fails():
    text = "I built a great tool."

    violations = check_citation_specificity(text, None, [])

    assert violations != []


def test_generic_praise_sharing_nothing_specific_with_experience_fails(facts):
    # "exp.acme.b1" reads "Did thing one with 42 widgets." -- vague
    # first-person praise that shares no number or specific word with
    # it must still fail, the same way the project case above does.
    text = "I brought strong professional skills to this role."

    violations = check_citation_specificity(text, facts, ["exp.acme.b1"])

    assert violations != []
