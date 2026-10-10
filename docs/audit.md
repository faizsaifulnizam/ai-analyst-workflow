# Manual audit — do the verdicts survive independent recomputation?

**Historical evidence limit:** the original `audit_recompute.py` is not available in the supplied repository or review bundle. The following is a historical reported receipt, not an authenticated recovered script or independently certified historical process. A newly run independent calculation is new evidence; it does not recover the old method or authorship. Exact source SHA-256: `9835dfe6cd92a46a1302fabf3a692bf893ee5b86ec95638d10dfce61dbfbdb9a` (241,920 rows).

**Method.** Every number below was recomputed from the raw CSV
(`data/raw/hdb-resale-prices-2017-onwards.csv`, 241,920 rows) with **stdlib `csv` + `Decimal` only** — no DuckDB, no `src/` code, no pipeline helpers. The audit script re-derives each answer from the raw rows (`audit_recompute.py`, kept out of the repo on purpose: the audit must not be another consumer of the pipeline it checks), then re-implements the documented fingerprint contract independently (numbers → fixed 2dp, cells joined with `0x1f`, rows with `0x1e`, sha256) and compares the resulting hash with `eval/golden_set.yaml`. A `MATCH` therefore covers both the golden SQL's answer **and** the serializer contract; the verdict column then checks the run's recorded outcome against that answer.

Fifteen questions were audited (the bar was ≥10), deliberately mixing question types and including both deliberate traps (Q04, Q13) and questions where the run passed and failed.

## The recomputation (raw CSV → answer, independent of the pipeline)

| Q | What was recomputed (from raw columns only) | Independent answer | Golden fingerprint | Cross-check |
|---|---|---|---|---|
| Q01 | count rows `town='TAMPINES'`, `month` in 2023 | **1,634** | 1 row | **MATCH** (sha `125c1f49…`) |
| Q02 | count `town='BEDOK'`, `flat_type='5 ROOM'`, `month` 2024-01…2024-06 | **125** | 1 row | **MATCH** (`20fd6820…`) |
| Q03 | count 2023 rows with `floor_area_sqm ≥ 110` **and** storey parsed from the raw `storey_range` text (`'13 TO 15' → 13`) ≥ 13 | **1,545** | 1 row | **MATCH** (`2d1a29d4…`) |
| Q04 *(trap)* | count `flat_type='2 ROOM'` in 2023 | **688** | 1 row | **MATCH** (`eb3bb117…`) |
| Q04 trap contrast | the near-miss the trap targets: `flat_model` text `'2-room'` in 2023 | 35 (≠ 688) | — | trap confirmed real |
| Q05 | median `resale_price` of `flat_type='4 ROOM'` 2023 (median = average of the two middle values), rounded to whole dollars | **S$550,000** | 1 row | **MATCH** (`560a1899…`) |
| Q06 | mean `floor_area_sqm` of `EXECUTIVE` 2023, 1 dp | **145.4 m²** | 1 row | **MATCH** (`dc29842a…`) |
| Q07 | 100 × (4 ROOM 2023 count) ÷ (all 2023 count), 2 dp | **44.10 %** (11,357 / 25,754) | 1 row | **MATCH** (`5adff50c…`) |
| Q08 | 2023 counts per `flat_type`, ordered count desc then name asc | 4 ROOM **11,357** · 3 ROOM **6,355** · 5 ROOM **5,842** · EXECUTIVE **1,503** · 2 ROOM **688** · 1 ROOM **6** · MULTI-GENERATION **3** | 7 rows | **MATCH** (`5ae67a84…`) |
| Q13 *(trap)* | distinct `street_name`+`block` pairs in `BUKIT MERAH` 2023 | **295** | 1 row | **MATCH** (`228e8d33…`) |
| Q13 trap contrast | the wrong grouping key the trap targets: distinct `block` strings alone | 196 (≠ 295) | — | trap confirmed real |
| Q20 | distinct `flat_model` in `TAMPINES` 2023 | **9** | 1 row | **MATCH** (`4cc019de…`) |
| Q22 | busiest `month` in 2020, ties → earliest | **2020-12**, **2,486** transactions | 1 row | **MATCH** (`ca3a3598…`) |
| Q25 | mean `resale_price` where `block='27'` in 2023, 2 dp | **S$484,502.70** | 1 row | **MATCH** (`fe8afa8a…`) |
| Q27 | 2023 months whose count exceeds that year's average month (2,146.17) | **6** months | 1 row | **MATCH** (`017144e2…`) |
| Q28 | highest `resale_price` in 2023, ties → earliest month | **2023-06**, **S$1,500,000** | 1 row | **MATCH** (`ff1269dd…`) |
| Q32 | count rows `month` 2023-01…2023-03 | **6,665** | 1 row | **MATCH** (`a74653f0…`) |

