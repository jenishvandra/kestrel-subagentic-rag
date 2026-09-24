"""
Phase 10: Run the same 16 questions through the single-agent baseline
and write results to a CSV, using the same scoring approach as
eval/run_eval.py so the two sheets are directly comparable.

Resumable, same as eval/run_eval.py: re-running this command skips
questions already recorded in the CSV, so a free-tier rate limit
mid-run doesn't lose earlier progress.

Run: python -m eval.run_baseline_eval
Run a small 6-question representative subset instead of all 16:
python -m eval.run_baseline_eval --quick
"""

import csv
import sys
import time
from pathlib import Path

from eval.baseline_single_agent import build_baseline_collection, get_baseline_agent
from eval.test_questions import TEST_SET, QUICK_SUBSET_IDS
from eval.run_eval import key_point_hits, CITATION_RE
from common.gemini_setup import is_daily_quota_exhausted

QUICK_MODE = "--quick" in sys.argv
ACTIVE_SET = [c for c in TEST_SET if c["id"] in QUICK_SUBSET_IDS] if QUICK_MODE else TEST_SET

OUTPUT_CSV = Path(__file__).resolve().parent / (
    "eval_results_baseline_quick.csv" if QUICK_MODE else "eval_results_baseline.csv"
)
SLEEP_BETWEEN_QUESTIONS_SECONDS = 5

FIELDNAMES = ["id", "question", "key_points_hit", "key_points_total", "citations_found", "time_seconds", "status", "answer"]


def load_existing_rows() -> dict[int, dict]:
    if not OUTPUT_CSV.exists():
        return {}
    rows = {}
    with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows[int(row["id"])] = row
    return rows


def write_rows(rows_by_id: dict[int, dict]) -> None:
    ordered = [rows_by_id[case["id"]] for case in ACTIVE_SET if case["id"] in rows_by_id]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(ordered)


def run_baseline_evaluation():
    if QUICK_MODE:
        print(f"Quick mode: running {len(ACTIVE_SET)} representative questions {QUICK_SUBSET_IDS} instead of all 16.\n")

    build_baseline_collection(reset=False)
    agent = get_baseline_agent()

    rows_by_id = load_existing_rows()
    already_done = {qid for qid, row in rows_by_id.items() if row.get("status") == "ok"}
    if already_done:
        print(f"Resuming: {len(already_done)} question(s) already completed in {OUTPUT_CSV.name}, skipping those.")

    failed_ids = []

    for case in ACTIVE_SET:
        if case["id"] in already_done:
            continue

        print(f"Running Q{case['id']}: {case['question']}")
        start = time.time()
        try:
            answer, elapsed = agent(case["question"])
            hits, n_points = key_point_hits(answer, case["key_points"])
            citations_found = len(CITATION_RE.findall(answer))
            rows_by_id[case["id"]] = {
                "id": case["id"], "question": case["question"],
                "key_points_hit": hits, "key_points_total": n_points,
                "citations_found": citations_found, "time_seconds": round(elapsed, 2),
                "status": "ok", "answer": answer,
            }
            write_rows(rows_by_id)
            print(f"  -> done in {elapsed:.1f}s")
        except Exception as exc:
            elapsed = time.time() - start
            print(f"  -> FAILED after {elapsed:.1f}s: {exc}")
            rows_by_id[case["id"]] = {
                "id": case["id"], "question": case["question"],
                "key_points_hit": "", "key_points_total": "", "citations_found": "",
                "time_seconds": round(elapsed, 2), "status": f"failed: {exc}", "answer": "",
            }
            write_rows(rows_by_id)
            failed_ids.append(case["id"])

            if is_daily_quota_exhausted(exc):
                print(
                    "\n  Daily API quota exhausted — stopping here instead of retrying every "
                    "remaining question. Re-run this same command after your quota resets."
                )
                break

        time.sleep(SLEEP_BETWEEN_QUESTIONS_SECONDS)

    ok_rows = [r for r in rows_by_id.values() if r.get("status") == "ok"]
    n_ok = len(ok_rows)
    n_total = len(ACTIVE_SET)

    print(f"\n=== SUMMARY (single-agent baseline) — {n_ok}/{n_total} questions completed ===")
    if n_ok:
        total_key_hits = sum(int(r["key_points_hit"]) for r in ok_rows)
        total_key_points = sum(int(r["key_points_total"]) for r in ok_rows)
        citation_ok_count = sum(1 for r in ok_rows if int(r["citations_found"]) > 0)
        total_time = sum(float(r["time_seconds"]) for r in ok_rows)

        if total_key_points:
            print(f"Key-point coverage: {total_key_hits}/{total_key_points} = {total_key_hits/total_key_points:.0%}")
        print(f"Citation presence: {citation_ok_count}/{n_ok} = {citation_ok_count/n_ok:.0%}")
        print(f"Avg time/question: {total_time/n_ok:.2f}s")
    print("NOTE: this baseline has no routing, no per-department 'not covered', and no conflict")
    print("detection logic at all — those columns are intentionally absent from this sheet.")

    if failed_ids:
        print(f"\n{len(failed_ids)} question(s) FAILED this run (likely rate-limited): {failed_ids}")
        rerun_cmd = "python -m eval.run_baseline_eval --quick" if QUICK_MODE else "python -m eval.run_baseline_eval"
        print(f"Re-run `{rerun_cmd}` later to fill these in.")
    elif n_ok == n_total:
        print(f"\nAll {n_total} question(s) completed successfully.")

    print(f"\nWrote {OUTPUT_CSV}")


if __name__ == "__main__":
    run_baseline_evaluation()
