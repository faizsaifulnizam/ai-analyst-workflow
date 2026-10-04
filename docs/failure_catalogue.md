# Failure catalogue — every failure in the as-of run, classified

**Run:** 2026-10-04 (receipt: [`outputs/results.csv`](../outputs/results.csv), [`outputs/summary.json`](../outputs/summary.json); config in [model_note.md](model_note.md)).
**Result:** 27/32 first-try, **0 of 5 retries rescued anything**, 5 failures. **All 5 failures are `value_mismatch`** — the row counts were right and the values were wrong. No `sql_error`, no `guardrail_reject`, no `timeout`: every candidate was a well-formed single SELECT that the guardrails let through. That is itself a finding: on this question set the failure mode is *semantics*, not syntax or safety.

Retries were offered to exactly the 5 failing questions (Q13, Q14, Q15, Q17, Q24). The retry feedback carries the error class and "did not match the verified answer" but never expected numbers — and on these five it changed nothing material (same fingerprint on both attempts for Q13/Q14/Q15/Q17; a different-but-still-wrong reading on Q24).

## Classification

| Class | n | Questions | What it looks like here |
|---|---|---|---|
| **Join/grouping slip** (grouping by a non-unique column) | 1 | Q13 *(trap)* | `COUNT(DISTINCT block)` when `block` is not unique across streets |
| **Window misuse** (row frame over a calendar series) | 1 | Q15 *(trap)* | `ROWS BETWEEN 2 PRECEDING` on a series with month gaps |
| **Contract slip — rounding order** | 1 | Q14 | rounds the medians first, then differences; the contract differences first, then rounds |
| **Contract slip — column type of a label** | 1 | Q17 | returns the year as INTEGER where the golden contract returns it as text |
| **Ambiguous question** (deliberate) | 1 | Q24 *(trap)* | "gone up in the last year" read as mean-change over the last two data years |

## The five failures, one by one

### Q13 — grouping slip on a non-unique column *(trap caught)*
**Question:** *How many distinct blocks were transacted in Bukit Merah in 2023?*
**Both attempts:** `SELECT COUNT(DISTINCT block) ... WHERE town = 'BUKIT MERAH'` → **196**. Verified answer: **295** (distinct `street_name || '|' || block`).
The trap is real and live: `block` is block-number text only, and the same string occurs in many towns/streets (9,755 distinct block strings vs 2,785 physical block identities per the data audit). The prompt's schema block says so in as many words ("NOT unique: the same string occurs in many towns/streets") — the model read it and still grouped on the wrong grain. The retry only swapped the date filter (`month` → `sale_date`), repeating the same mistake: the feedback "did not match" did not point at the grain.
**Next-iteration fix:** make the grain part of the question contract ("distinct block = distinct street + block pairs") rather than a schema hint; or add a lint that flags `COUNT(DISTINCT block)`/`GROUP BY block` for review.

### Q15 — window misuse: row frames over a gapped calendar *(trap caught)*
**Question:** *Hougang 2-room: the 3-month rolling median of monthly median price per m², 2022–2024 — each month covers that month and the two calendar months before it.*
**Both attempts:** `MEDIAN(...) OVER (ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)` → wrong values for every month after a gap. Verified answer uses `RANGE BETWEEN INTERVAL 2 MONTH PRECEDING AND CURRENT ROW`.
Hougang 2-room trades in only 22 of the 36 months — a row frame silently averages over whatever rows exist, not calendar months. The question text even spells the calendar semantics ("the two calendar months before it"), and the retry kept the row frame verbatim.
**Next-iteration fix:** put the frame choice in the prompt contract ("rolling windows over `month` are calendar months — use `RANGE ... INTERVAL n MONTH`"), and prefer questions that name the window semantics, since that is where this model actually loses.

### Q14 — contract slip: rounding order on a difference
**Question:** *For each month of 2023: island-wide median price per m² (2 dp) and its change from the previous month (2 dp).*
**Both attempts:** round each median to 2 dp **first**, then difference (or difference the rounded lag). The golden contract differences the **unrounded** medians and rounds the result once.
Both readings satisfy the sentence; only one is in the contract. The values differ in the last displayed decimal on some months, so the fingerprint (correctly) rejects.
**Next-iteration fix:** this is a question bug before it is a model bug — spell the order ("round the change, not the inputs") in the golden question. Same for every derived-difference question in the set.

### Q17 — contract slip: the year label's type
**Question:** *Per complete year 2017–2025: island-wide median price per m² (2 dp) and its year-on-year change (2 dp).*
**Both attempts:** return `year` as an INTEGER (`2017`), the golden contract returns the year as text (`'2017'`). The canonical serializer renders numbers at 2 dp — `2017.00` vs `2017` — so an otherwise correct answer fingerprints differently. Row count (9) matched.
This is the sharpest lesson in the run: **the fingerprint is type-sensitive through the serializer, and "return the columns the question names" does not specify a type**. The model's answer is arguably the more natural one.
**Next-iteration fix:** either name the type in the question ("year as `YYYY` text") or make the serializer's contract explicit in the prompt ("label columns are returned as text"). Recorded here rather than silently normalized — the golden set pins one reading and the mismatch is real.

### Q24 — ambiguous question *(trap by design)*
**Question:** *How much have HDB resale prices gone up in the last year?*
**Both attempts:** the model anchored "last year" on `CURRENT_DATE`/`MAX(sale_date)` and computed a **mean** price change across the last two data years. The golden pins: **median** resale price, 2025 minus 2024 (the last two complete years in the snapshot) — `S$` change in level.
Deliberately ambiguous wording, deliberately plausible wrong answers. The question's `why` line in `eval/golden_set.yaml` documents the pinned reading; a mismatch here is partly the question's fault and the README says so.
**Next-iteration fix:** replace with one of the two unambiguous versions ("median price change, 2024→2025") and keep Q24 as a labelled ambiguity probe — its value is measuring whether the workflow *surfaces* ambiguity, not whether the model guesses the pinned reading.

## What did not fail

- **The traps half-held:** 3 of 6 traps passed first try (Q04 near-miss column `flat_model='2-room'` vs `flat_type='2 ROOM'`; Q12 block grain *with* the town/street dimensions; Q26 remaining-lease **years** from the parsed column, not the lease text months). The other 3 (Q13, Q15, Q24) are the failures above — a 50% trap catch rate is the honest headline for "would this model fool an unverified pipeline?".
- **Syntax and safety:** zero `sql_error`, zero `guardrail_reject`, zero `timeout`. The guardrails' self-check still rejects the obvious escapes (`python src/guardrails.py`), but this run gave them nothing to reject — that is a statement about this question set, not a claim that the guardrails are unnecessary.
- **Type coverage:** filters 4/4, aggregation 5/5, ratio 4/4, distinct 2/2, date 3/3, grouping 7/8, window 2/5, ambiguous 0/1. Windows and ambiguity are where the model loses; every simple class is clean.

## Aggregate mismatch counts (from the receipt)

`value_mismatch: 5` — and nothing else. Row counts matched on all 32 first attempts: the model always got the *shape* of the answer right; when it was wrong it was wrong in the values, which is exactly the failure class that eyeballing SQL review misses and result fingerprints catch.
