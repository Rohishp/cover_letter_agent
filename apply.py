import json
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

from pydantic import ValidationError

from control_plane import reporting
from control_plane.application_paths import APPLICATIONS_ROOT, resolve_application_dir
from control_plane.brief import build_brief
from control_plane.cover_letter_containment import check_ungrounded_figures
from control_plane.fact_base_coverage import underdescribed_requirements
from control_plane.state import CoverLetterState
from cv.facts import load_facts
from cv.generate import build_cv_run_summary, generate_cv
from cv.selection_rules import top_ranked_project_text
from cv.selector import CVSelection, select_cv_content
from pipeline import redact, run_finish, run_prepare, should_generate_cover_letter
from verify_application import check_letter_text, verify_application

CV_FACTS_PATH = "input/cv_facts.yaml"
EXIT_FAILED, EXIT_UNVERIFIED, EXIT_REJECTED = 1, 2, 3  # rejected: weak match, the owner decides
FINISHABLE = ("prepared", "failed")  # a failed run may be finished again; a completed one never


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

    try:
        selection = select_cv_content(facts, state.parsed_jd)
    except Exception as error:
        print(f"PREPARE FAILED: CV selection failed: {redact(str(error))}")
        return EXIT_FAILED, None

    role = state.parsed_jd.job_title or selection.target_title
    strongest = top_ranked_project_text(facts, selection)
    folder = resolve_application_dir(state.parsed_jd.company_name, state.parsed_jd.job_title, date.today())

    try:
        folder.mkdir(parents=True)
    except OSError as error:
        print(f"PREPARE FAILED: cannot create {folder}: {error}")
        return EXIT_FAILED, None

    try:
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
    except OSError as error:
        shutil.rmtree(folder, ignore_errors=True)  # no half-made Application
        print(f"PREPARE FAILED: cannot write {folder}: {error}")
        return EXIT_FAILED, None

    print(f"\nApplication folder: {folder}\nBrief:              {folder / 'brief.md'}")

    return 0, folder


def _load_prepared(folder: Path) -> tuple[dict, CoverLetterState]:
    """state.json of a folder --prepare made. state.json is a file on disk, so Python re-checks the gate."""

    if APPLICATIONS_ROOT.resolve() not in folder.resolve().parents:
        raise ValueError(f"{folder} is not under {APPLICATIONS_ROOT}")

    try:
        run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
        saved = json.loads((folder / "state.json").read_text(encoding="utf-8"))
        state = CoverLetterState.model_validate(saved["state"])
        CVSelection.model_validate(saved["selection"])
        if not {"applied_for_role", "strongest_evidence"} <= saved.keys():
            raise KeyError("saved run is incomplete")
    except (OSError, ValueError, KeyError, TypeError, ValidationError):
        raise ValueError(f"{folder} is not a prepared Application (run.json or state.json missing or invalid)")

    if run.get("status") not in FINISHABLE:
        raise ValueError(f"run.json status is {run.get('status')!r}; --finish needs 'prepared' (or a failed run)")

    if state.status != "match_complete" or state.parsed_jd is None or state.match_analysis is None:
        raise ValueError(f"state.json is at status {state.status!r}, expected 'match_complete'")

    forced_past_gate = state.forced and state.match_gate_result == "would_have_rejected"

    if not should_generate_cover_letter(state.match_analysis) and not forced_past_gate:
        raise ValueError("state.json does not pass the match gate and was not forced")

    return saved, state


def _draft_problems(draft: str, facts, state: CoverLetterState) -> list[str]:
    """Deterministic checks a plain-text draft gets in place of the writer's own validation."""

    source = facts.model_dump_json() + "\n" + (state.raw_jd_text or "")

    return [
        *check_letter_text(draft, facts, state.parsed_jd.company_name),
        *(f"cover_letter.txt: {p}" for p in check_ungrounded_figures(draft, source)),
    ]


def finish(folder: Path, draft_file: Path | None = None) -> int:
    """Letter (the draft, else the OpenAI writer), validators, evaluator, CV + PDF, run.json, verify."""

    facts = load_facts(CV_FACTS_PATH)

    try:
        saved, state = _load_prepared(folder)
    except ValueError as error:
        print(f"FINISH REFUSED: {error}")
        return EXIT_FAILED

    draft = None

    if draft_file is not None:
        try:
            draft = draft_file.read_text(encoding="utf-8").strip()
        except OSError as error:
            print(f"FINISH REFUSED: cannot read draft: {error}")
            return EXIT_FAILED

        problems = _draft_problems(draft, facts, state)

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
        reason = redact(f"CV generation failed: {error}")
        run.update(status="failed", failure_reason=reason)
        _write_json(folder / "run.json", run)
        print(reason)
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
        return _usage() if force else finish(Path(args[1]), draft)

    if draft is not None:
        return _usage()

    if len(args) == 2 and args[0] == "--prepare":
        return prepare(_read_jd(args[1]), force)[0]

    if len(args) == 1 and not args[0].startswith("--"):  # both steps, OpenAI writer
        code, folder = prepare(_read_jd(args[0]), force)
        return code or finish(folder)

    return _usage()


def _read_jd(path: str) -> str:
    try:
        text = Path(path).read_text(encoding="utf-8").strip()
    except OSError as error:
        raise SystemExit(f"cannot read JD file: {error}")

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
