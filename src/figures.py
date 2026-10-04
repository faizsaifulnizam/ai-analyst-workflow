"""Figures 2–3 for the eval receipt — code-generated, series style, light + dark.

Run:  python src/figures.py

Produces (reports/figures/), each as a light/dark pair for `<picture>` README embeds,
with matching docs/img/ copies written in the same run:
  f2_pass_rate[-dark].png   — pass rate by question type (incl. the deliberate traps)
  f3_failures[-dark].png    — failure-type breakdown + verdict mix

Inputs are the COMMITTED receipt (outputs/summary.json + outputs/results.csv); the
figure footnote carries the run's as-of date and model id from that receipt and the
dataset pull date from data/raw/pull_manifest.json — never hardcoded.

QA (asserted in-code before every save): title/footnote width at render size by pixel
extent (≥ ~40px right margin), text clearance, in-bounds text, annotation overlaps,
legend-vs-annotation overlaps. Each figure is rendered TWICE in the same environment
and the two PNGs are sha256-compared before promotion; a mismatch is ship-blocking.
"""
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.style import use_series_style  # noqa: E402

use_series_style()

import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.text as mtext  # noqa: E402
from matplotlib.font_manager import FontProperties  # noqa: E402
from matplotlib.textpath import TextPath  # noqa: E402

FIGDIR = ROOT / "reports/figures"
IMGDIR = ROOT / "docs/img"
SUMMARY = ROOT / "outputs/summary.json"
RESULTS = ROOT / "outputs/results.csv"
MANIFEST = ROOT / "data/raw/pull_manifest.json"
DPI = 200
MARGIN_PX = 40  # keep text this far from the canvas edge

LIGHT = dict(ink="#14293D", petrol="#22607B", burnt="#C0552B", teal="#2E7D6B",
             violet="#8A6EAF", brass="#B9975B", muted="#5C6B79", light="#C9C6BF",
             edge="white", suffix="")
DARK = dict(ink="#E7E3DC", petrol="#4C93B5", burnt="#D97E4F", teal="#45A08B",
            violet="#A78FC8", brass="#D4B87A", muted="#8B98A5", light="#435D73",
            edge="#14293D", suffix="-dark")
T = LIGHT

SGT = timezone(timedelta(hours=8))


def use_palette(p):
    global T
    T = p


def load_receipt():
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    with RESULTS.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    pull = ""
    try:
        ts = json.loads(MANIFEST.read_text(encoding="utf-8")).get("retrieved_at", "")
        if ts:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=SGT)
            pull = dt.astimezone(SGT).date().isoformat()
    except Exception:
        pull = "n/a"
    return summary, rows, pull


# ---------- QA helpers (series harness) ----------

def foot(fig, text):
    return fig.text(0.012, 0.012, text, fontsize=7.5, color=T["muted"], va="bottom")


def drawn_title(ax):
    for t in (ax._left_title, ax.title, ax._right_title):
        if t.get_text().strip():
            return t
    return ax.title


def assert_clear(fig, pairs, label):
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    for a, b in pairs:
        ba, bb = a.get_window_extent(r), b.get_window_extent(r)
        ok = not ba.overlaps(bb)
        print(f"   [{'PASS' if ok else 'FAIL'}] clearance {label}")
        assert ok, f"{label}: text boxes overlap"


def assert_inbounds(fig, label, pad=3):
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    w, h = fig.canvas.get_width_height()
    bad = []
    for t in fig.findobj(mtext.Text):
        if not t.get_text().strip() or not t.get_visible():
            continue
        bb = t.get_window_extent(r)
        if bb.x0 < pad or bb.y0 < pad - 2 or bb.x1 > w - pad or bb.y1 > h - pad:
            bad.append((t.get_text()[:44].replace("\n", " / "), round(bb.x0), round(bb.x1)))
    ok = not bad
    print(f"   [{'PASS' if ok else 'FAIL'}] in-bounds {label} ({len(bad)} clipped)")
    for b in bad[:6]:
        print("       clipped:", b)
    assert ok, f"{label}: {len(bad)} text artist(s) clipped"


