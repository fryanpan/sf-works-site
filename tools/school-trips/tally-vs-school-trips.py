#!/usr/bin/env python3
"""Compare the 2024-25 Travel Tally workbook (records request 26-9690), school by school, with School Trips' modelled mode shares for today.

    python3 tools/school-trips/tally-vs-school-trips.py

Report only. It reads .cache/records-26-9690/ (gitignored; a worktree falls back to the main checkout's copy) and the
tracked site/data/school-sim/ files, prints the comparison, and writes no file. It runs no simulation. Nothing on the
site reads it. sources/sf-srts-travel-tally.md carries the results.

A tally share is the average of the morning and afternoon shares, the memo's rule (tools/school-trips/records-26-9690-check.py).
The tally has no yellow bus category: its transit includes the bus, so the like-for-like comparison is the model's
transit plus bus against the tally's transit. The model covers every grade at a school; the tally covers K, 5th, 6th
and 9th. The model is calibrated to grade totals and not to schools, so a school's gap is the model's spatial pattern against a
one-day classroom count, and a small tally is noisy: MIN_TALLY keeps schools with enough responses for the school table.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import importlib.util
import json
import math
import re
import statistics
from pathlib import Path

ROOT = Path(paths.ROOT)
rec = paths.load("records-26-9690-check.py", "rec")

SIM = ROOT / "site" / "data" / "school-sim"
TODAY = "ss0-calm0-conn0-muni0-bus0"
MIN_TALLY = 50
# Workbook name to the sim's, after canon(), where the two still differ. Both campuses of a school the sim holds as one
# go to that school, and their tallies are pooled.
ALIAS = {
    "bessie carmichael fec elementary campus": "bessie carmichael fec",
    "bessie carmichael fec middle school campus": "bessie carmichael fec",
    "claire lilienthal elementary madison campus": "claire lilienthal elementary",
    "claire lilienthal elementary scott campus": "claire lilienthal elementary",
    "presidio middle school": "presidio middle",
    "sota ruth asawa sf sch of the arts a public school": "ruth asawa sf sch of the arts a public school",
}
AM = {"walk": "AQ", "bike": "AR", "transit": "AS", "carpool": "AT", "other": "AU", "car": "AV"}
PM = {"walk": "BD", "bike": "BE", "transit": "BF", "carpool": "BG", "other": "BH", "car": "BI"}


def canon(name):
    """Lower case words, with the sim's 'Last (First) Rest' turned to 'First Last Rest'."""
    s = name.strip().strip('"')
    s = re.sub(r"^([^(]+?) \(([^)]+)\)", r"\2 \1", s)
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s.lower()).split())


def tally_rows():
    rows = rec.sheet(rec.WORKBOOK, "2024-2025")[4:]
    level, out = None, []
    for r in rows:
        am, pm = rec.num(r, "AP"), rec.num(r, "BC")
        name = (r.get("A") or "").strip().strip('"')
        if name in ("Elementary schools", "Middle schools", "High schools"):
            level = name.split()[0]
        if not (am or pm):
            continue
        share = {}
        for m in AM:
            parts = [rec.num(r, AM[m]) / am] if am else []
            parts += [rec.num(r, PM[m]) / pm] if pm else []
            share[m] = 100 * sum(parts) / len(parts)
        out.append({"name": name, "level": level, "n": (am + pm) / 2, "share": share, "bus": rec.num(r, "AO"),
                    "enrolled": rec.num(r, "J"), "sd": r.get("D")})
    return out


def corr(a, b):
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb) if sa and sb else float("nan")


