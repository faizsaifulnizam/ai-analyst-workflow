# data/raw — provenance

Raw files land here and are never edited or committed (gitignored). This repo re-downloads its own copy:

- **Dataset:** HDB Resale Flat Prices (registration date, Jan-2017 onwards) — data.gov.sg `d_8b84c4ee58e3cfc0ece0d773c8ca6abc` — https://data.gov.sg/datasets/d_8b84c4ee58e3cfc0ece0d773c8ca6abc/view
- **Licence:** Singapore Open Data Licence (© Housing & Development Board)
- **File:** `hdb-resale-prices-2017-onwards.csv` — **241,920 rows** at the 2026-10-04 pull (~22.8 MB).
- **Note:** same series as `hdb-resale-mart` and `hdb-lease-slope`; each repo keeps its own copy — no cross-repo file dependencies. Here it feeds the DuckDB `resale` table that LLM-generated SQL is judged against.
- **Fetch:** `src/download.py` (initiate → poll → signed-URL flow, browser UA required; structure-validated before the CSV is replaced).
- **`pull_manifest.json` is committed** (the only committed data file besides this note): SHA-256 of the file bytes, row count, month coverage and retrieval time. It doubles as the figure date receipt — `retrieved_at` is kept verbatim while the file bytes are unchanged, so identical inputs regenerate identical figures; changed bytes get a new receipt time.

**Last pull: 2026-10-04** (16:28 SGT) — sha256 `9835dfe6cd92a46a1302fabf3a692bf893ee5b86ec95638d10dfce61dbfbdb9a`, 23,928,760 bytes, 241,920 rows, 2017-01 → 2026-10. Re-pull any time with `python src/download.py --force`.
