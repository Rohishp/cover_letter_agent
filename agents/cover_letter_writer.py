from dotenv import load_dotenv
from openai import OpenAI

from control_plane.cover_letter_containment import (
    CLOSING_LINE,
    check_fabricated_employer,
    check_fabricated_role_claim,
    check_hedge_disclosure,
    check_letter_structure,
    known_organisations as get_known_organisations,
    real_held_titles as get_real_held_titles,
)
from cv.containment import check_citation_specificity
from cv.facts import CVFacts
from cv.selector import _render_facts_with_ids
from guidelines import (
    GENERIC_HOOK_EXAMPLES,
    JD_VOCABULARY_MIRRORING_GUIDANCE,
    TRADE_OFF_OWNERSHIP_GUIDANCE,
)
from models.cover_letter_schema import CoverLetterDraft
from models.jd_schema import ParsedJD
from models.match_schema import MatchAnalysis


load_dotenv()
client = OpenAI()

MAX_ATTEMPTS = 3


def validate_cover_letter_draft(
    draft: CoverLetterDraft,
    facts: CVFacts,
    known_organisations: list[str],
    real_held_titles: list[str] | None = None,
) -> list[str]:
    """
    Structural validation, the same pattern cv/selector.py's
    evidences_requirement validator uses: every factual claim must trace
    to a real, citable fact. The fabricated-employer and fabricated-role
    regex checks stay wired in too, applied to every paragraph regardless
    of kind -- a backstop in case a role-at-organisation (or bare
    held-role) claim ends up in text marked "connective" (which should
    never make a factual claim at all) or cites a technically-valid but
    unrelated fact_id.
    """

    errors: list[str] = []

    for index, paragraph in enumerate(draft.paragraphs):
        if paragraph.kind == "factual":
            if not paragraph.fact_ids:
                errors.append(
                    f"paragraph {index} is factual but cites no fact_ids -- every "
                    "factual claim must trace to at least one real fact-base ID"
                )

            for fact_id in paragraph.fact_ids:
                if facts.by_id(fact_id) is None:
                    errors.append(f"paragraph {index} cites an unknown fact_id: {fact_id!r}")

            # Phase K: citation proves the claim isn't invented; this
            # proves it isn't generic. A paragraph that cites a real
            # fact but shares no distinguishing detail with it ("the PR
            # Review Agent" with no mention of the four-arm experiment,
            # the judge failure and fix, or the variance reduction) could
            # describe any candidate with a similar-sounding project.
            if paragraph.fact_ids:
                for violation in check_citation_specificity(
                    paragraph.text, facts, paragraph.fact_ids
                ):
                    errors.append(f"paragraph {index} lacks specificity: {violation}")

        for org in check_fabricated_employer(paragraph.text, known_organisations):
            errors.append(
                f"paragraph {index} claims a position at an organisation not in the "
                f"candidate's real history: {org!r}"
            )

        if real_held_titles is not None:
            for role in check_fabricated_role_claim(paragraph.text, real_held_titles):
                errors.append(
                    f"paragraph {index} claims a held role the candidate never had: "
                    f"{role!r} -- the candidate's real held titles are {real_held_titles}"
                )

    return errors


def assemble_cover_letter(draft: CoverLetterDraft, facts: CVFacts) -> str:
    """
    Python owns assembly, including the sign-off (Phase J item 1): the
    LLM owns wording only (invariant 1's "Python aggregates, the LLM
    judges pieces", applied to the letter the same way it already
    applies to scoring). The closing line and the candidate's exact name
    are appended unconditionally -- assembly can never produce an
    unsigned letter, regardless of what the draft's paragraphs contain.
    """

    body = "\n\n".join(paragraph.text.strip() for paragraph in draft.paragraphs)
    return f"{body}\n\n{CLOSING_LINE}\n{facts.personal.full_name}"