All 15 independent fingerprints reproduce the committed golden fingerprints exactly — **0 discrepancies**. The two trap contrasts (Q04: 688 vs 35; Q13: 295 vs 196) confirm the traps are live failure opportunities, not decoration.

## Verdict check against the run (as-of receipt)

Each audited question's recorded verdict in `outputs/results.csv` is checked against the independently verified answer: a `pass` verdict is accepted only because the candidate's executed result carries the same fingerprint the independent recomputation above just re-derived from raw rows; the `fail` verdicts are inspected to confirm the mismatch lives in the candidate SQL (or the question's contract), not in the golden answer.

| Q | Run verdict | Independent answer stands | Note |
|---|---|---|---|
| Q01 | **pass first try** | 1,634 | candidate fingerprint == independently re-derived fingerprint |
| Q02 | **pass first try** | 125 | same |
| Q03 | **pass first try** | 1,545 | same |
| Q04 *(trap)* | **pass first try** | 688 (not 35) | trap avoided — model used `flat_type`, not the `flat_model` near-miss |
| Q05 | **pass first try** | 550,000 | same |
| Q06 | **pass first try** | 145.4 | same |
| Q07 | **pass first try** | 44.10 % | same |
| Q08 | **pass first try** | 7-row breakdown | order contract (count desc, name asc) verified against my sorted recomputation |
| Q13 *(trap)* | **fail** (both attempts) | 295 (not 196) | golden answer stands; candidate grouped on non-unique `block` → 196 — the failure is in the candidate SQL |
| Q20 | **pass first try** | 9 | same |
| Q22 | **pass first try** | 2020-12 / 2,486 | tie-break contract (earliest month) verified |
| Q25 | **pass first try** | 484,502.70 | same |
| Q27 | **pass first try** | 6 | same |
| Q28 | **pass first try** | 2023-06 / 1,500,000 | tie-break contract verified |
| Q32 | **pass first try** | 6,665 | same |

14 audited passes and 1 audited failure (Q13) — 15 verdicts, mix of pass and fail as required. Q15's failure-side check is covered in [failure_catalogue.md](failure_catalogue.md), not recomputed in the table above. In both failure-side checks (Q13 here; Q15's window frame in the catalogue) the independently recomputed golden answer is the one that stands.

## Discrepancy log

- **Golden answers vs raw CSV: 0 discrepancies** (15/15 fingerprints re-derived independently, 2026-10-04).
- **Run verdicts vs independent answers: 0 discrepancies** — every audited `pass` reproduces the independently derived fingerprint, and every audited `fail` is explained by the candidate SQL, not the golden answer.
- Two *contract* ambiguities found while auditing (not discrepancies — recorded because they are real reading risks): Q14's rounding order ("round the change, not the inputs" is not spelled in the question) and Q17's year-label type (text vs integer fingerprints differently through the 2dp serializer). Both are logged in [failure_catalogue.md](failure_catalogue.md) with next-iteration fixes.

## What this audit does not establish

- It re-derives the *golden* answers and the serializer contract from raw rows; it does not re-audit the downloader or the DuckDB build (that is [data_audit.md](data_audit.md)'s job) and it does not re-run the model.
- Passing the fingerprint is a *consistency* claim against a hand-written canonical SQL — the canonical SQL itself encodes one reading of each question (documented in `eval/golden_set.yaml`'s `why` lines). For deliberately ambiguous questions (Q24) the pinned reading is a choice, not ground truth.
- The audit covers 15 of 32 questions; un-audited questions are only as trustworthy as the golden set's own review.