def assert_texts_clear(fig, label):
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    bad = []
    for ax in fig.axes:
        texts = [t for t in ax.texts if t.get_text().strip() and t.get_visible()]
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                if texts[i].get_window_extent(r).overlaps(texts[j].get_window_extent(r)):
                    bad.append((texts[i].get_text()[:32], texts[j].get_text()[:32]))
    ok = not bad
    print(f"   [{'PASS' if ok else 'FAIL'}] annotation overlaps {label} ({len(bad)})")
    assert ok, f"{label}: {len(bad)} annotation overlap(s)"


def assert_legend_clear(fig, label):
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    bad = []
    for ax in fig.axes:
        leg = ax.get_legend()
        if leg is None:
            continue
        lb = leg.get_window_extent(r)
        for t in ax.texts:
            if t.get_text().strip() and t.get_visible() and lb.overlaps(t.get_window_extent(r)):
                bad.append((t.get_text()[:30], "legend"))
    ok = not bad
    print(f"   [{'PASS' if ok else 'FAIL'}] legend vs annotations {label} ({len(bad)})")
    assert ok, f"{label}: {len(bad)} legend/annotation overlap(s)"


def text_px(s, size_pt):
    fp = FontProperties(family="Inter", size=size_pt)
    return max(TextPath((0, 0), line, prop=fp).get_extents().width / 72 * DPI
               for line in s.split("\n"))


def assert_fits(s, size_pt, label, canvas_in):
    px = text_px(s, size_pt)
    limit = canvas_in * DPI - MARGIN_PX
    ok = px <= limit
    print(f"   [{'PASS' if ok else 'FAIL'}] width {label}: {px:.0f}px vs {limit:.0f}px limit")
    assert ok, f"{label} too wide: {px:.0f}px > {limit:.0f}px"


# ---------- rendering (build twice, hash-compare, then promote) ----------

def fig_to_png_bytes(fig):
    import io
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def render(build, name):
    """Two same-env renders must be byte-identical; promote only after the check."""
    a = fig_to_png_bytes(build())
    b = fig_to_png_bytes(build())
    ha = hashlib.sha256(a).hexdigest()
    hb = hashlib.sha256(b).hexdigest()
    ok = ha == hb
    print(f"   [{'PASS' if ok else 'FAIL'}] determinism {name}: {ha[:16]} == {hb[:16]}")
    assert ok, f"{name} renders differ in the same environment"
    target = FIGDIR / name.replace(".png", T["suffix"] + ".png")
    tmp = target.with_name(target.name + ".part")
    tmp.write_bytes(a)
    os.replace(tmp, target)
    mirror = IMGDIR / target.name
    mtmp = mirror.with_name(mirror.name + ".part")
    mtmp.write_bytes(a)
    os.replace(mtmp, mirror)
    print(f"   wrote {target.name} ({len(a)} bytes) + docs/img/{mirror.name}")


# ---------- the figures ----------

TYPE_ORDER = ["filter", "aggregation", "ratio", "grouping", "window", "distinct", "date", "ambiguous"]