def _system_prompt(
    facts_block: str, known_organisations: list[str], real_held_titles: list[str], valid_ids: list[str]
) -> str:
    generic_hook_bullets = "\n".join(f"- {example}" for example in GENERIC_HOOK_EXAMPLES)
    organisations_list = ", ".join(known_organisations) if known_organisations else "(none)"
    titles_list = ", ".join(real_held_titles) if real_held_titles else "(none)"
    valid_ids_list = ", ".join(valid_ids)

    return (
        "Write a concise, specific, professional cover letter as a structured list of "
        "paragraphs, in order.\n\n"

        "Every paragraph has kind, then fact_ids, then text, in that order -- decide what "
        "you are grounding a paragraph in BEFORE writing its prose, not after.\n\n"

        "kind=\"factual\": the paragraph makes any claim about the candidate -- a role "
        "held, an employer, a project, a skill, an outcome, a tool used. fact_ids must "
        "name at least one real ID from the fact base below that the claim traces to. "
        "Citing an ID not shown to you, or leaving fact_ids empty on a factual paragraph, "
        "is invalid and will be rejected. Citing a real ID is not enough on its own: the "
        "paragraph's text must also carry at least one distinguishing detail from that "
        "fact's own bullet text -- a number, or a named method or technology, not just "
        "the fact's existence. \"exemplifies my ability to design and deploy AI solutions "
        "with precision\" cites a real project while saying nothing that project's own "
        "bullets don't already make specific -- which experiment, which number, which "
        "tool. A paragraph with no such shared detail is rejected the same way an "
        "uncited claim is.\n\n"

        "kind=\"connective\": purely rhetorical text with NO claim about the candidate -- "
        "the greeting, a sentence like \"I look forward to discussing this further.\" "
        "fact_ids stays empty. A connective paragraph must never state or imply a role, "
        "employer, project, or skill -- if it does, it should have been factual and cited "
        "instead. Do not write a sign-off/closing line or the candidate's name in any "
        "paragraph -- the system appends that automatically after your last paragraph. "
        "End your final paragraph with the call-to-action content only.\n\n"

        "The candidate's real, closed fact base, with stable IDs in brackets. This is the "
        "ONLY source of factual claims about the candidate -- nothing outside it may be "
        "cited or implied:\n"
        f"{facts_block}\n\n"

        f"The ONLY valid fact_ids are exactly these {len(valid_ids)} IDs: {valid_ids_list}. "
        "Every one of them is shown bracketed next to the fact it identifies above -- if an "
        "ID is not shown in brackets above, it does not exist. There is no section-level ID "
        "such as \"languages\", \"experience\", \"skills\", \"education\", or "
        "\"certifications\" -- a section groups several real facts, each with its own ID; "
        "the section name itself is never a citable ID. To cite a candidate's language or "
        "certification, use its own bracketed ID from the LANGUAGES/CERTIFICATIONS lists "
        "above, never the section heading.\n\n"

        f"The candidate's ONLY real employers/institutions are: {organisations_list}. "
        f"The candidate's ONLY real HELD job titles are: {titles_list}. Never state or "
        "imply any other employer, institution, or held title -- including inventing one "
        "by combining a skill/technology label (like \"Agentic AI\", \"Generative AI\", "
        "\"RAG\") with a role word to make it read like a job. A skill or technology label "
        "is never an employer, no matter how much it reads like a plausible company "
        "name.\n\n"

        "The role the candidate is APPLYING FOR (not a role they have held, past or "
        "present) is given separately as applied_for_role in the user message. Never "
        "describe applied_for_role as something the candidate already does or has done, "
        "and never combine it with any organisation to imply a position held -- frame it "
        "only as the role this letter is applying for. This includes constructions "
        "without a named organisation at all -- \"my role as [applied_for_role]\" or "
        "\"working as [applied_for_role]\" is exactly as fabricated as naming an "
        "employer, because it still claims the candidate held that role.\n\n"

        "Do not begin with generic wording such as:\n"
        f"{generic_hook_bullets}\n\n"

        "Begin with a role-specific, evidence-based connection between the candidate and "
        "the role's mission.\n\n"

        "Never disclose a skill/tool gap, bluntly (\"I don't have X\") or softened as "
        "forward-looking enthusiasm about a specific skill/tool (\"eager to expand my "
        "expertise in X\"). Only write forward-looking enthusiasm that does not name a "
        "specific missing skill.\n\n"

        f"{TRADE_OFF_OWNERSHIP_GUIDANCE}\n\n"

        f"{JD_VOCABULARY_MIRRORING_GUIDANCE}"
    )


