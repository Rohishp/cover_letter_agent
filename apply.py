import json
import sys
from datetime import date, datetime
from pathlib import Path

from control_plane import reporting
from control_plane.application_paths import resolve_application_dir
from control_plane.brief import build_brief
from control_plane.fact_base_coverage import underdescribed_requirements
from control_plane.state import CoverLetterState
from cv.facts import load_facts
from cv.generate import build_cv_run_summary, generate_cv
from cv.selection_rules import top_ranked_project_text
from cv.selector import CVSelection, select_cv_content
from pipeline import run_finish, run_prepare
from verify_application import check_letter_text, verify_application

CV_FACTS_PATH = "input/cv_facts.yaml"
EXIT_FAILED, EXIT_UNVERIFIED, EXIT_REJECTED = 1, 2, 3  # rejected: weak match, the owner decides


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _report_match(state: CoverLetterState) -> None:
    if state.status == "rejected":
        reporting.print_rejection_report(state)
    elif state.forced:
        reporting.print_forced_notice(state)
    else:
        reporting.print_match_breakdown(state)


def prepare(jd_text: str, force: bool = False) -> tuple[int, Path | None]:
    """Parse, match, gate. Past the gate: pick CV content, make the Application folder, write the brief."""

    facts = load_facts(CV_FACTS_PATH)
    state = run_prepare(jd_text, facts, force)

    if state.match_analysis is not None:
        _report_match(state)

    if state.status == "rejected":
        return EXIT_REJECTED, None

    if state.status != "match_complete":
        print(f"PREPARE FAILED: {state.error}")
        return EXIT_FAILED, None

    selection = select_cv_content(facts, state.parsed_jd)
    role = state.parsed_jd.job_title or selection.target_title
    strongest = top_ranked_project_text(facts, selection)
    folder = resolve_application_dir(state.parsed_jd.company_name, state.parsed_jd.job_title, date.today())
    folder.mkdir(parents=True)
    (folder / "jd.txt").write_text(jd_text, encoding="utf-8")
    (folder / "brief.md").write_text(build_brief(state, facts, role, strongest), encoding="utf-8")
    _write_json(folder / "state.json", {
        "state": state.model_dump(mode="json"),
        "selection": selection.model_dump(mode="json"),
        "applied_for_role": role,
        "strongest_evidence": strongest,
    })
    _write_json(folder / "run.json", {
        "status": "prepared", "run_id": state.run_id, "generated_at": datetime.now().isoformat(),
        "company_name": state.parsed_jd.company_name, "job_title": state.parsed_jd.job_title,
        "forced": state.forced,
    })
    print(f"\nApplication folder: {folder}\nBrief:              {folder / 'brief.md'}")

    return 0, folder


def finish(folder: Path, draft_file: Path | None = None) -> int:
    """Letter (the draft, else the OpenAI writer), validators, evaluator, CV + PDF, run.json, verify."""

    facts = load_facts(CV_FACTS_PATH)
    saved = json.loads((folder / "state.json").read_text(encoding="utf-8"))
    state = CoverLetterState.model_validate(saved["state"])
    draft = None

    if draft_file is not None:
        draft = draft_file.read_text(encoding="utf-8").strip()
        problems = check_letter_text(draft, facts, state.parsed_jd.company_name)

        if problems:
            print("DRAFT REJECTED (deterministic checks):\n" + "\n".join(f"- {p}" for p in problems))
            return EXIT_UNVERIFIED

    state = run_finish(state, facts, saved["applied_for_role"], saved["strongest_evidence"], draft)
    reporting.print_retry_notices(state)
    reporting.print_final_result(state)
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    run.update(reporting.build_cover_letter_run_summary(state), generated_at=datetime.now().isoformat())

    if state.status != "completed":
        run.update(status="failed", failure_reason=state.error, last_eval_score=state.eval_score)
        _write_json(folder / "run.json", run)
        print("NO COVER LETTER WRITTEN, NO CV GENERATED.")
        return EXIT_FAILED

    (folder / "cover_letter.txt").write_text(state.cover_letter, encoding="utf-8")
    try:  # also writes cv.pdf beside cv.docx; no converter means no PDF, which is a failure, not a skip
        cv_result = generate_cv(
            facts, state.parsed_jd, folder / "cv.docx", forced=state.forced,
            selection=CVSelection.model_validate(saved["selection"]), raw_jd_text=state.raw_jd_text,
        )
    except Exception as error:
        run.update(status="failed", failure_reason=f"CV generation failed: {error}")
        _write_json(folder / "run.json", run)
        print(f"CV GENERATION FAILED: {error}")
        return EXIT_FAILED

    run["cv"] = build_cv_run_summary(cv_result)
    run["cv"]["underdescribed_requirements"] = underdescribed_requirements(state.parsed_jd, facts, cv_result.content)
    reporting.print_fact_base_coverage_report(run["cv"]["underdescribed_requirements"])
    run["status"] = "completed"
    _write_json(folder / "run.json", run)
    failures = verify_application(folder, facts)
    print(f"\nApplication folder: {folder}\nCV page count: {cv_result.page_count}")

    for failure in failures:
        print(f"VERIFY: {failure}")

    return EXIT_UNVERIFIED if failures else 0


def main(argv: list[str]) -> int:
    args, force = [a for a in argv[1:] if a != "--force"], "--force" in argv[1:]
    draft = None

    if "--draft" in args:
        index = args.index("--draft")

        if index + 1 >= len(args):
            return _usage()

        draft, args = Path(args[index + 1]), args[:index] + args[index + 2:]

    if len(args) == 2 and args[0] == "--finish":
        return finish(Path(args[1]), draft)

    if draft is not None:
        return _usage()

    if len(args) == 2 and args[0] == "--prepare":
        return prepare(_read_jd(args[1]), force)[0]

    if len(args) == 1 and not args[0].startswith("--"):  # both steps, OpenAI writer
        code, folder = prepare(_read_jd(args[0]), force)
        return code or finish(folder)

    return _usage()


def _read_jd(path: str) -> str:
    text = Path(path).read_text(encoding="utf-8").strip()

    if not text:
        raise SystemExit(f"JD file is empty: {path}")

    return text


def _usage() -> int:
    print("usage: python apply.py <jd_file> [--force]\n"
          "       python apply.py --prepare <jd_file> [--force]\n"
          "       python apply.py --finish <application_folder> [--draft <letter_file>]", file=sys.stderr)
    return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main(sys.argv))
