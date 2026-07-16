from models.eval_schema import EvalResult


GENERIC_HOOK_PREFIXES = (
    "i am writing to apply",
    "i am writing to express my interest",
    "i am writing to express my keen interest",
    "i am excited to apply",
    "i wish to apply",
)


def calculate_eval_total(
    eval_result: EvalResult,
) -> int:
    return (
        eval_result.hook.score
        + eval_result.keyword_match.score
        + eval_result.proof_over_pitch.score
        + eval_result.zero_resume_duplication.score
        + eval_result.cta.score
    )


def extract_opening_body(cover_letter: str) -> str:
    """
    Remove a possible salutation before checking the opening sentence.
    """

    lines = [
        line.strip()
        for line in cover_letter.strip().splitlines()
        if line.strip()
    ]

    if not lines:
        return ""

    if lines[0].lower().startswith(("dear ", "guten tag", "sehr geehrte")):
        lines = lines[1:]

    return " ".join(lines).lower()


def starts_with_generic_hook(
    cover_letter: str,
) -> bool:
    opening = " ".join(
        extract_opening_body(cover_letter).split()
    )

    return any(
        opening.startswith(prefix)
        for prefix in GENERIC_HOOK_PREFIXES
    )


def validate_eval_result(
    cover_letter: str,
    eval_result: EvalResult,
) -> EvalResult:
    """
    Enforce evaluator invariants deterministically.
    """

    if starts_with_generic_hook(cover_letter):
        if eval_result.hook.score > 5:
            eval_result.hook.score = 5

        eval_result.hook.feedback = (
            "The opening uses generic application boilerplate. "
            "Replace it with a concise, role-specific, evidence-based hook."
        )

    eval_result.overall_score = calculate_eval_total(eval_result)

    return eval_result