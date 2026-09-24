"""
Phase 9: Run all 16 test questions through the subagent design, score
routing accuracy / key-point coverage / citation presence / out-of-scope
handling, and write results to a CSV evaluation sheet.

Resumable: if the CSV from a previous run already has a result for a
question, that question is skipped. This matters on the Gemini free
tier, which can have a very low daily request quota (as low as 20
requests/day on some models) — if you hit a 429 partway through, just
re-run this same command (today or tomorrow once the quota resets) and
it will continue from where it left off instead of starting over.

Run: python -m eval.run_eval
Run a small 6-question representative subset instead of all 16 (useful
when a free-tier daily quota makes 16 questions impractical in one day):
python -m eval.run_eval --quick
"""

import csv
import re
import sys
import time
from pathlib import Path

from graph.workflow import run_query
from eval.test_questions import TEST_SET, QUICK_SUBSET_IDS
from common.gemini_setup import is_daily_quota_exhausted

QUICK_MODE = "--quick" in sys.argv
ACTIVE_SET = [c for c in TEST_SET if c["id"] in QUICK_SUBSET_IDS] if QUICK_MODE else TEST_SET

OUTPUT_CSV = Path(__file__).resolve().parent / (
    "eval_results_subagent_quick.csv" if QUICK_MODE else "eval_results_subagent.csv"
)
SLEEP_BETWEEN_QUESTIONS_SECONDS = 5  # be gentle on free-tier per-minute limits

CITATION_RE = re.compile(r"\[KSPL-[A-Z]+-POL-\d+,\s*section\s*[\d.]+\]", re.IGNORECASE)

FIELDNAMES = [
    "id", "question", "departments_expected", "departments_chosen",
    "routing_correct", "key_points_hit", "key_points_total",
    "citations_found", "citation_ok", "conflict_expected", "conflict_flagged",
    "conflict_ok", "time_seconds", "tokens", "status", "answer",
]


def key_point_hits(answer: str, key_points: list[str]) -> tuple[int, int]:
    """Very lightweight coverage check: how many key phrases appear
    (case-insensitively, allowing minor wording differences) in the answer."""
    lower = answer.lower()
    hits = 0
    for kp in key_points:
        if kp.lower() in lower:
            hits += 1
        else:
            tokens = [t for t in re.findall(r"[a-zA-Z0-9%]+", kp.lower()) if len(t) > 2]
            if tokens and all(t in lower for t in tokens):
                hits += 1
    return hits, len(key_points)


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


def score_one(case: dict, result: dict, elapsed: float) -> dict:
    chosen_depts = sorted(result["plan"].departments)
    expected_depts = sorted(case["expected_departments"])
    if case["id"] == 13:
        routing_ok = set(chosen_depts) <= {"finance", "hr"} and "finance" in chosen_depts
    else:
        routing_ok = chosen_depts == expected_depts

    answer = result["final"].answer
    hits, n_points = key_point_hits(answer, case["key_points"])

    citations_found = len(CITATION_RE.findall(answer))
    has_findings = len(result["findings"]) > 0
    citation_ok = (citations_found > 0) if has_findings else True

    conflict_expected = case["id"] in (12, 14)
    conflict_flagged = result["final"].conflict_detected

    return {
        "id": case["id"],
        "question": case["question"],
        "departments_expected": ",".join(expected_depts),
        "departments_chosen": ",".join(chosen_depts),
        "routing_correct": routing_ok,
        "key_points_hit": hits,
        "key_points_total": n_points,
        "citations_found": citations_found,
        "citation_ok": citation_ok,
        "conflict_expected": conflict_expected,
        "conflict_flagged": conflict_flagged,
        "conflict_ok": (conflict_flagged == conflict_expected) if conflict_expected else True,
        "time_seconds": round(elapsed, 2),
        "tokens": result.get("total_tokens", 0),
        "status": "ok",
        "answer": answer,
    }


def run_evaluation():
    if QUICK_MODE:
        print(f"Quick mode: running {len(ACTIVE_SET)} representative questions {QUICK_SUBSET_IDS} instead of all 16.\n")

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
            result = run_query(case["question"], case["profile"])
            elapsed = time.time() - start
            row = score_one(case, result, elapsed)
            rows_by_id[case["id"]] = row
            write_rows(rows_by_id)  # save progress after every question
            print(f"  -> done in {elapsed:.1f}s")
        except Exception as exc:
            elapsed = time.time() - start
            print(f"  -> FAILED after {elapsed:.1f}s: {exc}")
            rows_by_id[case["id"]] = {
                "id": case["id"], "question": case["question"],
                "departments_expected": ",".join(sorted(case["expected_departments"])),
                "departments_chosen": "", "routing_correct": "", "key_points_hit": "",
                "key_points_total": "", "citations_found": "", "citation_ok": "",
                "conflict_expected": "", "conflict_flagged": "", "conflict_ok": "",
                "time_seconds": round(elapsed, 2), "tokens": "", "status": f"failed: {exc}",
                "answer": "",
            }
            write_rows(rows_by_id)
            failed_ids.append(case["id"])

            if is_daily_quota_exhausted(exc):
                print(
                    "\n  Daily API quota exhausted — every remaining question would fail the same "
                    "way right now, so stopping here instead of waiting on each one. Re-run this "
                    "same command after your quota resets (check the error above for the reset "
                    "time, or just try again in a few hours / tomorrow)."
                )
                break

        time.sleep(SLEEP_BETWEEN_QUESTIONS_SECONDS)

    ok_rows = [r for r in rows_by_id.values() if r.get("status") == "ok"]
    n_ok = len(ok_rows)
    n_total = len(ACTIVE_SET)

    print(f"\n=== SUMMARY (subagent design) — {n_ok}/{n_total} questions completed ===")
    if n_ok:
        routing_correct = sum(1 for r in ok_rows if str(r["routing_correct"]) == "True")
        total_key_hits = sum(int(r["key_points_hit"]) for r in ok_rows)
        total_key_points = sum(int(r["key_points_total"]) for r in ok_rows)
        citation_ok_count = sum(1 for r in ok_rows if str(r["citation_ok"]) == "True")
        total_time = sum(float(r["time_seconds"]) for r in ok_rows)

        print(f"Routing accuracy: {routing_correct}/{n_ok} = {routing_correct/n_ok:.0%}")
        if total_key_points:
            print(f"Key-point coverage: {total_key_hits}/{total_key_points} = {total_key_hits/total_key_points:.0%}")
        print(f"Citation presence: {citation_ok_count}/{n_ok} = {citation_ok_count/n_ok:.0%}")
        print(f"Avg time/question: {total_time/n_ok:.2f}s")

    if failed_ids:
        print(f"\n{len(failed_ids)} question(s) FAILED this run (likely rate-limited): {failed_ids}")
        rerun_cmd = "python -m eval.run_eval --quick" if QUICK_MODE else "python -m eval.run_eval"
        print(f"Re-run `{rerun_cmd}` later (e.g. after your daily quota resets) to fill these in.")
    elif n_ok == n_total:
        print(f"\nAll {n_total} question(s) completed successfully.")

    print(f"\nWrote {OUTPUT_CSV}")


if __name__ == "__main__":
    run_evaluation()
