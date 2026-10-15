LETTER_LENGTH_RULE = "Keep the letter approximately 250-350 words across all paragraphs combined."

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

# Shared by cv/selector.py's ranking prompt and
# agents/cover_letter_writer.py's system prompt -- both judge/select
# evidence against a JD and need the same guidance against ranking or
# writing purely on literal keyword overlap.
TRADE_OFF_OWNERSHIP_GUIDANCE = (
    "A bullet does not need to share the JD's vocabulary to be strong evidence. "
    "A bullet describing a decision made under ambiguity, a trade-off explicitly "
    "chosen, a simplification made when evidence disagreed, or ownership from "
    "problem to shipped result, is real evidence for requirements about "
    "judgment, ambiguity, or ownership -- even if it was written in engineering "
    "terms. Example: \"Found retrieval grounding did not improve precision and "
    "shipped the simpler configuration supported by the data\" is genuine "
    "evidence of product judgment under ambiguity, not merely an engineering "
    "result. Recognize this kind of connection. Do not invent one that is not "
    "genuinely there -- only select and frame real, existing evidence."
)

# Optional, lower-priority guidance (Phase F item 5): shared by the same
# two callers as TRADE_OFF_OWNERSHIP_GUIDANCE. Redescribing a true fact in
# the JD's own words is not invention -- the underlying fact doesn't
# change, only which words describe it.
JD_VOCABULARY_MIRRORING_GUIDANCE = (
    "When a real, true fact honestly matches a concept the job description "
    "names in its own words (for example the JD's \"context management\" and "
    "a project described as using \"a repository's own history for context, "
    "not just the diff\"), prefer the JD's own term when redescribing that "
    "fact. This does not change what is true, only which words describe it. "
    "Never use the JD's term to redescribe a fact it does not honestly match."
)

# Phase I addendum: used ONLY by cv/selection_rules.py's headline_terms()
# to demote assumed-baseline tooling to the bottom of the CV headline
# strip's ordering -- NOT to exclude it, and NOT anywhere else. Every term
# here still appears normally in the Skills section, entry tools: lines,
# and all requirement-coverage logic (requirement_evidence_fact_ids(),
# the profile's coverage hint, the letter's underrepresented-requirement
# retry) -- none of that reads this list. The headline is one line of
# highest-attention, ATS-relevant real estate; a term nearly every
# applicant for this kind of role also has (Python, SQL, Git...) scores
# maximally on JD prominence but near-zero on differentiation, which is
# what the headline is actually for. Matched case-insensitively, whole
# term.
HEADLINE_TABLE_STAKES_TERMS = (
    "Python",
    "SQL",
    "Git",
    "GitHub",
    "CI/CD",
    "Docker",
    "pytest",
)
