from datetime import date

from control_plane.application_paths import application_slug, resolve_application_dir


RUN_DATE = date(2026, 8, 17)


def test_basic_slug_matches_expected_format():
    slug = application_slug("ArtiQuare GmbH", "Working Student AI Engineer", RUN_DATE)

    assert slug == "2026-08-17_ArtiQuare_Working-Student-AI-Engineer"


def test_missing_company_falls_back_to_unknown_company():
    slug = application_slug(None, "AI Engineer", RUN_DATE)

    assert slug == "2026-08-17_unknown-company_AI-Engineer"


def test_missing_role_falls_back_to_unknown_role():
    slug = application_slug("Acme", None, RUN_DATE)

    assert slug == "2026-08-17_Acme_unknown-role"


def test_both_missing_falls_back_to_both_unknowns():
    slug = application_slug(None, None, RUN_DATE)

    assert slug == "2026-08-17_unknown-company_unknown-role"


def test_empty_string_company_also_falls_back():
    # An empty (not None) string is just as unusable as a null.
    slug = application_slug("", "AI Engineer", RUN_DATE)

    assert slug.startswith("2026-08-17_unknown-company_")


def test_non_ascii_company_name_is_transliterated():
    slug = application_slug("Müller & Söhne AG", "Ingenieur", RUN_DATE)

    assert slug == "2026-08-17_Muller-Sohne_Ingenieur"
    assert slug.isascii()


def test_non_ascii_role_name_is_transliterated():
    slug = application_slug("Acme", "Käse-Ingenieur/in", RUN_DATE)

    assert "Kase-Ingenieur-in" in slug
    assert slug.isascii()


def test_legal_suffix_is_stripped_from_company():
    slug = application_slug("Beta Inc", "Engineer", RUN_DATE)

    assert slug == "2026-08-17_Beta_Engineer"


def test_never_raises_on_pathological_input():
    slug = application_slug("!!!___...", "###???...", RUN_DATE)

    # Punctuation-only input strips to nothing -- still falls back cleanly.
    assert slug == "2026-08-17_unknown-company_unknown-role"


def test_resolve_application_dir_no_collision(tmp_path):
    out_dir = resolve_application_dir("Acme", "Engineer", RUN_DATE, root=tmp_path)

    assert out_dir == tmp_path / "2026-08-17_Acme_Engineer"
    assert not out_dir.exists()


def test_resolve_application_dir_appends_suffix_on_collision(tmp_path):
    base = tmp_path / "2026-08-17_Acme_Engineer"
    base.mkdir(parents=True)

    out_dir = resolve_application_dir("Acme", "Engineer", RUN_DATE, root=tmp_path)

    assert out_dir == tmp_path / "2026-08-17_Acme_Engineer_2"


def test_resolve_application_dir_appends_incrementing_suffixes(tmp_path):
    (tmp_path / "2026-08-17_Acme_Engineer").mkdir(parents=True)
    (tmp_path / "2026-08-17_Acme_Engineer_2").mkdir(parents=True)
    (tmp_path / "2026-08-17_Acme_Engineer_3").mkdir(parents=True)

    out_dir = resolve_application_dir("Acme", "Engineer", RUN_DATE, root=tmp_path)

    assert out_dir == tmp_path / "2026-08-17_Acme_Engineer_4"


def test_resolve_application_dir_never_overwrites_existing(tmp_path):
    base = tmp_path / "2026-08-17_Acme_Engineer"
    base.mkdir(parents=True)
    (base / "cv.docx").write_text("existing run", encoding="utf-8")

    out_dir = resolve_application_dir("Acme", "Engineer", RUN_DATE, root=tmp_path)

    assert out_dir != base
    assert (base / "cv.docx").read_text(encoding="utf-8") == "existing run"
