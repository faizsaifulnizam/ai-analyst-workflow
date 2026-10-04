# Review remediation — 2026-10-04 pre-publication review

Fix log for the 2026-10-04 review of this repo. Factual only: finding → change → commit.

## Findings

| ID | Change | Commit |
|---|---|---|
| F1 | `docs/failure_catalogue.md` Q13: block-grain pair corrected to 2,785 distinct block strings vs 9,755 distinct town/street/block identities (matches `docs/data_audit.md`, README, `eval/golden_set.yaml` Q12) | `b86e9fa` |
| F2 | README Key numbers: clean-class total corrected to (18/18) | `81886eb` |
| F3 | `docs/audit.md` + README §Validation: audit sample restated as 15 verdicts = 14 passes + 1 fail (Q13), Q15's failure-side check covered in the failure catalogue | `81886eb` |
| F4 | `docs/failure_catalogue.md` retry line: Q24 reworded to "a differently-written but result-identical wrong answer" (both attempts share result fingerprint `5082289dda31…`, 1 row; only the SQL anchors differ) | `b86e9fa` |
| F5 | `src/download.py` row-count comment corrected to 241,920 rows | `a7019d2` |
| F6 | `src/guardrails.py` `check_sql`: table allowlist and CTE-reference matching fold case (DuckDB identifiers are case-insensitive); self-check gains `FROM RESALE`/`FROM Resale`/`FROM "RESALE"` accepts, a case-folded CTE reference accept, and `FROM EVIL` still rejected | `a7019d2` |
| F7 | `src/validate.py`: non-default `--candidates` without `--outdir` now defaults `--outdir` to the candidates file's parent directory, never the committed `outputs/` receipt; regression `tests/test_validate_outdir.py` | `a7019d2` |
| F8 | `docs/model_note.md`: egress IP and Actions run id genericized in the Groq-blocking evidence (substance unchanged) | `aa9ceef` |
| F9 | Series wording made self-consistent: "Six-on-SG" is the six-data-repo brand, this repo is the AI-workflow add ("six Singapore-data analyses plus this AI workflow (seven repos)") — README status + footer, both banner SVGs' `<title>` and series tag | `7fa8cb9` |
| F10 | README method step 1: `ORDER BY` qualified to "where the result has multiple rows" | `81886eb` |

Issue #2 (F6) is closed by `a7019d2` (PR body carries `Fixes #2`).

## Editorial items applied (README/figures)

| Item | Change | Commit |
|---|---|---|
| 1 | "What I built" contribution line added under the Status line | `9648cac` |
| 2 | "result fingerprint" glossed on first use as "(a hash of the actual rows returned)" | `9648cac` |
| 3 | "the honest picture is the other end" replaced with the failure-first phrasing | `9648cac` |
| 4 | Key-numbers audit phrasing: "re-derived from the raw CSV with stdlib `Decimal` — no DuckDB, no repo code" | `9648cac` |
| 7 | Glosses: "canonical result formatter (the \"serializer\")"; block-grain bullet notes grouping by `block` is the Q13 trap | `9648cac` |
| 8 | Blockquote closes with the one-line trust-for-X-not-Y statement | `9648cac` |
| 11 | "The question" opening rewritten (claims unchanged) | `9648cac` |
| 12 | f2 panel B recoloured: deliberate traps violet, everything else petrol; burnt reserved for "failed" figure-wide | `223620c` |
| 16 | Redundant full-size banner link removed; banner series tag updated with F9 | `7fa8cb9` |
| 17 | "### More views" renamed "### The failure view" | `9648cac` |

Figure re-render receipt (item 12): light `608c0682…`, dark `29d24fe9…`; f3 unchanged (`062a222a…` / `8d9990b8…`); `docs/img/` mirrors byte-identical to `reports/figures/`; in-code QA (title/footnote width, clearance, in-bounds, annotation/legend overlap) PASS; same-env double-render determinism PASS per figure in both themes.
