from control_plane.state import CoverLetterState


MIN_JD_TEXT_LENGTH = 200


def validate_jd_input_quality(
    state: CoverLetterState,
) -> bool:
    """
    Check whether the parsed JD is usable for matching.
    """

    if state.parsed_jd is None:
        state.set_error(
            "JD validation failed: parsed_jd is missing."
        )
        return False

    jd = state.parsed_jd

    if not state.raw_jd_text or not state.raw_jd_text.strip():
        state.set_error(
            "JD validation failed: raw job-description text is missing."
        )
        return False

    if len(state.raw_jd_text.strip()) < MIN_JD_TEXT_LENGTH:
        state.set_error(
            "JD validation failed: raw job-description text is too short. "
            "The copied posting may be incomplete."
        )
        return False

    if not jd.core_must_have_skills:
        state.set_error(
            "JD validation failed: no core must-have capabilities were extracted."
        )
        return False

    if not jd.job_title:
        state.add_warning(
            "JD warning: job_title is missing."
        )

    if not jd.company_name:
        state.add_warning(
            "JD warning: company_name is missing."
        )

    if not jd.location:
        state.add_warning(
            "JD warning: location is missing."
        )

    if not jd.employment_type:
        state.add_warning(
            "JD warning: employment_type is missing."
        )

    if not jd.language_skills:
        state.add_warning(
            "JD warning: language_skills is empty."
        )

    if not jd.eligibility_constraints:
        state.add_warning(
            "JD warning: no eligibility constraints were extracted."
        )

    if not jd.supporting_skills:
        state.add_warning(
            "JD warning: no supporting skills were extracted."
        )

    if jd.application_document_requirements:
        state.add_warning(
            "Application documents required: "
            + "; ".join(jd.application_document_requirements)
        )

    return True