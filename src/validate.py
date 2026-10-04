"""Validate candidate SQL against the golden set — the deterministic half.

Run:  python src/validate.py                                        (the committed receipt)
      python src/validate.py --candidates <file> --outdir <dir>     (a dated re-run)

Two things happen, in order:

1. The golden fingerprints are recomputed from the live DuckDB build and must
   match eval/golden_set.yaml exactly — this is the byte-reproducible receipt
   for the database build and the golden set. If they differ (a re-pull moved
   the data), this exits 1 rather than silently re-pinning.
2. Every committed candidate attempt is replayed under the guardrails
   (src/guardrails.py) and compared via the shared canonical serializer
   (src/fingerprint.py). The verdict vocabulary is explicit:
   pass_first_try | pass_after_retry | fail, with mismatch types
   sql_error | guardrail_reject | timeout | wrong_row_count | value_mismatch.

Outputs (temp + atomic replace; a failed run touches nothing):
  <outdir>/results.csv    per question: verdicts for both attempts
  <outdir>/summary.json   the as-of receipt: model id + run date + counts

The committed outputs/ files are the receipt of the as-of run. A re-run writes
only to its own --outdir (default outputs/reruns/<date>/ via src/generate.py);
with a non-default --candidates and no --outdir, results land beside the
candidates file — the committed receipt is never a re-run's default target.
Your re-run will differ — compare the two summary.json files.
"""
import argparse
import csv
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.fingerprint import fingerprint, load_golden, golden_fingerprints  # noqa: E402
from src.guardrails import execute_sql  # noqa: E402

RESULTS_COLS = ["question_id", "type", "trap", "status", "mismatch_type", "attempts",
                "attempt1_status", "attempt1_mismatch", "attempt2_status", "attempt2_mismatch", "note"]


def classify(res, want):
    """(mismatch_type or '' , note) for one executed attempt."""
    if res["outcome"] == "guardrail_reject":
        return "guardrail_reject", res.get("note", "")
    if res["outcome"] == "timeout":
        return "timeout", res.get("note", "")
    if res["outcome"] == "sql_error":
        return "sql_error", res.get("note", "")
    n, h = fingerprint(res["rows"])
    if n != want.get("rows"):
        return "wrong_row_count", f"rows {n} != {want.get('rows')}"
    if h != want.get("sha256"):
        return "value_mismatch", f"rows {n} right, sha {h[:12]} != {str(want.get('sha256'))[:12]}"
    return "", ""   # exact fingerprint match = pass


def run_attempt(sql, want):
    res = execute_sql(sql)
    mm, note = classify(res, want)
    return {"ok": res["outcome"] == "ok" and mm == "", "mismatch": mm, "note": note}


