# Data audit — the `resale` table (as built 2026-10-04)

**Input:** `data/raw/hdb-resale-prices-2017-onwards.csv` — data.gov.sg `d_8b84c4ee58e3cfc0ece0d773c8ca6abc` (© Housing & Development Board, Singapore Open Data Licence). Pull receipt: [`pull_manifest.json`](../data/raw/pull_manifest.json) — sha256 `9835dfe6…db9a`, 23,928,760 bytes, 241,920 rows, 2017-01 → 2026-10.

## Profile (computed from the built table)

| Property | Value |
|---|---|
| Rows | **241,920** (raw == staged; see exclusions below) |
| Months | 118 distinct (2017-01 → 2026-10) |
| Towns | 26 |
| Flat types | 7 (`1 ROOM` 88 · `2 ROOM` 5,092 · `3 ROOM` 57,407 · `4 ROOM` 102,833 · `5 ROOM` 59,179 · `EXECUTIVE` 17,231 · `MULTI-GENERATION` 90) |
| Resale price | S$140,000 – S$1,728,000 (median S$505,000) |
| Floor area | 31.0 – 366.7 m² |
| Remaining lease (parsed) | 39.33 – 97.75 years |
| Nulls in key columns (town, flat_type, resale_price, lease parse) | 0 |
| Exact duplicate rows (all 11 fields) | 318 — kept, not excluded: identical attributes are legitimate for repeated registrations of the same flat type/unit profile; they are distinct transactions |
| 2026-10 rows | 212 — a **partial month** (registrations to the pull date); every golden question bounds its period, and 2026-10 is never treated as a complete month |

## Cleaning rules (mirrored from `hdb-resale-mart` staging)

Applied in [`sql/00_build_db.sql`](../sql/00_build_db.sql), counted and reconciled in [`src/build_db.py`](../src/build_db.py) (retained + excluded must equal raw):

| Rule | Excluded rows |
|---|---|
| price null or ≤ 0 | 0 |
| area null or ≤ 0 | 0 |
| unparseable `month` | 0 |
| missing `remaining_lease` text | 0 |
| **Total excluded** | **0 of 241,920** |

Structural checks (all 0 violations, run before the database file is promoted): price > 0 · area > 0 · sale_month in range · month text matches sale_month · town/flat_type non-null · price/m² sane · storey band sane · lease years sane.

Derived columns: `sale_date`/`sale_month` (parsed month), `storey_low`/`storey_high`/`storey_mid` (parsed from `storey_range`), `remaining_lease_years` (years + months/12 from the lease text), `price_per_sqm`. Raw text columns are kept alongside — the near-miss pairs are deliberate eval material.

## Trap-relevant facts (verified against the build)

These are why the golden set's traps are real, not decorative:

1. **`block` is not a unique block identifier.** 2,785 distinct `block` strings vs **9,755** distinct (town, street, block) combinations. Block `'101'` occurs in **20 towns** (596 rows); even inside one town the same block number can sit on several streets (Bukit Merah block `'28'` on **5** streets). Grouping by `block` alone silently merges unrelated blocks — Q12/Q13 test exactly this (block-only top in 2023: `'9'` with 71 rows; physical-block top: Bukit Batok / BT BATOK ST 21 / 293D with 41).
2. **`flat_model` is not `flat_type`.** `flat_model = '2-room'` has 516 rows island-wide (35 in 2023) inside `flat_type = '2 ROOM`' (5,092 total; 688 in 2023). `'Maisonette'` is a flat_model under `EXECUTIVE`, while `'Model A-Maisonette'` sits under `5 ROOM`. Q04 tests the near-miss.
3. **Sparse series break row-based windows.** Hougang `2 ROOM` trades in only **22 of 36** months in 2022–2024; a `ROWS 2 PRECEDING` rolling median differs from the calendar (`RANGE … INTERVAL 2 MONTH PRECEDING`) answer in **5 months when both inputs are prefiltered to 2022–2024**. The actual Q15 SQL compares six output months because the candidate window retains earlier history before filtering output, while the golden reference filters before windowing: 2022-04, 2022-09, 2023-01, 2023-03, 2023-05 and 2023-09. This combines a frame choice and a window-population boundary, not an every-after-gap rule. Q15 tests this.
4. **`remaining_lease` is text** — 222,076 rows carry a months component (`'61 years 04 months'`). Parsing years only understates the average (4-room 2019: 77.4 vs **77.9** years). Q26 tests this.

## Data-quality notes (no exclusions, documented only)

- **Partial latest month:** 212 rows for 2026-10 at the pull date. Never compared against complete months.
- **Duplicates:** 318 exact duplicate rows retained (see table above).
- **Source is registration-date based:** a resale agreed earlier can register late; month comparisons are registration months.
- The raw file is immutable (gitignored); all cleaning is code and every exclusion is counted.

*Recompute: `python src/build_db.py` prints the counts and check results; `python src/fingerprint.py` re-verifies every golden fingerprint against this build.*
