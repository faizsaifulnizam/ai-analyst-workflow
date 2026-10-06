# Decision memo — ai-analyst-workflow

**Recommendation: propose a supervised feasibility pilot, not adoption or production use.** Start with recurring single-table tasks whose answers can be checked independently. The analyst owns the question and the validated answer, so model output cannot trigger unattended external reporting or business decisions.

## Evidence behind the recommendation

The 2026-10-04 receipt records 27/32 first-try passes, no retry rescues and five value-level wrong answers despite correct row counts. Comparing candidate results with known gold references caught those five errors. **This does not prove correctness checking for new questions without gold answers.** A fingerprint checks agreement with a reference, not whether that reference answers the right business question. The golden set's reading of an ambiguous question is a pinned choice, so clarify the intended reading before generating SQL.

This was a small, selected set on one HDB table using three free-tier Gemini model ids. It is a workflow receipt, not a generalizable accuracy estimate or model ranking. Neither time savings nor deployment readiness was measured. The parse-based SELECT-only boundary, read-only execution, watchdog and row cap reduce execution risk, but they do not establish answer correctness.

## Proposed pilot scope and checks

1. **Choose tasks with an independent check.** Start with recurring single-table counts, totals or grouped summaries where a separately maintained report or analyst calculation can supply a reference. Confirm grain, dates, filters, units, rounding and output types before SQL. Keep joins, changing schemas and unresolved ambiguous questions out of the initial scope.
2. **Keep verification separate from generation.** An analyst reviews the SQL and result against the agreed question and independent reference. Without a reliable reference oracle, manually verify from source data before using the answer. Do not treat another model's agreement, a plausible query or the right row count as proof. Hold tasks where reliable independent verification cannot be supplied.
3. **Clear data use first.** Review privacy requirements and provider terms before any private data, schema or prompt is sent. The public-data run does not authorize private-data use. Keep execution read-only and require analyst approval before an answer enters a report or decision.

## What to measure

Compare manual and assisted work on comparable tasks and the same input snapshot. Record **time to a validated answer**, including clarification, SQL work, verification and corrections. Also record setup, reference creation and maintenance, and reviewer effort so shared costs are visible rather than hidden as savings. Account for task difficulty and order when comparing the two routes.

Keep held-out tasks separate from prompt or workflow tuning. After the normal reviewer signs off, independently check their answers against source data or separately established references to identify material errors that escaped review. Report corrections, rejected answers and review escapes alongside time and total effort. Replaying the existing gold set alone cannot measure how well review catches errors on new work.

## Decision gate, agreed before starting

The analyst and business owner should predefine task-specific acceptance criteria for correctness, material error consequences, verification coverage and total effort. A reporting total and an exploratory summary need different checks, so no arbitrary pass-rate or savings threshold is proposed here.

**Hold or stop the pilot if reliable independent verification is unavailable or a material error escapes review.** Investigate the cause and re-check the affected tasks before considering a restart. Continue only within the agreed scope if the evidence meets the predefined criteria. Even then, the result supports a separate adoption review, not automatic deployment or unattended use.

## What this memo cannot say

No measured savings, production-readiness claim, model ranking or conclusion about multi-table work. The existing generation receipt remains dated and unchanged. Next technical iteration: make rounding and label contracts explicit, clarify ambiguity before SQL, and test window-frame semantics. Those changes would need fresh evaluation, not a reinterpretation of the recorded five failures.
