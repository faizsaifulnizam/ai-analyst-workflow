"""Generate candidate SQL for every golden question via a free-tier LLM.

Run:  python src/generate.py                 (writes outputs/reruns/<today>/candidates.jsonl)
      python src/generate.py --out <dir>     (explicit output directory)

Providers (free tier only):
  --provider gemini (default)  https://generativelanguage.googleapis.com/v1beta, key GOOGLE_API_KEY
  --provider groq              https://api.groq.com/openai/v1 (OpenAI-compatible), key GROQ_API_KEY

Gemini is the default because api.groq.com refused this build machine's VPN
egress AND GitHub-hosted runners (HTTP 403 "Access denied. Please check your
network settings.") — receipts in docs/model_note.md. The pipeline, prompt,
guardrails and comparison are provider-independent; groq stays selectable for
anyone with normal network access.

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
attempt sees the first attempt's SQL plus a fixed result-contract message,
never engine diagnostics, rows or expected numbers.
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
PACE_S = 4   # seconds between provider calls (free-tier burst/TPM pacing)
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
        # pinned id of the committed receipt (docs/model_note.md); used only if
        # listed at run time, else the newest stable flash the rule accepts
        "preferred": "gemini-3.7-flash",
    },
}


def http_json(url, payload=None, headers=None, timeout=120, attempts=6):
    """POST/GET JSON with bounded backoff on transient provider errors
    (429/5xx — including Gemini's 503 'high demand'). Honours Retry-After when
    the provider sends one, else 20s * 2^i capped at 120s. Anything else raises
    immediately — a bad request is not retryable."""
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
            try:
                ra = float(exc.headers.get("Retry-After", ""))
            except ValueError:
                ra = 0
            time.sleep(min(ra or 20 * (2 ** i), 120))
            continue
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


def ask(provider, api_key, model, question, feedback=None, prior_sql=None, response_evidence=None):
    prompt = PROMPT_TEMPLATE.replace("{question}", question)
    if feedback:
        # Diagnostics can contain database values. Never interpolate them into a prompt.
        feedback = "previous attempt did not satisfy the result contract"
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
        text = resp["choices"][0]["message"]["content"]
        if response_evidence is not None:
            response_evidence["response_text"] = text
        return extract_sql(text)
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": TEMPERATURE,
                                 "maxOutputTokens": PROVIDERS["gemini"]["max_tokens"],
                                 "thinkingConfig": {"thinkingBudget": 0}}}
    resp = http_json(f"{PROVIDERS['gemini']['base']}/models/{model}:generateContent", body,
                     headers={"x-goog-api-key": api_key, "Content-Type": "application/json"})
    parts = resp["candidates"][0]["content"]["parts"]
    time.sleep(PACE_S)   # pace free-tier calls; the burst/TPM limit trips without it
    text = "".join(p.get("text", "") for p in parts)
    if response_evidence is not None:
        response_evidence["response_text"] = text
    return extract_sql(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="output directory (default outputs/reruns/<today>)")
    ap.add_argument("--provider", default="gemini", choices=sorted(PROVIDERS))
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

    import hashlib
    identity = hashlib.sha256(json.dumps(golden, sort_keys=True).encode() + PROMPT_TEMPLATE.encode()).hexdigest()
    meta = {
        "meta": {
            "contract_sha256": identity,
            "serializer_version": 2,
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
    if out_path.exists():
        first = json.loads(out_path.read_text(encoding="utf-8").splitlines()[0]).get("meta", {})
        keys = ("provider", "model", "temperature", "max_tokens", "golden_set_version", "contract_sha256", "serializer_version")
        if any(first.get(k) != meta["meta"].get(k) for k in keys):
            print("resume identity mismatch — use a new output directory")
            return 2
        meta["meta"]["run_date"] = first["run_date"]
    if not out_path.exists():
        with out_path.open("w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(meta) + "\n")

    want = {}
    for q in golden["questions"]:
        reference = execute_sql(q["sql"], as_of=meta["meta"]["run_date"])
        if reference["outcome"] != "ok":
            raise RuntimeError("golden reference execution failed")
        n, h = fingerprint(reference["rows"], version=2)
        want[q["id"]] = {"rows": n, "sha256": h}

    def candidate_fingerprint(res):
        if res["outcome"] != "ok":
            return None
        try:
            return fingerprint(res["rows"], version=2)
        except (ValueError, TypeError) as exc:
            # Formatting is a local contract failure, not a transport failure.
            # Keep the complete diagnostic locally; ask() only sends fixed feedback.
            res["outcome"] = "result_contract_error"
            res["note"] = f"{type(exc).__name__}: {exc}"
            return None

    def passes(qid, res):
        if res["outcome"] != "ok":
            return False
        fp = candidate_fingerprint(res)
        if fp is None:
            return False
        n, h = fp
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
    latest = {r["id"]: r for r in records}
    # A persisted fingerprint is sufficient to recognize an already passing attempt.
    done = {qid for qid, r in latest.items()
            if len(r["attempts"]) == 2 or (r["attempts"][0]["outcome"] == "ok"
            and r["attempts"][0]["fingerprint"] == [want[qid].get("rows"), want[qid].get("sha256")])}
    if done:
        print(f"resuming: {len(done)} questions already generated")

    for i, q in enumerate(golden["questions"], 1):
        if q["id"] in done:
            continue
        attempts = latest.get(q["id"], {}).get("attempts", [])
        if attempts:
            sql = attempts[0]["sql"]
            res = execute_sql(sql, as_of=meta["meta"]["run_date"])
            ok = passes(q["id"], res)
        else:
            try:
                evidence = {}
                sql = ask(args.provider, api_key, model, q["question"], response_evidence=evidence)
            except Exception as exc:
                print(f"provider error on {q['id']}: {exc}")
                return 2
            res = execute_sql(sql, as_of=meta["meta"]["run_date"])
            ok = passes(q["id"], res)
            fp = candidate_fingerprint(res)
            attempts.append({"n": 1, "sql": sql, "outcome": res["outcome"],
                             "note": res.get("note", ""), "fingerprint": fp})
            if res["outcome"] == "result_contract_error":
                attempts[-1].update(evidence)
            with out_path.open("a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps({"id": q["id"], "question": q["question"],
                                    "model": model, "attempts": attempts}) + "\n")
                f.flush()
                os.fsync(f.fileno())
        if not ok:
            if res["outcome"] == "ok":
                fb = ("the query executed but its result does not match the verified answer "
                      "(check column order, grouping keys and the exact filters)")
            else:
                fb = f"{res['outcome']}: {res.get('note', '')}"
            try:
                evidence2 = {}
                sql2 = ask(args.provider, api_key, model, q["question"], feedback=fb, prior_sql=sql, response_evidence=evidence2)
            except Exception as exc:  # noqa: BLE001 — attempt 1 is already saved
                print(f"provider error on {q['id']} attempt 2: {exc}")
                print(f"progress saved in {out_path} — re-run the same command to resume.")
                return 2
            res2 = execute_sql(sql2, as_of=meta["meta"]["run_date"])
            fp2 = candidate_fingerprint(res2)
            attempts.append({"n": 2, "sql": sql2, "outcome": res2["outcome"],
                             "note": res2.get("note", ""), "fingerprint": fp2})
            if res2["outcome"] == "result_contract_error":
                attempts[-1].update(evidence2)
        records.append({"id": q["id"], "question": q["question"], "model": model, "attempts": attempts})
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
