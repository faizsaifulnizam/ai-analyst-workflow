"""Regression: a non-default --candidates without --outdir must never touch the
committed receipt (outputs/results.csv, outputs/summary.json) — the re-run
invariant ("a re-run never overwrites the committed receipt") has to hold for
validate.py's defaults, not only for the documented command lines.

Run:  python tests/test_validate_outdir.py   (needs the documented .venv + built DB)
# ponytail: dependency-backed (duckdb replay) by nature, so it runs locally in
# the documented environment and stays out of the stdlib-only CI smoke job.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = [ROOT / "outputs" / "results.csv", ROOT / "outputs" / "summary.json"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    before = {p: sha(p) for p in RECEIPT}
    with tempfile.TemporaryDirectory() as td:
        cand = Path(td) / "candidates.jsonl"
        shutil.copy(ROOT / "outputs" / "candidates.jsonl", cand)
        r = subprocess.run(
            [sys.executable, str(ROOT / "src" / "validate.py"), "--candidates", str(cand)],
            cwd=ROOT, capture_output=True, text=True)
        assert r.returncode == 0, f"validate.py failed:\n{r.stdout}\n{r.stderr}"
        assert (Path(td) / "results.csv").is_file(), \
            "results did not land beside the non-default candidates file"
        assert (Path(td) / "summary.json").is_file(), \
            "summary did not land beside the non-default candidates file"
        after = {p: sha(p) for p in RECEIPT}
        assert before == after, \
            f"committed receipt changed: {[str(p) for p in RECEIPT if before[p] != after[p]]}"
    print("PASS  non-default --candidates without --outdir leaves outputs/ untouched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
