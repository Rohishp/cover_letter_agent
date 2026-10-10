from cv.containment import check_containment, known_entities_blob
from models.jd_schema import ParsedJD


def _jd(**overrides) -> ParsedJD:
    return ParsedJD(**overrides)


def test_grounded_text_passes(facts):
    jd = _jd(company_name="Acme Corp", technical_skills=["Python"])

    text = (
        "Building reliable systems at Acme Corp draws on my work processing 1000 "
        "widgets per second with Python."
    )

    assert check_containment(text, facts, jd) == []


def test_ungrounded_company_name_is_flagged(facts):
    jd = _jd()

    text = "I previously built scalable systems at Google."

    violations = check_containment(text, facts, jd)

    assert "Google" in violations


def test_ungrounded_tool_name_is_flagged(facts):
    jd = _jd()

    text = "I have deep experience deploying services with Kubernetes."

    violations = check_containment(text, facts, jd)

    assert "Kubernetes" in violations


def test_ungrounded_number_is_flagged(facts):
    jd = _jd()

    text = "I reduced latency by 99% across the platform."

    violations = check_containment(text, facts, jd)

    assert "99%" in violations


def test_number_present_in_fact_base_is_not_flagged(facts):
    jd = _jd()

    # "1000" appears in the fact base: "Processed 1000 widgets per second."
    text = "My work processed 1000 items reliably."

    violations = check_containment(text, facts, jd)

    assert "1000" not in violations


def test_entity_present_only_in_jd_is_not_flagged(facts):
    jd = _jd(company_name="Novel Startup Inc")

    text = "Excited to bring my experience to Novel Startup Inc."

    violations = check_containment(text, facts, jd)

    assert violations == []


def test_sentence_initial_capitalisation_is_not_flagged(facts):
    jd = _jd()

    text = "Building reliable software is my focus. Delivering results matters most."

    violations = check_containment(text, facts, jd)

    assert violations == []


def test_alias_table_resolves_known_abbreviation(facts):
    jd = _jd(technical_skills=["Kubernetes"])

    text = "I have run production workloads on K8s for two years."

    violations = check_containment(text, facts, jd)

    assert "K8s" not in violations


def test_known_entities_blob_includes_fact_base_and_jd_content(facts):
    jd = _jd(company_name="Some Employer", technical_skills=["Rust"])

    blob = known_entities_blob(facts, jd)

    assert "acme" in blob
    assert "widget analyzer" in blob
    assert "some employer" in blob
    assert "rust" in blob
