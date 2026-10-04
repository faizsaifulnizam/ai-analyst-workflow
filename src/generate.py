"""Generate candidate SQL for every golden question via Groq (free tier).

Run:  python src/generate.py                 (writes outputs/reruns/<today>/candidates.jsonl)
      python src/generate.py --out <dir>     (explicit output directory)

Without GROQ_API_KEY in the environment this prints how to re-run and exits 0 —
the committed candidates are re-validated offline by src/validate.py, which is
the deterministic half of the workflow. A re-run NEVER touches the committed
receipt (outputs/candidates.jsonl, outputs/results.csv, outputs/summary.json):
new runs land in outputs/reruns/<date>/ and are compared, not adopted silently.

Model selection happens at RUNTIME against https://api.groq.com/openai/v1/models
(no guessed model ids): a preferred free chat model is used when it is listed,
otherwise the lexicographically last non-vision llama chat model. The exact id,
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
import sys
import time
import urllib.request as u
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.guardrails import execute_sql  # noqa: E402
from src.fingerprint import fingerprint, load_golden  # noqa: E402

API = "https://api.groq.com/openai/v1"
PROMPT_TEMPLATE = (ROOT / "prompts/sql_prompt.md").read_text(encoding="utf-8")
PREFERRED_MODEL = "llama-3.3-70b-versatile"   # used only if listed at run time
TEMPERATURE = 0
MAX_TOKENS = 1024
SGT = timezone(timedelta(hours=8))


def key():
    k = os.environ.get("GROQ_API_KEY", "").strip()
    if not k:
        return None
    return k


def call_api(path, payload=None, api_key=None, timeout=120):
    req = u.Request(API + path, method="POST" if payload is not None else "GET",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    if payload is not None:
        req.data = json.dumps(payload).encode("utf-8")
    with u.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def pick_model(models):
    ids = sorted(m["id"] for m in models)
    if PREFERRED_MODEL in ids:
        return PREFERRED_MODEL
    chat = [i for i in ids if "llama" in i and "vision" not in i and "guard" not in i]
    return chat[-1] if chat else ids[-1]


def build_prompt(question):
    return PROMPT_TEMPLATE.replace("{question}", question)


def extract_sql(text):
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        t = t.removeprefix("sql").strip()
    return t.strip()


def ask(model, question, feedback=None, prior_sql=None):
    prompt = build_prompt(question)
    if feedback:
        prompt += ("\n\nYour previous attempt was:\n" + prior_sql +
                   "\n\nIt did not produce the expected result (" + feedback + "). "
                   "Reread the contract (column order, ordering, rounding) and the schema, then write a corrected single SELECT.")
    body = {"model": model, "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}]}
    resp = call_api("/chat/completions", body)
    return extract_sql(resp["choices"][0]["message"]["content"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="output directory (default outputs/reruns/<today>)")
    ap.add_argument("--model", default=None, help="override the model id (recorded as-is)")
    args = ap.parse_args()

    api_key = key()
    if not api_key:
        print("GROQ_API_KEY is not set — generation skipped (nothing written).")
        print("To re-run generation:  export GROQ_API_KEY=...   then   python src/generate.py")
        print("The committed candidates stay authoritative; src/validate.py re-checks them offline.")
        return 0

    models = call_api("/models", api_key=api_key)["data"]
    model = args.model or pick_model(models)
    golden = load_golden()
    out_dir = Path(args.out) if args.out else ROOT / "outputs/reruns" / datetime.now(SGT).date().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "candidates.jsonl"

    print(f"model: {model}   (listed models: {len(models)})")
    print(f"questions: {len(golden['questions'])}   out: {out_path}")

    records = []
    want = {q["id"]: (q.get("fingerprint") or {}) for q in golden["questions"]}

    def passes(qid, res):
        if res["outcome"] != "ok":
            return False
        n, h = fingerprint(res["rows"])
        w = want[qid]
        return w.get("rows") == n and w.get("sha256") == h

    for i, q in enumerate(golden["questions"], 1):
        attempts = []
        sql = ask(model, q["question"])
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
            sql2 = ask(model, q["question"], feedback=fb, prior_sql=sql)
            res2 = execute_sql(sql2)
            fp2 = fingerprint(res2["rows"]) if res2["outcome"] == "ok" else None
            attempts.append({"n": 2, "sql": sql2, "outcome": res2["outcome"],
                             "note": res2.get("note", ""), "fingerprint": fp2})
        records.append({"id": q["id"], "question": q["question"], "attempts": attempts})
        print(f"  [{i:2d}/{len(golden['questions'])}] {q['id']}  attempt1={attempts[0]['outcome']}"
              + (f" attempt2={attempts[1]['outcome']}" if len(attempts) > 1 else ""))
        time.sleep(0.5)

    meta = {
        "meta": {
            "run_date": datetime.now(SGT).date().isoformat(),
            "run_at": datetime.now(SGT).isoformat(timespec="seconds"),
            "model": model,
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
            "prompt": "prompts/sql_prompt.md",
            "golden_set_version": golden.get("version"),
            "listed_models": sorted(m["id"] for m in models),
        }
    }
    tmp = out_path.with_name(out_path.name + ".part")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(meta) + "\n")
        for r in records:
            f.write(json.dumps(r) + "\n")
    os.replace(tmp, out_path)
    print(f"wrote {len(records)} candidate records -> {out_path}")
    print("next: python src/validate.py --candidates", out_path.as_posix(), "--outdir", out_dir.as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
