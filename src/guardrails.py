"""Execution guardrails for candidate SQL — the trust boundary of the whole repo.

Every candidate statement passes ALL of these before a row is fetched:

1. Parse-based single-SELECT check (sqlglot, DuckDB dialect) — exactly one
   statement, top level SELECT (WITH ... SELECT / UNION allowed). A
   `startswith('select')` check is NOT sufficient and is not used here.
2. Blocked outright: DDL/DML, ATTACH/COPY/PRAGMA/SET and any other command
   type; any table other than `resale` (or a CTE defined in the statement);
   table functions that touch the filesystem or the catalog (read_csv,
   read_parquet, glob, pragma_*, *_scan, ...).
3. Read-only DuckDB connection to the built database.
4. Wall-clock watchdog (DuckDB has no statement timeout): `con.interrupt()`
   fires after `timeout_s` and the attempt is classified `timeout`.
5. Row cap (10,000): fetching more rows than the cap is a guardrail reject,
   not an answer.

Outcomes (the vocabulary used across outputs/): ok | guardrail_reject |
timeout | sql_error. Nothing here modifies the database — it is opened
read_only.
"""
import sys
import threading
from pathlib import Path

import duckdb
import sqlglot
from sqlglot import exp

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data/processed/resale.duckdb"

TIMEOUT_S = 15
ROW_CAP = 10_000

# Command/statement types that must never appear anywhere in a candidate.
FORBIDDEN_TYPES = tuple(
    t for name in ("Insert", "Update", "Delete", "Create", "Drop", "Alter", "Copy",
                   "Pragma", "Attach", "Detach", "Set", "Command", "Transaction",
                   "Commit", "Rollback", "Grant", "Merge", "TruncateTable", "Upsert",
                   "Analyze", "Describe", "Explain", "Uncache", "Cache")
    if (t := getattr(exp, name, None)) is not None
)

# Function names that reach outside the database file (filesystem / catalog scans).
FORBIDDEN_FUNCS = {
    "read_csv", "read_csv_auto", "read_parquet", "read_json", "read_json_auto",
    "read_ndjson", "read_ndjson_auto", "read_text", "read_blob", "glob", "sniff_csv",
    "parquet_scan", "parquet_metadata", "parquet_schema", "csv_scan", "json_scan",
    "sqlite_scan", "postgres_scan", "mysql_scan", "pragma_database_list",
    "pragma_table_info", "duckdb_columns", "duckdb_tables", "duckdb_functions",
    "read_xlsx", "delta_scan", "iceberg_scan",
}
ALLOWED_TABLE = "resale"


def check_sql(sql):
    """Return (ok, reason). Parse-based; rejects anything not provably a single
    read-only SELECT over the `resale` table."""
    if not isinstance(sql, str) or not sql.strip():
        return False, "empty SQL"
    try:
        statements = sqlglot.parse(sql, read="duckdb")
    except Exception as exc:
        return False, f"unparseable SQL ({type(exc).__name__}: {str(exc)[:160]})"
    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        return False, f"{len(statements)} statements — exactly one is required"
    stmt = statements[0]
    if not isinstance(stmt, (exp.Select, exp.Union)):
        return False, f"top level is {type(stmt).__name__}, not a SELECT"

    # CTE names may be referenced as tables; everything else must be `resale`.
    # DuckDB identifiers are case-insensitive, so fold case before comparing.
    cte_names = {(c.alias_or_name or "").lower() for c in stmt.find_all(exp.CTE)}
    for node in stmt.find_all(*FORBIDDEN_TYPES):
        return False, f"blocked statement type: {type(node).__name__}"
    for node in stmt.find_all(exp.Table):
        name = node.name.lower()
        if name != ALLOWED_TABLE and name not in cte_names:
            return False, f"table {node.name!r} is not allowed (only {ALLOWED_TABLE!r} or a CTE)"
    for node in stmt.find_all(exp.Func):
        fn = (node.name or "").lower()
        if fn in FORBIDDEN_FUNCS or fn.startswith("read_") or fn.endswith("_scan") or fn.startswith("pragma_"):
            return False, f"blocked function: {fn}"
    return True, "ok"


def execute_sql(sql, timeout_s=TIMEOUT_S, row_cap=ROW_CAP, as_of=None):
    """Run one candidate under the guardrails. Returns a dict:
    outcome: ok | guardrail_reject | timeout | sql_error
    rows:    list of tuples (outcome == ok only)
    note:    short reason (non-ok outcomes)"""
    ok, reason = check_sql(sql)
    if not ok:
        return {"outcome": "guardrail_reject", "note": reason}

    if as_of is not None:
        from datetime import date
        day = date.fromisoformat(as_of).isoformat()
        tree = sqlglot.parse_one(sql, read="duckdb")
        tree = tree.transform(lambda node: sqlglot.parse_one(f"DATE '{day}'", read="duckdb")
                              if isinstance(node, exp.CurrentDate) else node)
        sql = tree.sql(dialect="duckdb")
    con = duckdb.connect(str(DB), read_only=True)
    watchdog = threading.Timer(timeout_s, con.interrupt)
    watchdog.start()
    try:
        rel = con.sql(sql)
        if rel is None:
            return {"outcome": "sql_error", "note": "statement returned no result set"}
        rows = rel.fetchmany(row_cap + 1)
        if len(rows) > row_cap:
            return {"outcome": "guardrail_reject", "note": f"row cap exceeded ({row_cap})"}
        return {"outcome": "ok", "rows": rows}
    except (duckdb.InterruptException, KeyboardInterrupt):
        return {"outcome": "timeout", "note": f"interrupted after {timeout_s}s"}
    except Exception as exc:  # noqa: BLE001 — classify, don't crash the runner
        return {"outcome": "sql_error", "note": f"{type(exc).__name__}: {str(exc)[:200]}"}
    finally:
        watchdog.cancel()
        con.close()


if __name__ == "__main__":
    # tiny self-check: the guardrails reject the obvious escapes
    bad = ["DROP TABLE resale", "SELECT 1; SELECT 2", "COPY resale TO 'x.csv'",
           "PRAGMA table_info('resale')", "SELECT * FROM read_csv_auto('data/raw/x.csv')",
           "ATTACH 'x.duckdb' AS other", "INSERT INTO resale VALUES (1)", "DELETE FROM resale"]
    for sql in bad:
        ok, why = check_sql(sql)
        assert not ok, f"guardrail missed: {sql}"
        print(f"  rejected: {sql!r} -> {why}")
    ok, why = check_sql("SELECT count(*) FROM resale")
    assert ok, why
    print("  accepted: 'SELECT count(*) FROM resale'")
    # identifiers are case-insensitive in DuckDB (issue #2): valid SQL must not
    # be misclassified as guardrail_reject, and non-allowlisted tables still must.
    for sql in ["SELECT count(*) FROM RESALE", "SELECT count(*) FROM Resale",
                "SELECT count(*) FROM \"RESALE\"",
                "WITH x AS (SELECT 1 AS a) SELECT * FROM X"]:
        ok, why = check_sql(sql)
        assert ok, f"false reject: {sql!r} -> {why}"
        print(f"  accepted: {sql!r}")
    ok, why = check_sql("SELECT count(*) FROM EVIL")
    assert not ok, "guardrail missed: FROM EVIL"
    print(f"  rejected: 'SELECT count(*) FROM EVIL' -> {why}")
    print("guardrail self-check PASS")
