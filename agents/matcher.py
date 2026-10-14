import json


from agents.client import client
from agents.fact_render import render_facts
from cv.facts import CVFacts
from models.jd_schema import ParsedJD
from models.match_schema import MatchAnalysis


def build_requirement_payload(parsed_jd: ParsedJD) -> dict:
    """
    Build the exact fixed requirement set the matcher must evaluate.

    Application-document requirements are deliberately excluded.
    """

    return {
        "core_must_have": [
            {
                "requirement_id": f"core_{index}",
                "requirement": requirement,
            }
            for index, requirement in enumerate(
                parsed_jd.core_must_have_skills,
                start=1,
            )
        ],
        "supporting": [
            {
                "requirement_id": f"supporting_{index}",
                "requirement": requirement,
            }
            for index, requirement in enumerate(
                parsed_jd.supporting_skills,
                start=1,
            )
        ],
        "eligibility": [
            {
                "requirement_id": f"eligibility_{index}",
                "requirement": requirement,
            }
            for index, requirement in enumerate(
                parsed_jd.eligibility_constraints,
                start=1,
            )
        ],
        "nice_to_have": [
            {
                "requirement_id": f"nice_{index}",
                "requirement": requirement,
            }
            for index, requirement in enumerate(
                parsed_jd.nice_to_have_skills,
                start=1,
            )
        ],
    }


def compare_cv_to_jd(parsed_jd: ParsedJD, facts: CVFacts) -> MatchAnalysis:
    """
    Evaluate the CV fact base (the same evidence the letter and CV are
    built from) against the exact requirements from ParsedJD.
    """

    requirements = build_requirement_payload(parsed_jd)

    response = client.beta.chat.completions.parse(
        model="gpt-4o",
        temperature=0,
        seed=42,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an evidence matcher.\n\n"

                    "Evaluate the CV against the fixed requirement set supplied "
                    "by deterministic code.\n\n"

                    "Mandatory rules:\n"
                    "- Return exactly one MatchEvidence object for every supplied requirement.\n"
                    "- Preserve every requirement_id exactly.\n"
                    "- Copy each requirement text exactly into jd_requirement.\n"
                    "- Preserve the supplied category and order.\n"
                    "- Do not create, remove, split, merge, rewrite, or reclassify requirements.\n\n"

                    "Strength rules:\n"
                    "- strong: direct and convincing CV evidence.\n"
                    "- partial: meaningful but incomplete evidence.\n"
                    "- indirect: related experience suggests the capability but is not conclusive.\n"
                    "- not_evidenced: no relevant evidence exists in the CV.\n\n"

                    "For behavioral requirements, inspect project ownership, documentation, "
                    "stakeholder work, presentations, leadership, responsibilities, and outcomes "
                    "for indirect evidence.\n\n"

                    "gap_note: when strength is 'indirect' or 'not_evidenced', write one "
                    "concise sentence stating specifically what is missing or insufficient "
                    "relative to that exact requirement. Leave gap_note null when strength "
                    "is 'strong' or 'partial'. gap_note is informational only, exactly like "
                    "the recommendation field -- it must never influence strength, "
                    "explanation, or any score.\n\n"

                    "Do not treat a job title alone as proof of extensive experience. "
                    "Do not calculate numeric scores. Leave all score fields null. "
                    "The recommendation is informational only."
                ),
            },
            {
                "role": "user",
                "content": (
                    "CV fact base:\n"
                    f"{render_facts(facts)}\n\n"
                    "Fixed requirement set:\n"
                    f"{json.dumps(requirements, indent=2, ensure_ascii=False)}"
                ),
            },
        ],
        response_format=MatchAnalysis,
    )

    match = response.choices[0].message.parsed

    if match is None:
        raise ValueError("Matcher returned no structured MatchAnalysis.")

    return match