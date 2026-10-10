import json
import sys
from datetime import date, datetime
from pathlib import Path

from control_plane.application_paths import resolve_application_dir
from control_plane.fact_base_coverage import underdescribed_requirements
from control_plane.jd_cache import parse_jd_cached
from control_plane.reporting import (
    build_cover_letter_run_summary,
    print_fact_base_coverage_report,
    print_final_result,
    print_forced_notice,
    print_jd_cache_status,
    print_match_breakdown,
    print_rejection_report,
    print_retry_notices,
)
from cv.facts import load_facts
from cv.generate import build_cv_run_summary, generate_cv
from cv.selection_rules import top_ranked_project_text
from cv.selector import select_cv_content
from pipeline import run_pipeline


CV_FACTS_PATH = "input/cv_facts.yaml"


def apply(jd_text: str, force: bool = False) -> Path:
    """
    One JD parse (shared with run_pipeline via the same content-addressed
    cache), the existing cover-letter pipeline's match gate, and --
    whenever a cover letter actually got written -- the existing CV
    generator, both writing into one application folder. Reuses
    run_pipeline() and generate_cv() as-is; no gate or generation logic
    is duplicated here.

    The CV selection now runs before run_pipeline (item 6/4): the letter
    needs the CV's top-ranked project and the candidate's real employer
    list before it's written, not after. This costs one selector call on
    every run, including ones the match gate goes on to reject without
    --force -- accepted here since this is a personal, interactively
    triggered tool, not a high-volume service.

    force is passed straight through to run_pipeline(); it never changes
    what gets written, only whether the gate blocks generation.
    """

    facts = load_facts(CV_FACTS_PATH)
    parsed_jd, _jd_cache_hit = parse_jd_cached(jd_text)
    selection = select_cv_content(facts, parsed_jd)

    strongest_evidence = top_ranked_project_text(facts, selection)
    applied_for_role = parsed_jd.job_title or selection.target_title

    state = run_pipeline(
        jd_text=jd_text,
        force=force,
        strongest_evidence=strongest_evidence,
        facts=facts,
        applied_for_role=applied_for_role,
    )

    if state.parsed_jd is not None:
        print_jd_cache_status(state)

    company_name = state.parsed_jd.company_name if state.parsed_jd else None
    job_title = state.parsed_jd.job_title if state.parsed_jd else None
    out_dir = resolve_application_dir(company_name, job_title, date.today())
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "jd.txt").write_text(jd_text, encoding="utf-8")

    summary = {
        "generated_at": datetime.now().isoformat(),
        "company_name": company_name,
        "job_title": job_title,
        "cover_letter": build_cover_letter_run_summary(state),
    }

    if state.match_analysis is not None:
        if state.status == "rejected":
            print_rejection_report(state)
        elif not state.forced:
            # A genuine pass.
            print_match_breakdown(state)
            print_retry_notices(state)
        else:
            # Forced past a would-be rejection: "MATCH PASSED." would be false.
            print_forced_notice(state)
            print_retry_notices(state)

    print_final_result(state)

    summary["run_id"] = state.run_id

    # status == "completed" is the ONLY state in which run_pipeline ever
    # called save_cover_letter -- it's set right before returning, in the
    # same branch that persists cover_letter_key. Every other status
    # (rejected, or failed after exhausting retries) must NOT be treated
    # as a sendable letter, even though state.cover_letter itself may
    # still hold text: the pipeline sets state.cover_letter to each
    # attempt's draft *before* evaluating it, so on the exhausted-retries
    # path it holds the last REJECTED draft, not an accepted one. Gating
    # on state.cover_letter is None (the old check) missed that case --
    # confirmed live: a run whose evaluation loop exhausted retries still
    # wrote cover_letter.txt and generated a CV from stale/rejected
    # content, byte-identical to a prior run. Gate on status instead.
    if state.status != "completed":
        if state.status == "rejected":
            summary["rejection_reason"] = (
                state.error or "match gate rejected: deterministic scores below threshold"
            )
        elif state.status == "failed":
            summary["failure_reason"] = state.error
            summary["last_eval_score"] = state.eval_score

            # Debug-only, never a deliverable -- named so it can't be
            # mistaken for cover_letter.txt if someone skims the folder.
            if state.cover_letter:
                (out_dir / "cover_letter.REJECTED.txt").write_text(
                    state.cover_letter, encoding="utf-8"
                )

        (out_dir / "run.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        print()
        if state.status == "failed":
            print("NO COVER LETTER WRITTEN -- evaluation never passed threshold.")
            print("NO CV GENERATED.")
        print(f"Application folder: {out_dir}")
        print(f"Run ID:             {state.run_id}")
        print(f"Generated at:       {summary['generated_at']}")

        return out_dir

    (out_dir / "cover_letter.txt").write_text(state.cover_letter, encoding="utf-8")

    cv_result = generate_cv(
        facts, state.parsed_jd, out_dir / "cv.docx", forced=state.forced,
        selection=selection, raw_jd_text=jd_text,
    )
    summary["cv"] = build_cv_run_summary(cv_result)

    # Report-only diagnostic (Phase H item 2): surfaces fact-base gaps to
    # the human, never auto-fixes them. See control_plane/fact_base_coverage.py.
    coverage_gaps = underdescribed_requirements(state.parsed_jd, facts, cv_result.content)
    summary["cv"]["underdescribed_requirements"] = coverage_gaps
    print_fact_base_coverage_report(coverage_gaps)

    (out_dir / "run.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print()
    print(f"Application folder: {out_dir}")
    print(f"Run ID:             {state.run_id}")
    print(f"Generated at:       {summary['generated_at']}")
    print(f"CV page count: {cv_result.page_count}")

    return out_dir


def main() -> None:
    args = sys.argv[1:]
    force = "--force" in args
    positional = [a for a in args if a != "--force"]

    if not positional:
        raise SystemExit("Usage: python apply.py <jd_text_file> [--force]")

    jd_text = Path(positional[0]).read_text(encoding="utf-8").strip()

    if not jd_text:
        raise SystemExit(f"JD file is empty: {positional[0]}")

    apply(jd_text, force=force)


if __name__ == "__main__":
    main()