def _user_content(
    parsed_jd: ParsedJD,
    match_analysis: MatchAnalysis,
    applied_for_role: str,
    eval_feedback: str | None,
    strongest_evidence: str | None,
    underrepresented_hint: list[dict] | None,
    grounding_feedback: str | None,
) -> str:
    feedback_block = ""

    if eval_feedback:
        feedback_block += (
            "\nEvaluator feedback from the previous attempt:\n"
            f"{eval_feedback}\n"
            "Revise the new letter to fix these issues.\n"
        )

    if grounding_feedback:
        feedback_block += f"\n{grounding_feedback}\n"

    strongest_evidence_block = ""

    if strongest_evidence:
        strongest_evidence_block = (
            "\nThe CV generated for this application leads with this as its single "
            "strongest, most JD-relevant evidence:\n"
            f"{strongest_evidence}\n"
            "Engage with it directly in a factual paragraph -- you don't need to quote it "
            "verbatim, and may draw on other real evidence too, but do not omit the "
            "candidate's strongest point.\n"
        )

    underrepresented_block = ""

    if underrepresented_hint:
        lines = [
            f"- {item['jd_requirement']} -- cite {', '.join(item['fact_ids'])} to cover this"
            for item in underrepresented_hint
        ]
        underrepresented_block = (
            "\nThe previous letter left real, matcher-confirmed evidence unused. Add (or "
            "revise) a factual paragraph citing the specific fact_ids below for each -- "
            "never reference these requirements without citing this evidence:\n"
            + "\n".join(lines)
            + "\n"
        )

    return (
        f"applied_for_role (the role being applied for -- NOT a role the candidate has "
        f"held): {applied_for_role!r}\n\n"
        "Parsed Job Description:\n"
        f"{parsed_jd.model_dump_json(indent=2)}\n\n"
        "Match Analysis:\n"
        f"{match_analysis.model_dump_json(indent=2)}\n"
        f"{feedback_block}"
        f"{strongest_evidence_block}"
        f"{underrepresented_block}\n"
        "Requirements:\n"
        "- Use a strong role-specific hook.\n"
        "- Naturally reflect important JD concepts.\n"
        "- Use concrete proof instead of unsupported claims.\n"
        "- Do not copy resume bullets verbatim -- interpret the evidence.\n"
        "- End with a concise professional CTA.\n"
        "- If the company name is missing, use 'Dear Hiring Team,' as a connective "
        "paragraph.\n"
        "- Keep the letter approximately 250-350 words across all paragraphs combined."
    )


def _call_writer(
    facts_block: str,
    known_organisations: list[str],
    real_held_titles: list[str],
    valid_ids: list[str],
    parsed_jd: ParsedJD,
    match_analysis: MatchAnalysis,
    applied_for_role: str,
    eval_feedback: str | None,
    strongest_evidence: str | None,
    underrepresented_hint: list[dict] | None,
    grounding_feedback: str | None,
) -> CoverLetterDraft:
    response = client.beta.chat.completions.parse(
        model="gpt-4o",
        temperature=0,
        seed=42,
        messages=[
            {
                "role": "system",
                "content": _system_prompt(facts_block, known_organisations, real_held_titles, valid_ids),
            },
            {
                "role": "user",
                "content": _user_content(
                    parsed_jd, match_analysis, applied_for_role, eval_feedback,
                    strongest_evidence, underrepresented_hint, grounding_feedback,
                ),
            },
        ],
        response_format=CoverLetterDraft,
    )

    draft = response.choices[0].message.parsed

    if draft is None or not draft.paragraphs:
        raise ValueError("Cover-letter writer returned no structured draft.")

    return draft


