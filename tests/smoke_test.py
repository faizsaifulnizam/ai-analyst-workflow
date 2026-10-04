"""Committed-artifact smoke test — stdlib only, no network, no LLM calls.

Run:  python tests/smoke_test.py        (also runs under pytest)

Design rules (series standard):
- asserts COMMITTED artifacts only (outputs/, eval/, reports/figures/, docs/img/);
- required-column SUBSET on CSV headers, never exact header equality;
- numeric anchors are conditioned on the receipt's NAMED AS-OF RUN DATE and only
  updated on a publisher restatement or an explicit new snapshot — never because
  a re-run of the non-deterministic generation step differs;
- figures = existence + size floors in BOTH themes;
- potency: substituting an implausible pass count at the artifact-loading
  boundary must make these checks FAIL (see test_potency).

The LLM generation step itself is a dated receipt and is never re-run or
byte-diffed here.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SUMMARY = ROOT / "outputs" / "summary.json"
RESULTS = ROOT / "outputs" / "results.csv"
CANDIDATES = ROOT / "outputs" / "candidates.jsonl"
GOLDEN = ROOT / "eval" / "golden_set.yaml"

REQUIRED_COLS = {"question_id", "type", "trap", "status", "mismatch_type", "attempts"}
VALID_STATUS = {"pass_first_try", "pass_after_retry", "fail"}
VALID_MISMATCH = {"", "value_mismatch", "wrong_row_count", "sql_error", "guardrail_reject", "timeout"}

# Numeric anchors per named as-of run (model id + run date recorded in summary.json).
# Update ONLY for a publisher restatement or an explicit snapshot change.
RUN_ANCHORS: dict[str, dict[str, int]] = {
    # as-of receipt 2026-10-04 (models gemini-3.7/3.5/3.1-flash; see docs/model_note.md)
    "2026-10-04": {"questions": 32, "pass_first_try": 27, "pass_after_retry": 0, "fail": 5},
}

EXPECTED_FIGURES = [
    "f2_pass_rate.png", "f2_pass_rate-dark.png",
    "f3_failures.png", "f3_failures-dark.png",
]
MIN_FIGURE_BYTES = 5000
N_QUESTIONS = 32


def load_summary(path: Path = SUMMARY) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_results(path: Path = RESULTS) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def check_summary(summary: dict) -> None:
    """All summary-level invariants; raises AssertionError on anything implausible."""
    r = summary["receipt"]
    assert r.get("run_date"), "receipt must carry the as-of run date"
    assert r.get("model") or r.get("models_used"), "receipt must carry the model id(s)"
    assert r.get("golden_fingerprints_verified") is True, "golden fingerprints must be verified"
    t = summary["totals"]
    assert t["questions"] == N_QUESTIONS, f"expected {N_QUESTIONS} questions, got {t['questions']}"
    assert t["pass_first_try"] + t["pass_after_retry"] + t["fail"] == t["questions"], \
        "verdict counts must sum to the question count"
    assert t["passed"] == t["pass_first_try"] + t["pass_after_retry"], "passed must equal first-try + after-retry"
    for k in ("pass_first_try", "pass_after_retry", "fail"):
        assert 0 <= t[k] <= t["questions"], f"{k} out of range: {t[k]}"
    anchors = RUN_ANCHORS.get(r["run_date"])
    if anchors:
        for k, v in anchors.items():
            assert t[k] == v, f"anchor {k} for run {r['run_date']}: got {t[k]}, expected {v}"


def test_summary() -> None:
    check_summary(load_summary())


def test_results_schema() -> None:
    rows = load_results()
    assert len(rows) == N_QUESTIONS, f"{len(rows)} result rows, expected {N_QUESTIONS}"
    missing = REQUIRED_COLS - set(rows[0].keys())
    assert not missing, f"results.csv missing columns: {sorted(missing)}"
    ids = [r["question_id"] for r in rows]
    assert len(set(ids)) == N_QUESTIONS, "duplicate question_id in results.csv"
    for r in rows:
        assert r["status"] in VALID_STATUS, f"{r['question_id']}: bad status {r['status']!r}"
        assert r["mismatch_type"] in VALID_MISMATCH, f"{r['question_id']}: bad mismatch {r['mismatch_type']!r}"
        assert r["trap"] in ("true", "false"), f"{r['question_id']}: bad trap flag"
        assert int(r["attempts"]) in (1, 2), f"{r['question_id']}: attempts must be 1 or 2"
        if r["status"].startswith("pass"):
            assert r["mismatch_type"] == "", f"{r['question_id']}: passing row carries a mismatch"


def test_results_agree_with_summary() -> None:
    rows = load_results()
    summary = load_summary()
    t = summary["totals"]
    n_first = sum(1 for r in rows if r["status"] == "pass_first_try")
    n_retry = sum(1 for r in rows if r["status"] == "pass_after_retry")
    n_fail = sum(1 for r in rows if r["status"] == "fail")
    assert (n_first, n_retry, n_fail) == (t["pass_first_try"], t["pass_after_retry"], t["fail"]), \
        f"results.csv says {(n_first, n_retry, n_fail)}, summary.json says {(t['pass_first_try'], t['pass_after_retry'], t['fail'])}"


def test_candidates_receipt() -> None:
    meta, records = None, []
    for line in CANDIDATES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        (records.append(rec) if "meta" not in rec else None)
        if "meta" in rec:
            meta = rec["meta"]
    assert meta is not None, "candidates.jsonl must start with a meta line"
    assert meta.get("run_date"), "meta line must carry the run date"
    assert meta.get("model"), "meta line must carry the model id"
    assert len(records) == N_QUESTIONS, f"{len(records)} candidate records, expected {N_QUESTIONS}"
    for rec in records:
        assert rec["attempts"], f"{rec['id']}: no attempts recorded"
        assert len(rec["attempts"]) <= 2, f"{rec['id']}: more than 2 attempts (retry cap)"


def test_golden_set_shape() -> None:
    text = GOLDEN.read_text(encoding="utf-8")
    n_ids = text.count("\n- id: ") + (1 if text.startswith("- id: ") else 0)
    n_traps = text.count("trap: true")
    assert n_ids == N_QUESTIONS, f"golden set has {n_ids} questions, expected {N_QUESTIONS}"
    assert n_traps == 6, f"golden set has {n_traps} traps, expected 6"


def test_figures_present() -> None:
    for d in (ROOT / "reports" / "figures", ROOT / "docs" / "img"):
        missing = [n for n in EXPECTED_FIGURES if not (d / n).is_file()]
        assert not missing, f"{d.name}: missing figures {missing}"
        small = [n for n in EXPECTED_FIGURES if (d / n).stat().st_size < MIN_FIGURE_BYTES]
        assert not small, f"{d.name}: suspiciously small figures {small}"


def test_potency() -> None:
    """Substituting an implausible pass count at the loading boundary must FAIL the checks."""
    good = load_summary()
    bad = json.loads(json.dumps(good))
    bad["totals"]["pass_first_try"] = bad["totals"]["questions"] + 7   # impossible
    bad["totals"]["passed"] = bad["totals"]["pass_first_try"]
    try:
        check_summary(bad)
    except AssertionError:
        print("   potency: implausible pass count rejected by check_summary")
    else:
        raise AssertionError("POTENCY FAILED: an implausible pass count passed the summary checks")

    rows = load_results()
    doctored = json.loads(json.dumps(rows))
    for r in doctored:
        r["status"] = "pass_first_try"
    n_first = sum(1 for r in doctored if r["status"] == "pass_first_try")
    t = good["totals"]
    if n_first != t["pass_first_try"]:
        print("   potency: doctored results.csv would disagree with summary.json (cross-check live)")
    else:
        raise AssertionError("POTENCY FAILED: doctored results would silently agree with the summary")


def main() -> int:
    checks = [test_summary, test_results_schema, test_results_agree_with_summary,
              test_candidates_receipt, test_golden_set_shape, test_figures_present, test_potency]
    failed = 0
    for fn in checks:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001 — report, don't crash the runner
            failed += 1
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"{len(checks) - failed}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