def build_f2(summary):
    totals = summary["totals"]
    by_type = summary["by_type"]
    by_trap = summary["by_trap"]
    run = summary["receipt"]
    models = ", ".join(run.get("models_used") or [run.get("model") or "unknown"])
    canvas_in = 9.0
    title = (f"{totals['passed']} of {totals['questions']} verified answers reproduced "
             f"({totals['pass_first_try']} first try) — by question type")
    sub = ("The right panel isolates the deliberate traps; a pass is a byte-exact result fingerprint, not a human review")
    foottext = (f"As-of run {run.get('run_date')} · model {models} · temperature {run.get('temperature')}\n"
                f"Fingerprint = row count + sha256 over ordered rows (2dp canonical serializer) · "
                f"source: outputs/summary.json, outputs/results.csv\n"
                f"Data: HDB resale via data.gov.sg, pulled {PULL_DATE}")
    assert_fits(title, 12.5, "F2 title", canvas_in)
    assert_fits(foottext, 7.5, "F2 footnote", canvas_in)

    types = [t for t in TYPE_ORDER if t in by_type]
    fig, axs = plt.subplots(1, 2, figsize=(canvas_in, 4.7))
    st = fig.suptitle(title, x=0.012, y=0.975, ha="left", fontsize=12.5, color=T["ink"])
    fig.text(0.012, 0.917, sub, fontsize=8.5, color=T["muted"], ha="left")

    # panel A — stacked passed/failed per question type
    ax = axs[0]
    xs = range(len(types))
    passed = [by_type[t]["passed"] for t in types]
    failed = [by_type[t]["n"] - by_type[t]["passed"] for t in types]
    ax.bar(xs, passed, color=T["teal"], label="passed (fingerprint match)", edgecolor=T["edge"])
    ax.bar(xs, failed, bottom=passed, color=T["burnt"], label="failed", edgecolor=T["edge"])
    ax.set_xticks(list(xs))
    ax.set_xticklabels(types, rotation=30, ha="right")
    ax.tick_params(axis="x", pad=5)
    for i, t in enumerate(types):
        n = by_type[t]["n"]
        ax.annotate(f"{by_type[t]['passed']}/{n}", (i, n + 0.18), ha="center",
                    fontsize=8.5, color=T["ink"])
    ax.set_ylim(0, max(by_type[t]["n"] for t in types) + 1.2)
    ax.set_ylabel("questions", fontsize=9)
    ax.set_title("By question type", fontsize=10, color=T["muted"])
    ax.legend(loc="best", fontsize=8)

    # panel B — trap vs non-trap pass rate
    ax = axs[1]
    labels = [f"deliberate traps\n({by_trap['true']['n']} questions)",
              f"everything else\n({by_trap['false']['n']} questions)"]
    keys = ["true", "false"]
    rates = [by_trap[k]["passed"] / by_trap[k]["n"] * 100 for k in keys]
    bars = ax.bar(range(2), rates, color=[T["burnt"], T["petrol"]],
                  edgecolor=T["edge"], width=0.55)
    for i, k in enumerate(keys):
        ax.annotate(f"{by_trap[k]['passed']}/{by_trap[k]['n']} = {rates[i]:.0f}%",
                    (i, rates[i] + 2.5), ha="center", fontsize=9, color=T["ink"])
    ax.set_xticks(range(2))
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 118)
    ax.set_ylabel("pass rate (%)", fontsize=9)
    ax.set_title("Trap questions vs the rest", fontsize=10, color=T["muted"])

    fig.subplots_adjust(left=0.085, right=0.985, top=0.80, bottom=0.235, wspace=0.22)
    ftxt = foot(fig, foottext)
    assert_clear(fig, [(st, drawn_title(axs[0])), (st, drawn_title(axs[1])),
                       (ftxt, axs[0].get_xticklabels()[-1])], "F2 suptitle/title + footnote/ticks")
    assert_inbounds(fig, "F2")
    assert_texts_clear(fig, "F2")
    assert_legend_clear(fig, "F2")
    return fig


MISMATCH_ORDER = ["value_mismatch", "wrong_row_count", "sql_error", "guardrail_reject", "timeout"]


