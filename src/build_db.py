"""Build the DuckDB database: raw CSV -> table `resale` (sql/00) -> checks (sql/01).

Run: python src/build_db.py
Receipts printed: raw/staged/excluded counts (per rule, reconciled) and check results.
Exit 1 if any check fails.

Order matters: staging + checks run against a TEMP database file; the real
data/processed/resale.duckdb is replaced only after every check passes — a
failing run never touches the existing database.
"""
import os
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "sql/00_build_db.sql"
CHECKS = ROOT / "sql/01_checks.sql"
OUT = ROOT / "data/processed/resale.duckdb"
RAW = ROOT / "data/raw/hdb-resale-prices-2017-onwards.csv"

# Exclusion rules — must mirror the WHERE clause in sql/00. A row is excluded if ANY rule matches.
RULES = [
    ("price null or <= 0", "resale_price IS NULL OR resale_price <= 0"),
    ("area null or <= 0", "floor_area_sqm IS NULL OR floor_area_sqm <= 0"),
    ("bad month", "try_strptime(month, '%Y-%m') IS NULL"),
    ("no lease text", "remaining_lease IS NULL"),
]
ANY_RULE = "NOT (" + " AND ".join(f"NOT ({expr})" for _, expr in RULES) + ")"


def q(con, sql):
    return con.sql(sql).fetchall()


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from src.download import validate
    _, problems = validate(RAW.read_bytes())
    if problems:
        raise SystemExit("raw source validation failed: " + "; ".join(problems))
    os.chdir(ROOT)  # sql/00 references data/raw relatively
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_name(OUT.name + ".tmp")
    tmp.unlink(missing_ok=True)

    raw_rel = RAW.name  # read via a view on the raw CSV, path escaped for SQL
    raw_sql = (RAW.parent.as_posix() + "/" + raw_rel).replace("'", "''")

    con = duckdb.connect(str(tmp))
    try:
        raw_n = q(con, f"SELECT count(*) FROM read_csv_auto('{raw_sql}')")[0][0]
        con.execute(f"CREATE OR REPLACE VIEW raw_rows AS SELECT * FROM read_csv_auto('{raw_sql}')")
        con.execute(BUILD.read_text(encoding="utf-8"))
        out_n = q(con, "SELECT count(*) FROM resale")[0][0]
        excl_any = q(con, f"SELECT count(*) FROM raw_rows WHERE {ANY_RULE}")[0][0]
        print(f"raw rows:    {raw_n}")
        print(f"staged rows: {out_n}")
        print(f"excluded:    {raw_n - out_n}  ({100 * (raw_n - out_n) / raw_n:.3f}%)")
        print("exclusion rules (per-rule counts; a row may match more than one):")
        for rule, expr in RULES:
            k = q(con, f"SELECT count(*) FROM raw_rows WHERE {expr}")[0][0]
            print(f"    rule [{rule}]: {k}")
        ok_recon = (out_n + excl_any) == raw_n
        print(f"    [{'PASS' if ok_recon else 'FAIL'}] retained + excluded == raw ({out_n} + {excl_any} vs {raw_n})")

        print("checks:")
        failed = not ok_recon
        for name, v in con.execute(CHECKS.read_text(encoding="utf-8")).fetchall():
            status = "PASS" if v == 0 else "FAIL"
            print(f"    [{status}] {name}  (violations: {v})")
            if v:
                failed = True

        import hashlib
        con.execute("CREATE OR REPLACE TABLE source_receipt (sha256 VARCHAR)")
        con.execute("INSERT INTO source_receipt VALUES (?)", [hashlib.sha256(RAW.read_bytes()).hexdigest()])
        if failed:
            print("checks failed — database NOT written (existing file left untouched)")
            sys.exit(1)
    finally:
        con.close()

    os.replace(tmp, OUT)
    print(f"wrote: {OUT.as_posix()}  ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
