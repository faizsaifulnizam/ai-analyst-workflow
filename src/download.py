"""Download the raw HDB resale dataset from data.gov.sg into data/raw/.

One official file:
  - hdb-resale-prices-2017-onwards.csv
    (HDB resale flat prices based on registration date from Jan 2017 onwards,
     dataset d_8b84c4ee58e3cfc0ece0d773c8ca6abc)

Flow: initiate-download -> poll-download -> signed URL (data.gov.sg v1 public API).
Run: python src/download.py [--force]   (validates an existing cache before reuse)

Downloads land in a .part file and are structurally validated (exact header,
non-empty, month coverage floors) BEFORE the raw CSV is replaced. On success
writes data/raw/pull_manifest.json: dataset id, source URLs, retrieval time,
byte size, SHA-256, row count and month coverage.

The manifest is committed (the only committed data/raw artifact besides the
lineage note) and doubles as the figure date receipt: `retrieved_at` is kept
verbatim while the file bytes are unchanged, so identical inputs regenerate
identical figures. Changed bytes get a new receipt time.
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request as u
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw"
OUT = RAW / "hdb-resale-prices-2017-onwards.csv"
MANIFEST = RAW / "pull_manifest.json"
DATASET = "d_8b84c4ee58e3cfc0ece0d773c8ca6abc"
DATASET_URL = f"https://data.gov.sg/datasets/{DATASET}/view"
EXPECTED_HEADER = ("month,town,flat_type,block,street_name,storey_range,floor_area_sqm,"
                   "flat_model,lease_commence_date,remaining_lease,resale_price")
ROW_FLOOR = 240000        # a truncated pull must fail loudly (241,822 rows at the 2026-10-02 pull)
MONTH_FLOOR_EARLY = "2017-01"
MONTH_FLOOR_LATE = "2025-06"   # freshness floor: data must run at least to this month
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"


def get(url, ref="https://data.gov.sg/"):
    r = u.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Referer": ref})
    with u.urlopen(r, timeout=300) as resp:
        return resp.read()


def validate(data: bytes):
    """Structural validation + summary. Returns (info, problems)."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, [f"not UTF-8: {exc}"]
    lines = text.splitlines()
    problems = []
    if not lines:
        return None, ["file is empty"]
    header = lines[0].strip().lstrip("\ufeff")
    if header != EXPECTED_HEADER:
        problems.append(f"header mismatch: {header!r}")
    body = [ln for ln in lines[1:] if ln.strip()]
    if len(body) < ROW_FLOOR:
        problems.append(f"only {len(body)} rows (< floor {ROW_FLOOR})")
    months = sorted({ln[:7] for ln in body if len(ln) > 6 and ln[4:5] == "-" and ln[:4].isdigit()})
    if not months:
        problems.append("no parseable YYYY-MM months")
    else:
        if months[0] > MONTH_FLOOR_EARLY:
            problems.append(f"earliest month {months[0]} is later than the floor {MONTH_FLOOR_EARLY}")
        if months[-1] < MONTH_FLOOR_LATE:
            problems.append(f"latest month {months[-1]} is below the freshness floor {MONTH_FLOOR_LATE}")
    if problems:
        return None, problems
    return {
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "rows": len(body),
        "month_min": months[0],
        "month_max": months[-1],
        "months": len(months),
    }, []


def manifest_text(info, retrieved_at):
    m = {
        "dataset_id": DATASET,
        "dataset_url": DATASET_URL,
        "file": OUT.name,
        "retrieved_at": retrieved_at,
        "source": "data.gov.sg — api-open v1 public API (signed URL flow)",
        **info,
    }
    return json.dumps(m, indent=2) + "\n"


def write_manifest(info, retrieved_at):
    """Temp + atomic replace; keeps byte-stable JSON formatting."""
    part = MANIFEST.with_name(MANIFEST.name + ".part")
    part.write_text(manifest_text(info, retrieved_at), encoding="utf-8", newline="\n")
    os.replace(part, MANIFEST)
    print("manifest:", MANIFEST.name)
    for k in ("retrieved_at", "rows", "month_min", "month_max", "sha256"):
        print(f"    {k}: {info.get(k, retrieved_at) if k == 'retrieved_at' else info[k]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-download even if the cache validates")
    args = ap.parse_args()

    if OUT.exists() and not args.force:
        info, problems = validate(OUT.read_bytes())
        if problems:
            raise SystemExit("cached CSV failed validation (use --force):\n  - " + "\n  - ".join(problems))
        kept = None
        if MANIFEST.exists():
            try:
                old = json.loads(MANIFEST.read_text(encoding="utf-8"))
                if old.get("sha256") == info["sha256"]:
                    kept = old.get("retrieved_at")   # same bytes -> receipt keeps its retrieval time
            except (OSError, ValueError):
                kept = None
        if MANIFEST.exists() and kept is not None:
            print("raw cache validated against the committed receipt; use --force to refresh")
        else:
            write_manifest(info, kept or datetime.now().astimezone().isoformat(timespec="seconds"))
        return 0

    print(f"downloading {DATASET} ...")
    base = f"https://api-open.data.gov.sg/v1/public/api/datasets/{DATASET}"
    url = ""
    try:
        j = json.loads(get(base + "/poll-download"))
        url = (j.get("data") or {}).get("url") or ""
    except Exception as exc:  # a 403 and "not ready yet" must not look the same
        print(f"  poll-download ({type(exc).__name__}): {ascii(str(exc))}")
    if not url:
        get(base + "/initiate-download")
        for _ in range(15):
            time.sleep(1.5)
            try:
                j = json.loads(get(base + "/poll-download"))
                url = (j.get("data") or {}).get("url") or ""
            except Exception:
                continue
            if url:
                break
    if not url:
        raise SystemExit("no signed URL returned — try again in a minute")

    part = OUT.with_name(OUT.name + ".part")
    try:
        part.write_bytes(get(url))
        info, problems = validate(part.read_bytes())
        if problems:
            raise SystemExit("download failed structure validation — kept existing file:\n  - " + "\n  - ".join(problems))
        kept = None
        if MANIFEST.exists():
            try:
                old = json.loads(MANIFEST.read_text(encoding="utf-8"))
                if old.get("sha256") == info["sha256"]:
                    kept = old.get("retrieved_at")
            except (OSError, ValueError):
                kept = None
        os.replace(part, OUT)
        write_manifest(info, kept or datetime.now().astimezone().isoformat(timespec="seconds"))
        print(f"  ok: {info['bytes']} bytes | {info['rows']} rows | {info['month_min']} -> {info['month_max']}")
    finally:
        part.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
