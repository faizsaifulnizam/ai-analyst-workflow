# Model note — generation configuration (pinned, as-of)

**As-of receipt: 2026-10-04 — Gemini free tier, three sibling model ids: `gemini-3.7-flash` (Q01–Q08) · `gemini-3.5-flash` (Q09–Q21) · `gemini-3.1-flash-lite` (Q22–Q32).** The committed [`outputs/candidates.jsonl`](../outputs/candidates.jsonl) + [`outputs/results.csv`](../outputs/results.csv) + [`outputs/summary.json`](../outputs/summary.json) are the receipt of ONE dated run (per-question model id is recorded in `candidates.jsonl` and surfaced as `receipt.models_used`). Nothing else in this repo claims model results that were not produced by that run. **Why three ids:** the free tier caps `generate_content_free_tier_requests` at **20 requests/day per model per project** (`quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier`); a 32-question run with retries needs ~40 requests, so the run was resumed per question across sibling model buckets as each was exhausted. The pinned id remains `gemini-3.7-flash`; a single-model re-run is one command once its daily quota resets (see Re-running).

## What is pinned

| Knob | Value | Where |
|---|---|---|
| Provider | **Gemini free tier** (Google Generative Language API), `--provider gemini` (the default of [`src/generate.py`](../src/generate.py)) | `PROVIDERS["gemini"]` |
| Endpoint | `https://generativelanguage.googleapis.com/v1beta` (`:generateContent`) | same |
| Model id | **`gemini-3.7-flash`** — pinned as `preferred`, confirmed listed by the endpoint at run time (runtime model discovery; ids are never guessed), passed explicitly as `--model gemini-3.7-flash`. The as-of receipt additionally carries per-question runs on `gemini-3.5-flash` and `gemini-3.1-flash-lite` (quota wall above; `receipt.models_used` lists all three) | `PROVIDERS["gemini"]["preferred"]` |
| Temperature | `0` | `TEMPERATURE` |
| Max output tokens | `2048` (thinking budget `0` — hidden thinking would consume the budget) | `PROVIDERS["gemini"]["max_tokens"]` |
| Prompt | [`prompts/sql_prompt.md`](../prompts/sql_prompt.md) — question text + schema block only, no rows | committed |
| Retry protocol | ≤ 2 attempts per question; attempt 2 sees attempt 1's SQL + error-class feedback, never expected numbers | `src/generate.py` |
| HTTP retry policy | bounded: 6 attempts on 429/500/502/503/504 (covers Gemini's 503 "high demand"), `Retry-After` honoured when sent, else 20s × 2^i capped at 120s; 4s pacing between provider calls | `http_json` / `PACE_S` |
| Resume | per question — records append as they go; a provider outage keeps progress, re-run the same command to continue | `src/generate.py` |
| Run date | **2026-10-04** (Asia/Singapore), stamped in the run's meta line and in `outputs/summary.json` → `receipt.run_date` | `outputs/candidates.jsonl` line 1 |

Non-determinism: generation output is **not** byte-reproducible even at temperature 0 (provider-side batching). The committed outputs are the receipt of ONE dated run; re-runs write `outputs/reruns/<date>/` and are compared, never adopted silently. Byte-reproducibility in this repo applies only to the DuckDB build, the golden fingerprints, and the validation of the committed candidates (re-running `src/validate.py` over the committed candidates is byte-identical).

## Why this provider (network notes, 2026-10-04)

The free-tier route was chosen by elimination — every other executable route was probed and failed:

1. **Groq: HTTP 403 egress-reputation block.** `GET https://api.groq.com/openai/v1/models` returns `{"error":{"message":"Access denied. Please check your network settings."}}` — repeatedly, with and without browser-style headers — from this machine's VPN egress (a VPN egress IP) **and** from GitHub-hosted runners (a GitHub Actions run, same 403). The unauthenticated response shape from an unblocked path is `Invalid API Key`, so the key is fine and the edge rejects the client address. Not circumvented (no VPN change, no proxy laundering).
2. **OpenCode Free: client-policy block.** `403 FreeTierError: free tier can only be used from within OpenCode` — a product policy, not a network fault. Not circumvented.
3. **Gemini, morning of 2026-10-04: HTTP 429 quota exhausted.** Recovered the same day; the as-of run landed that evening. A discarded stopgap attempt before the recovery sent ~5 prompts (see [`never_leaves_machine.md`](never_leaves_machine.md)); none of its output was adopted.
4. **Gemini `gemini-3.8-flash`: HTTP 503 "high demand"** on every call — not used. **`gemini-2.0-flash` is retired** (no longer served).
5. **GitHub Models (`models.github.ai`) is unverifiable from here:** every path returns a plain `OK` HTTP 200 catch-all — no model response, so it cannot honestly produce a receipt.

No paid route was used. The pipeline, prompt, guardrails and comparison are provider-independent — `--provider groq` stays selectable for anyone with normal network access.

## Re-running (this never touches the committed receipt)

```bash
export GOOGLE_API_KEY=...           # loaded at runtime; never printed or committed
python src/generate.py              # writes outputs/reruns/<date>/candidates.jsonl (resumable)
python src/validate.py --candidates outputs/reruns/<date>/candidates.jsonl --outdir outputs/reruns/<date>
```

Your re-run will differ — that is expected for generation. Compare the two `summary.json` files. Adoption of a new run as the committed receipt is a deliberate copy of its `candidates.jsonl` to `outputs/candidates.jsonl` followed by `python src/validate.py`, recorded here with the new model id and run date. `.github/workflows/llm-run.yml` (manual dispatch) runs the same `src/generate.py` from a GitHub-hosted runner against the pinned model id; it needs the repo secret `GOOGLE_API_KEY`.
