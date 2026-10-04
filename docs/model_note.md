# Model note — generation configuration (pinned, as-of)

**Status at 2026-10-04: no as-of receipt has been produced yet — generation is blocked on network access to the pinned provider.** Nothing in this repo claims model results that were not actually produced. This file records (1) exactly what is pinned, (2) the blocking evidence, and (3) what will be written here the moment a run lands.

## What is pinned

| Knob | Value | Where |
|---|---|---|
| Provider | **Groq free tier** (`--provider groq`, the default of [`src/generate.py`](../src/generate.py)) | `PROVIDERS["groq"]` |
| Endpoint | `https://api.groq.com/openai/v1` (OpenAI-compatible) | same |
| Model id | **discovered at run time** from `GET /models` — never guessed. Preferred `llama-3.3-70b-versatile` when listed; else the newest non-vision, non-guard llama chat model (`pick_model`) | same |
| Temperature | `0` | `TEMPERATURE` |
| Max tokens | `1024` | `PROVIDERS["groq"]["max_tokens"]` |
| Prompt | [`prompts/sql_prompt.md`](../prompts/sql_prompt.md) — question + schema block, no rows | committed |
| Retry protocol | ≤ 2 attempts per question; attempt 2 sees attempt 1's SQL + error-class feedback, never expected numbers | `src/generate.py` |
| Run date | stamped into the run's meta line (`outputs/reruns/<date>/candidates.jsonl`) and copied here at adoption | — |

Non-determinism: generation output is **not** byte-reproducible even at temperature 0 (provider-side batching). The committed `outputs/candidates.jsonl` + `outputs/results.csv` + `outputs/summary.json` are the receipt of ONE dated run; re-runs write `outputs/reruns/<date>/` and are compared, never adopted silently. Byte-reproducibility in this repo applies only to the DuckDB build, the golden fingerprints and the validation of the committed candidates.

## Why there is no receipt yet (blocking evidence, 2026-10-04)

1. **Groq is unreachable from every executable egress on this machine.** `GET https://api.groq.com/openai/v1/models` returns **HTTP 403 `{"error":{"message":"Access denied. Please check your network settings."}}`** — repeatedly (6 probes, 17:0x–17:4x SGT), with and without browser-style headers, HTTP/1.1 and HTTP/2. The host's public egress is **187.15.103.97** (a NordVPN exit — NordVPN 8.11 service processes are running on a Singapore workstation); Groq's edge rejects that client address. The unauthenticated response shape is normally `Invalid API Key`, which is what the same endpoint returns from an unblocked fetch path — so this is an egress-reputation block, not a key problem.
2. **GitHub-hosted runners are blocked too.** Actions run **37191193213** (workflow `llm-run.yml`, ubuntu-latest) failed its models probe with the same 403 (log kept at the run page).
3. **The browser route is unavailable in this session** — 6 attempts (`browser_exec`, cloud and local) all timed out at 420 s before any page context existed.
4. **A Gemini free-tier stopgap was discarded** (course correction): its quota was already exhausted (HTTP 429), and no Gemini artifacts were produced or adopted. The ~5 prompts it received during the aborted probe are disclosed in [`never_leaves_machine.md`](never_leaves_machine.md).
5. **GitHub Models is not usable from this network:** every path on `models.github.ai` (including `/inference/chat/completions` and random paths) returns a plain `OK` catch-all with HTTP 200 — no verifiable model response, so it cannot honestly produce a receipt.

## When the network allows

```bash
export GROQ_API_KEY=...           # loaded at runtime; never printed or committed
python src/generate.py            # writes outputs/reruns/<date>/candidates.jsonl
python src/validate.py --candidates outputs/reruns/<date>/candidates.jsonl --outdir outputs/reruns/<date>
```

Adoption (making a run the committed receipt) is a deliberate copy of `candidates.jsonl` to `outputs/candidates.jsonl`, then `python src/validate.py` — recorded here with the run's exact model id, listed-models snapshot, parameters and date. `.github/workflows/llm-run.yml` runs the same `src/generate.py` from a GitHub-hosted runner (needs the `GROQ_API_KEY` repo secret) for networks like this one — note the runner's egress was blocked on 2026-10-04 as well.
