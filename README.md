# ai-analyst-workflow

**Can an LLM write correct SQL for a real analyst question — and how would I know when to trust it?**

A small, verifiable LLM-assisted analytics workflow over Singapore public data: generate candidate SQL → execute it against a real DuckDB database → compare against a hand-written golden set → catalogue every failure. Built to show **validation discipline**, not model magic.

**Status:** built 2026-10-04 to the generation boundary — data pipeline, DuckDB build (241,920 rows, 9/9 checks), the hand-written golden set (32 questions, 6 deliberate traps, verified fingerprints), parse-based execution guardrails and the generate/validate code are complete and pushed. **The LLM eval receipt is not produced yet:** the pinned free-tier provider (Groq) refuses every executable egress from the build machine and from GitHub-hosted runners (HTTP 403) — no substitute provider was used and no results are claimed. See [docs/model_note.md](docs/model_note.md) for the pinned configuration and the blocking receipts, and [docs/never_leaves_machine.md](docs/never_leaves_machine.md) for what would (and would not) leave the machine.

## The question

Entry-level analytics job specs in 2026 expect AI tool fluency *plus* the habit of verifying AI output. This repo answers both with one artifact: a workflow where the LLM does real work, and the pipeline shows exactly where it can and cannot be trusted.

## The data

- HDB resale flat prices, Jan 2017 → latest (data.gov.sg `d_8b84c4ee58e3cfc0ece0d773c8ca6abc`, © Housing & Development Board, Singapore Open Data Licence) — the same series used by `hdb-resale-mart`.
- Turned into a single local DuckDB table (`resale`, ~241K rows). Raw files stay out of git.

## Method (planned)

1. **Golden set** — 30+ analyst-phrased questions, each with canonical SQL + a result fingerprint (row count + checksum).
2. **Generate** — one prompt template, free-tier LLM; candidate SQL executed under guardrails (SELECT-only, statement timeout, read-only).
3. **Validate** — candidate result vs golden fingerprint → pass/fail per question → `outputs/results.csv`.
4. **Catalogue failures** — ambiguous questions, schema confusion, join/grouping slips, window misuse, hallucinated columns — with examples.
5. **Audit by hand** — a sample of verdicts checked manually against the raw data; discrepancies logged.

## What you'll find here (at build)

- The standard: pass rate first-try vs after one retry, as of a pinned model + date.
- The honest part: a failure catalogue — what broke, why, and what I'd fix next.
- The governance note: what data was sent, what never leaves the machine.

## Limits (by design)

- One table, one workflow — a validation demo, not an agent framework or a benchmark.
- Non-deterministic by nature: numbers are "as of" a dated run; everything else is pinned.
- No fine-tuning, no model-quality claims — the generation is the LLM's; the judgment is mine.

## Repo layout

`src/` generator + validator · `eval/` golden set · `prompts/` prompt templates · `sql/` DB build · `docs/` catalogue, audit, governance · `outputs/` results.
