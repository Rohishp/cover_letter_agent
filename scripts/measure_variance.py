import json
import sys
from datetime import datetime
from pathlib import Path

from pipeline import run_pipeline


CV_PATH = "resume/Rohish_Resume.pdf"

DEFAULT_RUNS = 5


def read_jd_text(jd_file: str) -> str:
    text = Path(jd_file).read_text(encoding="utf-8")

    if not text.strip():
        raise ValueError(f"JD file is empty: {jd_file}")

    return text.strip()


def run_variance_check(jd_file: str, n_runs: int = DEFAULT_RUNS) -> list[dict]:
    jd_text = read_jd_text(jd_file)

    results = []

    for run_number in range(1, n_runs + 1):
        state = run_pipeline(CV_PATH, jd_text)

        match = state.match_analysis

        result = {
            "run_number": run_number,
            "base_score": match.base_score if match else None,
            "core_must_have_score": match.core_must_have_score if match else None,
            "overall_score": match.overall_score if match else None,
            "eval_score": state.eval_score,
            "retry_count": state.retry_count,
            "jd_cache_hit": state.jd_cache_hit,
        }

        results.append(result)

        print(
            f"Run {run_number}: "
            f"base_score={result['base_score']} "
            f"core_must_have_score={result['core_must_have_score']} "
            f"overall_score={result['overall_score']} "
            f"eval_score={result['eval_score']} "
            f"retry_count={result['retry_count']} "
            f"jd_cache_hit={result['jd_cache_hit']}"
        )

    return results


def print_summary(results: list[dict]) -> None:
    base_scores = [
        r["base_score"] for r in results if r["base_score"] is not None
    ]

    if not base_scores:
        print("No base scores recorded.")
        return

    base_min = min(base_scores)
    base_max = max(base_scores)

    print()
    print(f"base_score min: {base_min}")
    print(f"base_score max: {base_max}")
    print(f"base_score range: {base_max - base_min}")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(
            "Usage: python scripts/measure_variance.py <jd_text_file> [n_runs]"
        )

    jd_file = sys.argv[1]
    n_runs = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_RUNS

    results = run_variance_check(jd_file, n_runs)

    print_summary(results)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output_path = Path("output") / f"variance_{timestamp}.json"

    output_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print(f"Raw results written to: {output_path}")


if __name__ == "__main__":
    main()
