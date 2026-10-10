"""The ONE canonical result serializer + fingerprint, shared by golden-set
authoring and candidate comparison.

A result fingerprint is  (row_count, sha256 over the ordered rows)  where every
cell goes through `canonical_cell` first:

  - numbers (int, float, Decimal) -> fixed 2-decimal formatting, so an INTEGER
    count and a DOUBLE count of the same value compare equal, and materially
    different values never do;
  - None -> the literal 'null'; dates -> ISO (YYYY-MM-DD); strings -> as-is.

Rows are joined with US (0x1f) / RS (0x1e). ORDER IS PART OF THE CONTRACT:
golden queries all carry a deterministic ORDER BY (the ordering convention in
eval/golden_set.yaml), and a candidate in a different order fingerprints
differently.

Run: python src/fingerprint.py           recompute every golden fingerprint
                                          from the database and verify it
       python src/fingerprint.py --write  fill/refresh fingerprints in the YAML
"""
import hashlib
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "eval/golden_set.yaml"

RS, US = "\x1e", "\x1f"


def canonical_cell(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float, Decimal)):
        return f"{float(v):.2f}"
    if hasattr(v, "isoformat"):  # date / datetime
        return v.isoformat()[:10]
    return str(v)


def fingerprint(rows, version=1):
    """Version 1 preserves historical pins; version 2 frames typed cells.

    Numeric equivalence is explicitly two decimal places, without a float
    conversion of integers/Decimals. Dates and full timestamps remain distinct.
    """
    if version == 1:
        payload = RS.join(US.join(canonical_cell(c) for c in row) for row in rows)
    elif version == 2:
        import json
        from datetime import date, datetime
        def cell(v):
            if v is None:
                return ["null"]
            if isinstance(v, bool):
                return ["bool", v]
            if isinstance(v, (int, float, Decimal)):
                number = Decimal(str(v))
                if not number.is_finite():
                    raise ValueError("non-finite result number")
                return ["number", format(number, ".2f") if number else "0.00"]
            if isinstance(v, datetime):
                return ["datetime", v.isoformat()]
            if isinstance(v, date):
                return ["date", v.isoformat()]
            if isinstance(v, str):
                return ["text", v]
            raise TypeError(f"unsupported result type: {type(v).__name__}")
        payload = json.dumps([[cell(v) for v in row] for row in rows],
                             ensure_ascii=False, separators=(",", ":"))
    else:
        raise ValueError("unsupported fingerprint version")
    return len(rows), hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_golden():
    import yaml
    return yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))


def golden_fingerprints(golden=None):
    """Recompute every golden fingerprint from the live database."""
    import duckdb
    from src.guardrails import DB
    golden = golden or load_golden()
    con = duckdb.connect(str(DB), read_only=True)
    out = {}
    try:
        for q in golden["questions"]:
            rows = con.sql(q["sql"]).fetchall()
            out[q["id"]] = fingerprint(rows)
    finally:
        con.close()
    return out


def main():
    sys.path.insert(0, str(ROOT))
    import yaml
    golden = load_golden()
    recomputed = golden_fingerprints(golden)
    bad = 0
    for q in golden["questions"]:
        want = q.get("fingerprint") or {}
        got = recomputed[q["id"]]
        ok = want.get("rows") == got[0] and want.get("sha256") == got[1]
        if not ok:
            bad += 1
        print(f"  [{'ok' if ok else 'MISMATCH'}] {q['id']}  rows={got[0]}  {got[1][:16]}"
              + ("" if ok else f"   (yaml: rows={want.get('rows')} {str(want.get('sha256'))[:16]})"))
    if "--write" in sys.argv:
        for q in golden["questions"]:
            n, h = recomputed[q["id"]]
            q["fingerprint"] = {"rows": n, "sha256": h}
        part = GOLDEN.with_name(GOLDEN.name + ".part")
        part.write_text(yaml.safe_dump(golden, sort_keys=False, allow_unicode=True, width=100),
                        encoding="utf-8", newline="\n")
        import os
        os.replace(part, GOLDEN)
        print(f"wrote fingerprints for {len(golden['questions'])} questions -> {GOLDEN.name}")
    print(f"{len(golden['questions']) - bad}/{len(golden['questions'])} fingerprints match the database")
    return 1 if (bad and "--write" not in sys.argv) else 0


if __name__ == "__main__":
    sys.exit(main())
