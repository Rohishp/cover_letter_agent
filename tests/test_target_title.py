from cv.selector import CVSelection, ItemRank, title_overlaps_job_title, validate_selection


def _selection(target_title: str) -> CVSelection:
    return CVSelection(
        section_order_reason="test",
        section_order=["skills", "experience", "projects", "education"],
        bullet_ranks=[],
        project_ranks=[],
        skill_group_ranks=[],
        target_title=target_title,
    )


def test_overlapping_title_passes():
    assert title_overlaps_job_title("AI Engineer", "Working Student AI Engineer") is True


def test_identical_title_passes():
    assert title_overlaps_job_title("Backend Engineer", "Backend Engineer") is True


def test_unrelated_title_fails():
    assert title_overlaps_job_title("Backend Developer", "Frontend Designer") is False


def test_gender_marker_noise_is_stripped():
    # "(m/f/x)" tokenizes to meaningless single letters that are all
    # noise-stripped; only "ai" and "associate" (also noise) remain from
    # the JD side, so "ai" alone must still be enough to pass.
    assert title_overlaps_job_title("AI Engineer", "AI Associate (m/f/x)") is True


def test_null_job_title_always_passes():
    assert title_overlaps_job_title("Anything At All", None) is True
    assert title_overlaps_job_title("Anything At All", "") is True


def test_seniority_noise_does_not_block_a_real_match():
    assert title_overlaps_job_title("Backend Engineer", "Senior Backend Engineer") is True


def test_validate_selection_rejects_unrelated_title(facts):
    from models.jd_schema import ParsedJD

    jd = ParsedJD(job_title="Frontend Designer")
    selection = _selection(target_title="Backend Developer")

    errors = validate_selection(selection, facts, jd)

    assert any("target_title" in error for error in errors)


def test_validate_selection_accepts_overlapping_title(facts):
    from models.jd_schema import ParsedJD

    # target_title equal to job_title trivially overlaps and is trivially
    # grounded (job_title itself is part of the containment blob), so this
    # isolates the title-overlap check from containment.
    jd = ParsedJD(job_title="Senior Thing Doer")
    selection = _selection(target_title="Senior Thing Doer")

    errors = validate_selection(selection, facts, jd)

    assert not any("target_title" in error for error in errors)
