# What never leaves the machine — governance note

The repo's question is about *trust*; this file is about *data*. Short version: **no row data is ever sent to a model. Only question text and a schema block leave the machine; everything else — the 241,920 raw rows, the DuckDB file, the fingerprints — stays local.**

## What is sent to the model provider

Per question, exactly two things (see [`prompts/sql_prompt.md`](../prompts/sql_prompt.md)):

1. the analyst question text (written by hand in [`eval/golden_set.yaml`](../eval/golden_set.yaml));
2. the schema block: table + column names and one-line semantics (the same DDL that is committed in [`sql/00_build_db.sql`](../sql/00_build_db.sql)).

On the retry attempt, additionally: the model's own previous SQL and an error class (`sql_error`, `guardrail_reject`, `timeout`) with the engine message, or a bare "did not match the verified answer". **Expected answers, golden fingerprints, row counts and result values are never included in any prompt.**

## What is never sent

- No rows, aggregates, samples or file bytes from the dataset.
- No API keys in prompts, logs, commits or outputs (keys are read from the local environment at runtime; `grep`-level key-material checks run before every push).
- No personal data — the dataset is public resale transactions (no buyer/seller identities exist in it).

## Guardrails on every candidate before execution

[`src/guardrails.py`](../src/guardrails.py) — all of these, before a single row is fetched:

1. **Parse-based single-SELECT check** (sqlglot, DuckDB dialect): exactly one statement, top level SELECT; a `startswith('select')` check is deliberately not used.
2. **Blocked anywhere in the statement:** DDL/DML, `ATTACH`/`COPY`/`PRAGMA`/`SET` and every other command type; any table other than `resale` (or a CTE defined in the statement); table functions that touch the filesystem or catalog (`read_csv*`, `read_parquet`, `glob`, `pragma_*`, `*_scan`, …).
3. **Read-only** DuckDB connection to the built database.
4. **Wall-clock watchdog** (DuckDB has no statement timeout): `con.interrupt()` after 15 s → attempt classified `timeout`.
5. **Row cap 10,000** — exceeding it is a guardrail reject, not an answer.

The guardrails have a runnable self-check (`python src/guardrails.py`) that asserts the obvious escapes are rejected.

## What a stricter setting would change

| Stricter step | What it buys | What it costs |
|---|---|---|
| Per-question schema views (columns named in the question only) | less schema exposure per call | more plumbing; marginal — schema is not sensitive here |
| Offline replay only (run nothing against a provider; validate the committed candidates) | zero egress | no new runs; the receipt stays frozen |
| Self-hosted model (e.g. a local GGUF) | nothing leaves the machine at all | noticeably weaker SQL; the honest comparison point changes |
| No retry feedback | less signal in prompts | lower pass rate; feedback already excludes expected values |
| Corporate proxy / egress allowlist in front of the provider | one audited exit | operational setup |

## Disclosure log

- **2026-10-04:** during a discarded stopgap attempt, ~5 prompts (Q01–Q04 plus one retry-free question start) were sent to **Google's Gemini API** (`gemini-3.8-flash`, thinking disabled) from this machine. The provider was then ruled out by course correction; its free quota was already exhausted (HTTP 429); **no Gemini output was adopted** — `outputs/reruns/2026-10-04/` was left empty and the partial run never reached a written file. Payload per prompt: question + schema only, per the contract above.
- **2026-10-04:** Groq probes (`GET /models`) carried the API key in the `Authorization` header to `api.groq.com` only; all were rejected at the network edge (403) before any application processing.
- **GitHub Actions route (`.github/workflows/llm-run.yml`):** if used, question + schema travel to Groq **from a GitHub-hosted runner**, and the key is read from the repo's encrypted Actions secret `GROQ_API_KEY` (currently set; remove with `gh secret remove GROQ_API_KEY` if the cloud route is not wanted). No run of it has produced any output: its probe failed at the same 403.
