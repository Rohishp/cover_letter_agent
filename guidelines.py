GENERIC_HOOK_EXAMPLES = (
    "I am writing to apply",
    "I am writing to express my interest",
    "I am writing to express my keen interest",
    "I am excited to apply",
    "I wish to apply",
)

GENERIC_HOOK_PREFIXES = tuple(
    example.lower() for example in GENERIC_HOOK_EXAMPLES
)

GENERIC_HOOK_RULE = (
    "A generic opening such as "
    + ", ".join(f"'{example}'" for example in GENERIC_HOOK_EXAMPLES)
    + ", or equivalent wording, must receive a hook score of 5 or lower."
)