def atomic_write(path, text):
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", default=str(ROOT / "outputs/candidates.jsonl"))
    ap.add_argument("--outdir", default=None,
                    help="default: outputs/ for the committed candidates, else the candidates file's parent dir")
    args = ap.parse_args()

    cand_path = Path(args.candidates)
    if args.outdir is not None:
        out_dir = Path(args.outdir)
    elif args.candidates != ap.get_default("candidates"):
        out_dir = cand_path.parent   # a re-run never overwrites the committed receipt
    else:
        out_dir = ROOT / "outputs"
    golden = load_golden()

    # 1 — golden fingerprints must reproduce from the database (deterministic receipt)
    recomputed = golden_fingerprints(golden)
    drift = [q["id"] for q in golden["questions"]
             if (q.get("fingerprint") or {}).get("rows") != recomputed[q["id"]][0]
             or (q.get("fingerprint") or {}).get("sha256") != recomputed[q["id"]][1]]
    if drift:
        print(f"GOLDEN FINGERPRINT DRIFT: {drift}")
        print("the database no longer matches eval/golden_set.yaml — if the input data changed,")
        print("re-pin only after re-auditing: python src/fingerprint.py --write")
        return 1
    print(f"golden fingerprints: {len(golden['questions'])}/{len(golden['questions'])} reproduce from the database")

    # 2 — replay candidates
    meta = {}
    cand = {}
    with cand_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if "meta" in rec:
                meta = rec["meta"]
            else:
                cand[rec["id"]] = rec
    missing = [q["id"] for q in golden["questions"] if q["id"] not in cand]
    if missing:
        print(f"no candidates for: {missing}")
        return 1

    rows, counts = [], {"pass_first_try": 0, "pass_after_retry": 0, "fail": 0}
    mm_counts = {}
    models_used = sorted({cand[q["id"]].get("model") or meta.get("model")
                          for q in golden["questions"]})
    for q in golden["questions"]:
        want = q.get("fingerprint") or {}
        atts = cand[q["id"]]["attempts"]
        a1 = run_attempt(atts[0]["sql"], want)
        a2 = run_attempt(atts[1]["sql"], want) if len(atts) > 1 else None
        if a1["ok"]:
            status, attempts_used = "pass_first_try", 1
        elif a2 and a2["ok"]:
            status, attempts_used = "pass_after_retry", 2
        else:
            status, attempts_used = "fail", len(atts)
        counts[status] += 1
        mm = "" if status.startswith("pass") else (a2 or a1)["mismatch"]
        if mm:
            mm_counts[mm] = mm_counts.get(mm, 0) + 1
        note = "" if status == "pass_first_try" else (a2 or a1)["note"][:120]
        rows.append({
            "question_id": q["id"], "type": q["type"], "trap": "true" if q["trap"] else "false",
            "status": status, "mismatch_type": mm, "attempts": attempts_used,
            "attempt1_status": "pass" if a1["ok"] else a1["mismatch"],
            "attempt1_mismatch": "" if a1["ok"] else a1["mismatch"],
            "attempt2_status": ("" if a2 is None else ("pass" if a2["ok"] else a2["mismatch"])),
            "attempt2_mismatch": ("" if a2 is None or a2["ok"] else a2["mismatch"]),
            "note": note,
        })

    by_type = {}
    for r in rows:
        t = by_type.setdefault(r["type"], {"n": 0, "passed": 0})
        t["n"] += 1
        t["passed"] += r["status"].startswith("pass")
    by_trap = {"true": {"n": 0, "passed": 0}, "false": {"n": 0, "passed": 0}}
    for r in rows:
        t = by_trap[r["trap"]]
        t["n"] += 1
        t["passed"] += r["status"].startswith("pass")

    summary = {
        "receipt": {
            "model": meta.get("model"), "models_used": models_used,
            "run_date": meta.get("run_date"),
            "temperature": meta.get("temperature"), "max_tokens": meta.get("max_tokens"),
            "prompt": meta.get("prompt"), "golden_set_version": golden.get("version"),
            "golden_fingerprints_verified": True,
            "candidates_file": cand_path.name,
        },
        "totals": {"questions": len(rows), **counts,
                   "passed": counts["pass_first_try"] + counts["pass_after_retry"]},
        "mismatch_counts": dict(sorted(mm_counts.items())),
        "by_type": {k: by_type[k] for k in sorted(by_type)},
        "by_trap": by_trap,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "results.csv"
    tmp = csv_path.with_name(csv_path.name + ".part")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RESULTS_COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, csv_path)
    atomic_write(out_dir / "summary.json", json.dumps(summary, indent=2) + "\n")

    t = summary["totals"]
    print(f"results:  {t['pass_first_try']}/{t['questions']} first-try, "
          f"{t['pass_after_retry']} after one retry, {t['fail']} fail")
    print(f"mismatches: {summary['mismatch_counts']}")
    print(f"wrote {csv_path} and {out_dir / 'summary.json'}")

    committed = ROOT / "outputs/summary.json"
    if out_dir.resolve() != (ROOT / "outputs").resolve() and committed.exists():
        old = json.loads(committed.read_text(encoding="utf-8"))
        print(f"committed receipt was: {old['totals']['pass_first_try']}/{old['totals']['questions']} first-try, "
              f"{old['totals']['pass_after_retry']} after retry, {old['totals']['fail']} fail "
              f"(model {old['receipt']['model']}, {old['receipt']['run_date']})")
        print("your re-run will differ — that is expected; compare the two summary.json files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