def build_f3(summary):
    totals = summary["totals"]
    mm = summary["mismatch_counts"]
    run = summary["receipt"]
    models = ", ".join(run.get("models_used") or [run.get("model") or "unknown"])
    canvas_in = 9.0
    n_fail = totals["fail"]
    top = max(mm, key=mm.get) if mm else "none"
    title = f"{n_fail} of {totals['questions']} questions failed — failure types and verdict mix"
    sub = (f"Largest failure class: {top}" if mm
           else "No failure was recorded in this run — the taxonomy is still the contract")
    foottext = (f"As-of run {run.get('run_date')} · model {models} · ≤2 attempts per question\n"
                "Mismatch taxonomy: value_mismatch · wrong_row_count · sql_error · guardrail_reject · timeout\n"
                f"Source: outputs/summary.json, outputs/results.csv · data: HDB resale via data.gov.sg, pulled {PULL_DATE}")
    assert_fits(title, 12.5, "F3 title", canvas_in)
    assert_fits(foottext, 7.5, "F3 footnote", canvas_in)

    fig, axs = plt.subplots(1, 2, figsize=(canvas_in, 4.7))
    st = fig.suptitle(title, x=0.012, y=0.975, ha="left", fontsize=12.5, color=T["ink"])
    fig.text(0.012, 0.917, sub, fontsize=8.5, color=T["muted"], ha="left")

    # panel A — failure classes (every taxonomy class shown, zeroes included)
    ax = axs[0]
    names = MISMATCH_ORDER
    counts = [mm.get(k, 0) for k in names]
    ax.barh(range(len(names)), counts, color=T["burnt"], edgecolor=T["edge"], height=0.6)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names)
    ax.invert_yaxis()
    for i, c in enumerate(counts):
        ax.annotate(str(c), (c + max(counts + [1]) * 0.03, i), va="center",
                    fontsize=9, color=T["ink"])
    ax.set_xlim(0, max(counts + [1]) * 1.25)
    ax.set_xlabel("failed questions (final attempt)", fontsize=9)
    ax.set_title("Failure type", fontsize=10, color=T["muted"])

    # panel B — verdict mix
    ax = axs[1]
    mix = [("pass first try", totals["pass_first_try"], T["teal"]),
           ("pass after one retry", totals["pass_after_retry"], T["petrol"]),
           ("fail after retry", totals["fail"], T["burnt"])]
    ax.bar(range(3), [m[1] for m in mix], color=[m[2] for m in mix],
           edgecolor=T["edge"], width=0.55)
    for i, m in enumerate(mix):
        ax.annotate(str(m[1]), (i, m[1] + max(x[1] for x in mix) * 0.035),
                    ha="center", fontsize=9, color=T["ink"])
    ax.set_xticks(range(3))
    ax.set_xticklabels([m[0] for m in mix], rotation=20, ha="right")
    ax.set_ylim(0, max(x[1] for x in mix) * 1.22 + 0.5)
    ax.set_ylabel("questions", fontsize=9)
    ax.set_title("Verdict mix (32 questions)", fontsize=10, color=T["muted"])

    fig.subplots_adjust(left=0.135, right=0.985, top=0.80, bottom=0.245, wspace=0.30)
    ftxt = foot(fig, foottext)
    assert_clear(fig, [(st, drawn_title(axs[0])), (st, drawn_title(axs[1])),
                       (ftxt, axs[0].get_xticklabels()[-1])], "F3 suptitle/title + footnote/ticks")
    assert_inbounds(fig, "F3")
    assert_texts_clear(fig, "F3")
    assert_legend_clear(fig, "F3")
    return fig


def main():
    os.chdir(ROOT)
    global PULL_DATE
    summary, rows, PULL_DATE = load_receipt()
    FIGDIR.mkdir(parents=True, exist_ok=True)
    IMGDIR.mkdir(parents=True, exist_ok=True)
    for palette in (LIGHT, DARK):
        use_palette(palette)
        use_series_style(dark=(palette is DARK))
        print(f"-- rendering {'dark' if palette['suffix'] else 'light'} set --")
        render(lambda: build_f2(summary), "f2_pass_rate.png")
        render(lambda: build_f3(summary), "f3_failures.png")
    print("figures done — 2 charts x light/dark, mirrored to docs/img/ in the same run")


if __name__ == "__main__":
    main()