def write_cover_letter(
    facts: CVFacts,
    parsed_jd: ParsedJD,
    match_analysis: MatchAnalysis,
    applied_for_role: str,
    eval_feedback: str | None = None,
    strongest_evidence: str | None = None,
    underrepresented_requirements_hint: list[dict] | None = None,
) -> str:
    """
    Generate or revise a cover letter grounded in the fact base, not free
    prose (Phase H). The writer receives cv_facts.yaml via CVFacts (the
    same source the CV path uses), never the candidate's raw parsed
    resume text -- that was the actual source of the recurring "AI
    Engineer at Agentic AI" fabrication: the real resume's own headline
    literally reads "AI Engineer - Agentic AI", sitting in title
    position, right under the candidate's name.

    Every factual claim must cite a real fact_id (facts.by_id()); an
    invalid or missing citation is a hard fail -> retry, mirroring
    cv/selector.py's evidences_requirement pattern for the CV path.

    applied_for_role is passed under its own explicit label; the system
    prompt states plainly it is a role being applied for, not held.

    underrepresented_requirements_hint (Phase H item 3, replacing Phase G
    item 2's broken version): a list of {"jd_requirement": str,
    "fact_ids": list[str]} -- never a bare term. A coverage nudge naming
    a keyword with no grounded evidence to point to is what caused the
    writer to invent a job role in the first place.
    """

    facts_block = _render_facts_with_ids(facts)
    known_organisations = get_known_organisations(facts, parsed_jd.company_name)
    real_held_titles = get_real_held_titles(facts)
    valid_ids = facts.all_ids()

    grounding_feedback = None
    last_errors: list[str] = []

    for _attempt in range(1, MAX_ATTEMPTS + 1):
        draft = _call_writer(
            facts_block=facts_block,
            known_organisations=known_organisations,
            real_held_titles=real_held_titles,
            valid_ids=valid_ids,
            parsed_jd=parsed_jd,
            match_analysis=match_analysis,
            applied_for_role=applied_for_role,
            eval_feedback=eval_feedback,
            strongest_evidence=strongest_evidence,
            underrepresented_hint=underrepresented_requirements_hint,
            grounding_feedback=grounding_feedback,
        )

        content = assemble_cover_letter(draft, facts)

        errors = validate_cover_letter_draft(draft, facts, known_organisations, real_held_titles)
        errors += [
            f"volunteers a skill/tool gap the candidate doesn't need to disclose: {phrase!r}"
            for phrase in check_hedge_disclosure(content)
        ]
        errors += [
            f"structural requirement violated: {violation}"
            for violation in check_letter_structure(content, draft, facts)
        ]

        if not errors:
            return content

        last_errors = errors
        grounding_feedback = (
            "The previous letter was invalid for these reasons:\n"
            + "\n".join(f"- {error}" for error in errors)
            + "\nRewrite the letter, fixing these specific problems. Every factual claim "
            "must cite a real fact_id from the fact base shown to you, and carry a "
            "distinguishing detail (a number, named method, or technology) from that "
            "fact's own text. Never disclose a skill/tool gap, blunt or softened as "
            "forward-looking enthusiasm."
        )

        if any("unknown fact_id" in error for error in errors):
            grounding_feedback += (
                "\nAt least one paragraph cited a fact_id that does not exist -- see the "
                "specific invalid ID(s) named above. The complete list of valid IDs is: "
                + ", ".join(valid_ids)
                + ". There is no section-level ID (no \"languages\", \"experience\", "
                "\"skills\", etc.) -- only the exact per-entry IDs in this list."
            )

    raise ValueError(
        "Cover letter failed validation after "
        f"{MAX_ATTEMPTS} attempts: " + "; ".join(last_errors)
    )
