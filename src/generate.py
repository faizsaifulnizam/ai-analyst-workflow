"""Generate candidate SQL for every golden question via a free-tier LLM.

Run:  python src/generate.py                 (writes outputs/reruns/<today>/candidates.jsonl)
      python src/generate.py --out <dir>     (explicit output directory)

Providers (free tier only):
  --provider groq   (default)  https://api.groq.com/openai/v1 (OpenAI-compatible), key GROQ_API_KEY
  --provider gemini            https://generativelanguage.googleapis.com/v1beta, key GOOGLE_API_KEY

Gemini exists because api.groq.com refused this build machine's VPN egress AND
GitHub-hosted runners (HTTP 403 "Access denied. Please check your network
settings.") — receipts in docs/model_note.md. The pipeline, prompt, guardrails
and comparison are provider-independent; Groq remains the default for anyone
with normal network access.

Without the provider's API key in the environment this prints how to re-run and
exits 0 — the committed candidates are re-validated offline by src/validate.py,
which is the deterministic half of the workflow. A re-run NEVER touches the
committed receipt (outputs/candidates.jsonl, outputs/results.csv,
outputs/summary.json): new runs land in outputs/reruns/<date>/ and are compared,
not adopted silently.

Model selection happens at RUNTIME against the provider's models endpoint (no
guessed model ids): a preferred free chat model is used when it is listed,
otherwise the newest stable chat model the selection rule accepts. The exact id,
the parameters and the run date are recorded in the run's meta line and in
docs/model_note.md.

What is sent to the model: the question text + the schema block from
prompts/sql_prompt.md. No rows, no key material in prompts, no files.

Retry protocol (spec 07 §4.8): at most 2 attempts per question. The second
attempt sees the first attempt's SQL plus feedback (error class and engine
message for execution problems; a bare "did not match" for wrong answers —
never the expected numbers).
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request as u
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.guardrails import execute_sql  # noqa: E402
from src.fingerprint import fingerprint, load_golden  # noqa: E402

PROMPT_TEMPLATE = (ROOT / "prompts/sql_prompt.md").read_text(encoding="utf-8")
TEMPERATURE = 0
SGT = timezone(timedelta(hours=8))

PROVIDERS = {
    "groq": {
        "base": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "max_tokens": 1024,
        "preferred": "llama-3.3-70b-versatile",   # used only if listed at run time
    },
    "gemini": {
        "base": "https://generativelanguage.googleapis.com/v1beta",
        "key_env": "GOOGLE_API_KEY",
        "max_tokens": 2048,
        "preferred": None,  # chosen by the runtime rule in pick_model()
    },
}


def http_json(url, payload=None, headers=None, timeout=120, attempts=4):
    """POST/GET JSON with exponential backoff on transient provider errors
    (429/5xx). Anything else raises immediately — a bad request is not retryable."""
    last = None
    for i in range(attempts):
        req = u.Request(url, method="POST" if payload is not None else "GET", headers=headers or {})
        if payload is not None:
            req.data = json.dumps(payload).encode("utf-8")
        try:
            with u.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except u.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or i == attempts - 1:
                raise
            last = exc
        time.sleep(2 ** i * 2)
    raise last


def list_models(provider, api_key):
    if provider == "groq":
        d = http_json(PROVIDERS["groq"]["base"] + "/models",
                      headers={"Authorization": f"Bearer {api_key}"})
        return sorted(m["id"] for m in d["data"])
    d = http_json(PROVIDERS["gemini"]["base"] + "/models",
                  headers={"x-goog-api-key": api_key})
    out = [m["name"].removeprefix("models/") for m in d.get("models", [])
           if "generateContent" in m.get("supportedGenerationMethods", [])]
    return sorted(out)


def pick_model(provider, ids):
    pref = PROVIDERS[provider]["preferred"]
    if pref and pref in ids:
        return pref
    if provider == "gemini":
        # newest stable flash chat model (no image/tts/preview/omni/robotics variants)
        cands = [i for i in ids if re.fullmatch(r"gemini-\d+\.\d+-flash", i)]
        ver = lambda i: tuple(int(x) for x in re.findall(r"\d+", i)[:2])  # noqa: E731
        return max(cands, key=ver) if cands else ids[-1]
    chat = [i for i in ids if "llama" in i and "vision" not in i and "guard" not in i]
    return chat[-1] if chat else ids[-1]


def extract_sql(text):
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        t = t.removeprefix("sql").strip()
    return t.strip()


def ask(provider, api_key, model, question, feedback=None, prior_sql=None):
    prompt = PROMPT_TEMPLATE.replace("{question}", question)
    if feedback:
        prompt += ("\n\nYour previous attempt was:\n" + prior_sql +
                   "\n\nIt did not produce the expected result (" + feedback + "). "
                   "Reread the contract (column order, ordering, rounding) and the schema, "
                   "then write a corrected single SELECT.")
    if provider == "groq":
        body = {"model": model, "temperature": TEMPERATURE,
                "max_tokens": PROVIDERS["groq"]["max_tokens"],
                "messages": [{"role": "user", "content": prompt}]}
        resp = http_json(PROVIDERS["groq"]["base"] + "/chat/completions", body,
                         headers={"Authorization": f"Bearer {api_key}",
                                  "Content-Type": "application/json"})
        return extract_sql(resp["choices"][0]["message"]["content"])
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": TEMPERATURE,
                                 "maxOutputTokens": PROVIDERS["gemini"]["max_tokens"],
                                 "thinkingConfig": {"thinkingBudget": 0}}}
    resp = http_json(f"{PROVIDERS['gemini']['base']}/models/{model}:generateContent", body,
                     headers={"x-goog-api-key": api_key, "Content-Type": "application/json"})
    parts = resp["candidates"][0]["content"]["parts"]
    return extract_sql("".join(p.get("text", "") for p in parts))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="output directory (default outputs/reruns/<today>)")
    ap.add_argument("--provider", default="groq", choices=sorted(PROVIDERS))
    ap.add_argument("--model", default=None, help="override the model id (recorded as-is)")
    args = ap.parse_args()

    cfg = PROVIDERS[args.provider]
    api_key = os.environ.get(cfg["key_env"], "").strip()
    if not api_key:
        print(f"{cfg['key_env']} is not set — generation skipped (nothing written).")
        print(f"To re-run generation:  export {cfg['key_env']}=...   then   "
              f"python src/generate.py --provider {args.provider}")
        print("The committed candidates stay authoritative; src/validate.py re-checks them offline.")
        return 0

    listed = list_models(args.provider, api_key)
    model = args.model or pick_model(args.provider, listed)
    golden = load_golden()
    out_dir = Path(args.out) if args.out else ROOT / "outputs/reruns" / datetime.now(SGT).date().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "candidates.jsonl"

    print(f"provider: {args.provider}   model: {model}   (listed models: {len(listed)})")
    print(f"questions: {len(golden['questions'])}   out: {out_path}")

    meta = {
        "meta": {
            "provider": args.provider,
            "run_date": datetime.now(SGT).date().isoformat(),
            "run_at": datetime.now(SGT).isoformat(timespec="seconds"),
            "model": model,
            "temperature": TEMPERATURE,
            "max_tokens": cfg["max_tokens"],
            "thinking_budget": 0 if args.provider == "gemini" else None,
            "prompt": "prompts/sql_prompt.md",
            "golden_set_version": golden.get("version"),
            "listed_models": listed,
        }
    }
    if not out_path.exists():
        with out_path.open("w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(meta) + "\n")

    want = {q["id"]: (q.get("fingerprint") or {}) for q in golden["questions"]}

    def passes(qid, res):
        if res["outcome"] != "ok":
            return False
        n, h = fingerprint(res["rows"])
        w = want[qid]
        return w.get("rows") == n and w.get("sha256") == h

    records = []
    if out_path.exists():          # resume: keep whatever a previous run already wrote
        with out_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    if "meta" not in rec:
                        records.append(rec)
    done = {r["id"] for r in records}
    if done:
        print(f"resuming: {len(done)} questions already generated")

    for i, q in enumerate(golden["questions"], 1):
        if q["id"] in done:
            continue
        attempts = []
        sql = ask(args.provider, api_key, model, q["question"])
        res = execute_sql(sql)
        ok = passes(q["id"], res)
        fp = fingerprint(res["rows"]) if res["outcome"] == "ok" else None
        attempts.append({"n": 1, "sql": sql, "outcome": res["outcome"],
                         "note": res.get("note", ""), "fingerprint": fp})
        if not ok:
            if res["outcome"] == "ok":
                fb = ("the query executed but its result does not match the verified answer "
                      "(check column order, grouping keys and the exact filters)")
            else:
                fb = f"{res['outcome']}: {res.get('note', '')}"
            sql2 = ask(args.provider, api_key, model, q["question"], feedback=fb, prior_sql=sql)
            res2 = execute_sql(sql2)
            fp2 = fingerprint(res2["rows"]) if res2["outcome"] == "ok" else None
            attempts.append({"n": 2, "sql": sql2, "outcome": res2["outcome"],
                             "note": res2.get("note", ""), "fingerprint": fp2})
        records.append({"id": q["id"], "question": q["question"], "attempts": attempts})
        with out_path.open("a", encoding="utf-8", newline="\n") as f:   # incremental: a crash keeps progress
            f.write(json.dumps(records[-1]) + "\n")
        print(f"  [{i:2d}/{len(golden['questions'])}] {q['id']}  attempt1={attempts[0]['outcome']}"
              + (f" attempt2={attempts[1]['outcome']}" if len(attempts) > 1 else ""))
        time.sleep(0.5)

    print(f"{len(records)} candidate records in {out_path} (meta + {len(records)} questions)")
    print("next: python src/validate.py --candidates", out_path.as_posix(), "--outdir", out_dir.as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