def main():
    index = json.load(open(SIM / "index.json"))
    city = json.load(open(SIM / "city.json"))
    sim = {canon(s["name"]): s for s in index["schools"] if not s.get("charter") and not s.get("private")}
    grouped, unmatched = {}, []
    for t in tally_rows():
        k = canon(t["name"])
        k = ALIAS.get(k, k)
        if k not in sim:
            unmatched.append(t["name"])
            continue
        g = grouped.get(k)
        if g is None:
            grouped[k] = dict(t, share=dict(t["share"]))
            continue
        n = g["n"] + t["n"]
        g["share"] = {m: (g["share"][m] * g["n"] + t["share"][m] * t["n"]) / n for m in g["share"]}
        g["n"], g["bus"] = n, g["bus"] + t["bus"]
        g["enrolled"] += t["enrolled"]
    pairs = []
    for k, t in grouped.items():
        s = sim[k]
        g = json.load(open(SIM / f"{s['cds']}.json"))["grid"][TODAY]["0"]
        pairs.append((t, s, {x: g[x][1] for x in ("car", "carpool", "walk", "bike", "transit", "bus")}))
    print(f"Matched {len(pairs)} sim schools. Unmatched tally rows: {unmatched}")
    print(f"Sim public schools with no tally: {sorted(s['name'] for k, s in sim.items() if k not in grouped)}")

    def model(m, mode):
        return m["transit"] + m["bus"] if mode == "transit" else m.get(mode, 0)

    print("\nTally schools, weighted by tally responses (tally, model):")
    total = sum(t["n"] for t, _, _ in pairs)
    for mode in ("car", "carpool", "walk", "bike", "transit"):
        a = sum(t["share"][mode] * t["n"] for t, _, _ in pairs) / total
        b = sum(model(m, mode) * t["n"] for t, _, m in pairs) / total
        print(f"  {mode}: {a:.1f}, {b:.1f}")
    print("By level, weighted by tally responses (schools, tally car, model car, tally transit, model transit+bus, tally walk, model walk):")
    for level in ("Elementary", "Middle", "High"):
        ps = [p for p in pairs if p[0]["level"] == level]
        n = sum(t["n"] for t, _, _ in ps)
        f = [sum(g(t, m) * t["n"] for t, _, m in ps) / n for g in (
            lambda t, m: t["share"]["car"], lambda t, m: m["car"], lambda t, m: t["share"]["transit"],
            lambda t, m: model(m, "transit"), lambda t, m: t["share"]["walk"], lambda t, m: m["walk"])]
        print(f"  {level}: {len(ps)}, " + ", ".join(f"{x:.1f}" for x in f))

    big = [p for p in pairs if p[0]["n"] >= MIN_TALLY]
    print(f"\nSchool level, {len(big)} schools with at least {MIN_TALLY} responses:")
    for mode in ("car", "walk", "transit", "bike"):
        a = [t["share"][mode] for t, _, _ in big]
        b = [model(m, mode) for _, _, m in big]
        gaps = sorted(abs(x - y) for x, y in zip(a, b))
        print(f"  {mode}: sd tally {statistics.pstdev(a):.1f}, sd model {statistics.pstdev(b):.1f}, r {corr(a, b):.2f}, mean gap {statistics.fmean(y - x for x, y in zip(a, b)):+.1f}, "
              f"median abs gap {gaps[len(gaps) // 2]:.1f}, 90th {gaps[int(len(gaps) * .9)]:.1f}, "
              f"within 10 pts {sum(1 for g in gaps if g <= 10)}")
    within = [p for p in big if p[0]["level"] == "Elementary"]
    print(f"  car, elementary only: r {corr([t['share']['car'] for t, _, _ in within], [m['car'] for _, _, m in within]):.2f}")
    print("Largest family-car gaps (school, level, responses, tally, model):")
    for t, s, m in sorted(big, key=lambda p: -abs(p[0]["share"]["car"] - p[2]["car"]))[:12]:
        print(f"  {t['name']}, {t['level']}, {t['n']:.0f}, {t['share']['car']:.1f}, {m['car']:.1f}")

    print("\nEnrolment and yellow bus:")
    known = [p for p in pairs if p[0]["enrolled"]]  # '#REF!' and 'N/A' cells read as 0 here
    print(f"  enrolment on the {len(known)} schools with a figure: workbook {sum(t['enrolled'] for t, _, _ in known):.0f}, sim {sum(s['students'] for _, s, _ in known)}")
    bus_tally = sum(t["bus"] for t, _, _ in pairs)
    bus_model = sum(m["bus"] / 100 * s["students"] for _, s, m in pairs)
    print(f"  yellow bus: workbook count {bus_tally:.0f}, model riders {bus_model:.0f} on the matched schools")
    a = [100 * t["bus"] / t["enrolled"] for t, _, _ in pairs if t["enrolled"]]
    b = [m["bus"] for t, _, m in pairs if t["enrolled"]]
    print(f"  bus share by school: r {corr(a, b):.2f}")

    # Each case in a set is ten numbers, low first, so the central case's family-car students sit at index 10.
    car = city["sets"]["today|today|0000000"][10]
    print(f"\nCity view today: {car:.0f} family-car students of {city['students']}, {100 * car / city['students']:.1f}%; tally basis {city['tallyCar']}")
    model_sfusd = sum(m["car"] * s["students"] for _, s, m in pairs) / sum(s["students"] for _, s, _ in pairs)
    print(f"Model family car on the matched schools, weighted by students: {model_sfusd:.1f}%")


if __name__ == "__main__":
    main()
