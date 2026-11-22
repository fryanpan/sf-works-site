#!/usr/bin/env python3
"""How people travel between each SF neighborhood or Supervisor district and every neighborhood and Bay Area region, for the Street Safety map's where-traffic-comes-from view: person trips by car, transit, bike and walking, and the typical morning trip's minutes and miles by each, from MTC's Travel Model 1.6 trip files and skims.

    ~/.venvs/sf-works-geo/bin/python -I tools/street-safety/where-traffic-modes.py                 # build
    ~/.venvs/sf-works-geo/bin/python -I tools/street-safety/where-traffic-modes.py --published     # the totals for the source file
    ~/.venvs/sf-works-geo/bin/python -I tools/street-safety/where-traffic-modes.py --thresholds sunset-parkside   # candidate tests, to stdout only

Bryan, 2026-11-20: "For each region try to compute car vs bike vs transit trip length and challenges", then "I want us
to think about fractions and current mode share and what might shift". Prior work:
research/notes/street-safety-2026-11/2026-11-20-mode-skims-prior-work.md. We adopt MTC's own trip files and skims
(research/sources/mtc-travel-model-1-6-skims.md) and build only the tabulation by area and unit.

WHAT IS COUNTED
  A person trip, every purpose, a 2023 weekday: one row of indivTripData is one person, one row of jointTripData is
  num_participants people, and each row stands for 1/sampleRate trips. Modes (MTC's trip_mode): car 1 to 6 and
  taxi and ride-hail 19 to 21; walk 7; bike 8; transit reached on foot 9 to 13; transit reached by car 14 to 18.
  This is every person trip between two places, by its two ends. It isn't the cars on the area's streets that the
  bubbles count: a trip passing through the area has neither end in it and isn't here.

THE UNITS
  The 47 groups of where-traffic-comes-from.py (41 neighborhoods, six regions of MTC superdistricts). An MTC zone in
  SF is split over neighborhoods and districts by the weights tools/street-safety/through-traffic.py prep gave its SF-CHAMP zones
  (LODES homes plus jobs), recovered here from routing.npz's car trips, which carry them as an exact factor. For a
  chosen area, a trip counts for a unit when one end is in the area and the other is in the unit and outside the area;
  `own` is both ends in the area.

TIMES AND MILES (MTC's SimpleTimeSkims and SimpleDistanceSkims, AM peak, 6 to 10 am, door to door)
  car      `da`: congested drive-alone minutes plus the destination's terminal time; network miles
  transit  `wTrnW`: walk to the stop, wait, ride, transfer, walk from the stop, raw minutes added; `dTrnW` the same
           with a drive to the first stop (trips toward the area from a region only)
  bike     `bike`: shortest path on streets that allow bikes, at 12 mph; no hills, no bike lanes in it. Where the
           model's network has a path one way only (the Golden Gate Bridge out of SF), the other direction's miles.
           The skim has no bike path over 75 miles, so "no path" is no path that short
  Within the area (`own`) the pairs inside one zone, which have no transit skim, are left out of the medians and
  no-path shares (the eligibility tests take them; see OUTPUT).
  The medians use the AM peak's skims for every trip, whatever hour it leaves. The eligibility line's transit test
  times each trip in its own period.
  Each figure is the median over zone pairs, weighted by the car person trips on the pair, among the pairs the skim
  has a path for; the share of those car trips on a pair with no path is reported beside it.

OUTPUT  site/data/street-safety/where-from/modes-<slug>.json, one per neighborhood and district (lazy-loaded):
  {"own": row, "from": [row per unit], "to": [...], "both": [...]} where a row is
  [unit, car, transit on foot, transit by car, bike, walk, car min, car miles, transit min, % no transit path,
   drive-to-transit min, bike min, bike miles, % no bike path, transit test, bike test, car trips tested]; a figure
  with no trips to rest on is null. Each test is [car, transit, bike, walk] person trips on the zone pairs that pass
  it: walk-to-transit (`wTrnW`) at most TRN_RATIO times the drive (`da`), each trip timed in the MTC period it leaves
  (EA 3 to 6 am, AM 6 to 10, MD 10 to 3 pm, PM 3 to 7, EV 7 pm to 3 am, from depart_hour), and a bike path of
  BIKE_MI miles or less, which doesn't change by period (Bryan's eligibility line, 2026-11-20). Pairs within one zone
  (inside the area, or a zone split between the area and a unit) are tested like any pair: they have a bike distance,
  and they fail the transit test because the transit skim is empty within a zone. Car trips tested is the row's car
  trips.

Checks (stop on failure): the trip files' row and trip totals, every mode code in 1 to 21, the regional mode shares
within a point of MTC's published figure (Plan Bay Area 2050+ Forecasting and Modeling Report, Figures 30 and 31),
the skims 1,454 x 1,454 with no zero, bike minutes equal to bike miles at 12 mph, every SF zone's weights adding to
1, and every area's unit trips adding to its trips with one end outside it. Fixed inputs (MTC's 2023 run), so the
pipeline step is manual, as through-traffic's is.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import csv
import io
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = Path(paths.ROOT)
sys.path.insert(0, str(HERE))
from lib.stable import write_text  # noqa: E402

SCR = ROOT / "scratch"
if not (SCR / "runs/through-traffic").exists():
    _git = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=ROOT, capture_output=True, text=True)
    if _git.returncode == 0:
        SCR = Path(_git.stdout.strip()).parent / "scratch"
RUNS = SCR / "runs/through-traffic"
MTC = RUNS / "mtc-2023"
SKIMS = SCR / "runs/mode-skims-prior-work"
CACHE = SCR / "runs/where-from-modes"
OUT = ROOT / "site/data/street-safety/where-from"
NZ = 1454
N_DIST = 11
# Mode groups, in the output's order.
CAR, TW, TD, BIKE, WALK = range(5)
GROUP = {**{m: CAR for m in (1, 2, 3, 4, 5, 6, 19, 20, 21)}, 7: WALK, 8: BIKE, **{m: TW for m in range(9, 14)}, **{m: TD for m in range(14, 19)}}
# MTC's published regional share of all trips, 2023, read off Figures 30 and 31 of the Forecasting and Modeling
# Report (pp. 128-129): the mode codes each bar covers and its label in percent.
PUBLISHED = [("Drive alone", (1, 2), 46), ("Two occupants", (3, 4), 20), ("Three or more occupants", (5, 6), 13), ("Taxi and ride-hail", (19, 20, 21), 3),
             ("Walk", (7,), 13), ("Bicycle", (8,), 2), ("Walk to transit", tuple(range(9, 14)), 3), ("Drive to transit", tuple(range(14, 19)), 1)]
BIKE_MPH = 12.0
# The eligibility line's two tests (Bryan, 2026-11-20): transit door to door at most 1.5 times the car time (Van Exel and Van Hagen
# 2011's rail planning cut-off) and a bike path at most 3 miles (65% of tracked Denver e-bike voucher rides were shorter).
TRN_RATIO = 1.5
BIKE_MI = 3.0
PERIODS = ("EA", "AM", "MD", "PM", "EV")


def check(ok, msg):
    if not ok:
        sys.exit("CHECK FAILED: " + msg)
    print("ok  " + msg, file=sys.stderr)


def slug(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


def dump(obj):
    return json.dumps(obj, separators=(",", ":"), sort_keys=True) + "\n"


def period_of_hour(h):
    """MTC's five time periods (0 EA, 1 AM, 2 MD, 3 PM, 4 EV) from a trip's depart_hour, 0 to 23."""
    p = np.full(len(h), -1)
    p[(h >= 3) & (h <= 5)] = 0
    p[(h >= 6) & (h <= 9)] = 1
    p[(h >= 10) & (h <= 14)] = 2
    p[(h >= 15) & (h <= 18)] = 3
    p[(h >= 19) | ((h >= 0) & (h <= 2))] = 4
    return p


def trips_by_period():
    """Daily person trips by MTC period, mode group and zone pair, Tp[5, 5, 1454, 1454] in float32 (for the
    eligibility line's transit test, which times each trip in the period it leaves)."""
    import pandas as pd
    f = CACHE / "trips-by-period.npz"
    src = [MTC / "indivTripData.zip", MTC / "jointTripData.zip"]
    key = ",".join(str(p.stat().st_size) for p in src)
    if f.exists():
        Z = np.load(f)
        if str(Z["key"]) == key:
            return Z["Tp"]
    Tp = np.zeros((len(PERIODS), 5, NZ, NZ), dtype=np.float32)
    grp = np.full(22, -1)
    for m, g in GROUP.items():
        grp[m] = g
    for name in ("indivTripData", "jointTripData"):
        cols = ["orig_taz", "dest_taz", "trip_mode", "sampleRate", "depart_hour"] + (["num_participants"] if name == "jointTripData" else [])
        with zipfile.ZipFile(MTC / f"{name}.zip") as zf, zf.open(f"{name}_3.csv") as fh:
            for ch in pd.read_csv(fh, usecols=cols, chunksize=2_000_000):
                p = period_of_hour(ch.depart_hour.values)
                if (p < 0).any():
                    sys.exit(f"CHECK FAILED: depart_hour outside 0..23 in {name}")
                w = (ch.num_participants.values if name == "jointTripData" else 1.0) / ch.sampleRate.values
                np.add.at(Tp, (p, grp[ch.trip_mode.values], ch.orig_taz.values - 1, ch.dest_taz.values - 1), w.astype(np.float32))
                print(f"  {name} by period: {len(ch):,} rows", file=sys.stderr)
    CACHE.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(f, Tp=Tp, key=key)
    return Tp


def trips():
    """Daily person trips by mode group and zone pair, T[5, 1454, 1454], and the region's person trips by mode code."""
    import pandas as pd
    f = CACHE / "trips.npz"
    src = [MTC / "indivTripData.zip", MTC / "jointTripData.zip"]
    key = ",".join(str(p.stat().st_size) for p in src)
    if f.exists():
        Z = np.load(f)
        if str(Z["key"]) == key:
            return Z["T"], Z["by_mode"], float(Z["rows"])
    T = np.zeros((5, NZ, NZ), dtype=np.float64)
    by_mode = np.zeros(22)
    rows = 0
    grp = np.full(22, -1)
    for m, g in GROUP.items():
        grp[m] = g
    for name in ("indivTripData", "jointTripData"):
        cols = ["orig_taz", "dest_taz", "trip_mode", "sampleRate"] + (["num_participants"] if name == "jointTripData" else [])
        with zipfile.ZipFile(MTC / f"{name}.zip") as zf, zf.open(f"{name}_3.csv") as fh:
            for ch in pd.read_csv(fh, usecols=cols, chunksize=2_000_000):
                rows += len(ch)
                m = ch.trip_mode.values
                check_ok = (m >= 1) & (m <= 21)
                if not check_ok.all():
                    sys.exit(f"CHECK FAILED: trip_mode outside 1..21 in {name}")
                o, d = ch.orig_taz.values, ch.dest_taz.values
                if o.min() < 1 or o.max() > NZ or d.min() < 1 or d.max() > NZ:
                    sys.exit(f"CHECK FAILED: a zone outside 1..{NZ} in {name}")
                w = (ch.num_participants.values if name == "jointTripData" else 1.0) / ch.sampleRate.values
                np.add.at(by_mode, m, w)
                np.add.at(T, (grp[m], o - 1, d - 1), w)
                print(f"  {name}: {rows:,} rows", file=sys.stderr)
    CACHE.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(f, T=T, by_mode=by_mode, rows=rows, key=key)
    return T, by_mode, float(rows)


def skims():
    """AM peak minutes and miles by zone pair, NaN where the skim has no path."""
    import pandas as pd
    f = CACHE / "skims-am.npz"
    src = [SKIMS / "SimpleTimeSkims/SimpleTimeSkims.zip", SKIMS / "SimpleDistanceSkims/SimpleDistanceSkims.zip"]
    key = ",".join(str(p.stat().st_size) for p in src)
    if f.exists():
        Z = np.load(f)
        if str(Z["key"]) == key:
            if "trn_skip" in Z.files:
                return {k: Z[k] for k in Z.files if k != "key"}
    out = {}
    for path, member, cols in ((src[0], "TimeSkimsDatabaseAM.csv", {"da": "car_min", "bike": "bike_min", "wTrnW": "trn_min", "dTrnW": "dtrn_min"}),
                               (src[1], "DistanceSkimsDatabaseAM.csv", {"da": "car_mi", "bike": "bike_mi"})):
        with zipfile.ZipFile(path) as zf, zf.open(member) as fh:
            df = pd.read_csv(io.TextIOWrapper(fh), skipinitialspace=True, usecols=["orig", "dest"] + list(cols))
        check(len(df) == NZ * NZ, f"{member}: {NZ} x {NZ} rows ({len(df):,})")
        df = df.sort_values(["orig", "dest"])
        check((df.orig.values == np.repeat(np.arange(1, NZ + 1), NZ)).all() and (df.dest.values == np.tile(np.arange(1, NZ + 1), NZ)).all(), f"{member}: every zone pair once")
        for c, k in cols.items():
            v = df[c].values.astype(np.float64).reshape(NZ, NZ)
            check(not (v == 0).any() and ((v > 0) | (v == -999)).all(), f"{member} {c}: every value positive or -999")
            out[k] = np.where(v == -999, np.nan, v)
    check(not np.isnan(out["car_min"]).any() and not np.isnan(out["car_mi"]).any(), "the car skim has a path for every pair")
    ok = ~np.isnan(out["bike_min"])
    check((np.isnan(out["bike_mi"]) == ~ok).all(), "bike minutes and miles are missing on the same pairs")
    check(np.abs(out["bike_min"][ok] - out["bike_mi"][ok] / BIKE_MPH * 60).max() < 0.06, "bike minutes are bike miles at 12 mph")
    # The model's bike network has some links in one direction only: the Golden Gate Bridge has a path into SF and
    # none out of it. A bike route runs both ways, so a pair missing one direction takes the other's miles. A pair
    # missing both (every pair across the Bay Bridge) stays missing.
    one_way = int((np.isnan(out["bike_mi"]) & ~np.isnan(out["bike_mi"].T)).sum())
    for k in ("bike_mi", "bike_min"):
        out[k] = np.where(np.isnan(out[k]), out[k].T, out[k])
    check((np.isnan(out["bike_mi"]) == np.isnan(out["bike_mi"].T)).all(), f"a bike path one way is a bike path both ways ({one_way:,} pairs filled from the other direction)")
    # Within a zone the skim has no transit trip at all, which isn't a missing path: those pairs are left out of both
    # the transit median and the no-path share (trn_skip).
    out["trn_skip"] = np.eye(NZ, dtype=bool)
    check(np.isnan(out["trn_min"][out["trn_skip"]]).all(), "the transit skim is empty within every zone")
    CACHE.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(f, key=key, **out)
    return out


def transit_ok():
    """The eligibility line's transit test per MTC period, ok[5, 1454, 1454]: the walk-to-transit skim (`wTrnW`) at
    most TRN_RATIO times the drive-alone skim (`da`) in that period. A pair with no transit path, and every pair within
    one zone (the transit skim is empty there), fails."""
    import pandas as pd
    f = CACHE / f"transit-ok-{TRN_RATIO:g}.npz"
    src = SKIMS / "SimpleTimeSkims/SimpleTimeSkims.zip"
    key = str(src.stat().st_size)
    if f.exists():
        Z = np.load(f)
        if str(Z["key"]) == key:
            return Z["ok"]
    ok = np.zeros((len(PERIODS), NZ, NZ), dtype=bool)
    for k, per in enumerate(PERIODS):
        member = f"TimeSkimsDatabase{per}.csv"
        with zipfile.ZipFile(src) as zf, zf.open(member) as fh:
            df = pd.read_csv(io.TextIOWrapper(fh), skipinitialspace=True, usecols=["orig", "dest", "da", "wTrnW"])
        check(len(df) == NZ * NZ, f"{member}: {NZ} x {NZ} rows")
        df = df.sort_values(["orig", "dest"])
        check((df.orig.values == np.repeat(np.arange(1, NZ + 1), NZ)).all() and (df.dest.values == np.tile(np.arange(1, NZ + 1), NZ)).all(), f"{member}: every zone pair once")
        car = df["da"].values.astype(np.float64).reshape(NZ, NZ)
        trn = df["wTrnW"].values.astype(np.float64).reshape(NZ, NZ)
        del df
        check((car > 0).all(), f"{member} da: a positive drive time for every pair")
        check(not (trn == 0).any() and ((trn > 0) | (trn == -999)).all(), f"{member} wTrnW: every value positive or -999")
        check((np.diag(trn) == -999).all(), f"{member}: the transit skim is empty within every zone")
        ok[k] = (trn > 0) & (trn <= TRN_RATIO * car)
        print(f"  {per}: {ok[k].sum():,} zone pairs pass the transit test", file=sys.stderr)
    CACHE.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(f, ok=ok, key=key)
    return ok


def transit_eligible(Tp, ok):
    """Person trips by mode group and zone pair on the pairs that pass the transit test in the period each trip
    leaves, E[5, 1454, 1454]."""
    E = np.zeros((5, NZ, NZ), dtype=np.float64)
    for k in range(len(PERIODS)):
        for g in range(5):
            E[g] += np.where(ok[k], Tp[k, g], 0).astype(np.float64)
    return E


def memberships(units, routing):
    """Each MTC zone's share in each neighborhood and district, hd[zone, 41 + 1, 11 + 1] (the last index of each axis
    is outside SF), and its region index (0 to 5, or -1 in SF)."""
    Z = np.load(routing)
    for k in ("zone_mtc", "hood_of_taz", "dist_of_taz"):
        check(k in Z.files, f"routing.npz has {k} (through-traffic.py zones stage)")
    zone_mtc, hood, dist = Z["zone_mtc"], Z["hood_of_taz"], Z["dist_of_taz"]
    w = np.zeros(len(zone_mtc))
    for k in range(5):
        od = Z[f"od_{k}"]
        np.add.at(w, od[:, 0].astype(int), od[:, 2])
        np.add.at(w, od[:, 1].astype(int), od[:, 2])
    with open(MTC / "tazData.csv") as fh:
        sd = {int(r["ZONE"]): int(r["SD"]) for r in csv.DictReader(fh)}
    check(len(sd) == NZ, "tazData.csv has 1,454 zones")
    reg_of_sd = {}
    for i, r in enumerate(units["regions"]):
        for s in r["superdistricts"]:
            reg_of_sd[s] = i
    check(sorted(reg_of_sd) == list(range(5, 35)), "the regions take superdistricts 5 to 34 once each")
    hd = np.zeros((NZ, 42, N_DIST + 1))
    region = np.full(NZ, -1)
    n_sf = 0
    for z in range(1, NZ + 1):
        if sd[z] > 4:
            region[z - 1] = reg_of_sd[sd[z]]
            hd[z - 1, 41, N_DIST] = 1
            continue
        ts = np.nonzero(zone_mtc == z)[0]
        check(len(ts) > 0 and (hood[ts] >= 0).all() and (dist[ts] >= 0).all(), f"SF zone {z} has SF-CHAMP zones, each in a neighborhood and a district") if len(ts) == 0 or (hood[ts] < 0).any() or (dist[ts] < 0).any() else None
        ww = w[ts] if w[ts].sum() > 0 else np.ones(len(ts))
        for t, x in zip(ts, ww / ww.sum()):
            hd[z - 1, hood[t], dist[t]] += x
        n_sf += 1
    check(n_sf == 190, f"190 SF zones ({n_sf})")
    check(np.abs(hd.sum(axis=(1, 2)) - 1).max() < 1e-9, "every zone's weights add to 1")
    return hd, region


def wmedian(v, w):
    """Weighted median of v over w > 0, and the share of weight on NaN v. (None, share) when nothing has a value."""
    v, w = v.ravel(), w.ravel()
    on = w > 0
    v, w = v[on], w[on]
    tot = w.sum()
    if tot <= 0:
        return None, None
    ok = ~np.isnan(v)
    miss = float(w[~ok].sum() / tot)
    if not ok.any():
        return None, miss
    v, w = v[ok], w[ok]
    o = np.argsort(v, kind="stable")
    c = np.cumsum(w[o])
    return float(v[o][np.searchsorted(c, c[-1] / 2)]), miss


def r1(x):
    return None if x is None else round(x, 1)


def row(u, P, pairs, S, with_drive, own=False):
    """One output row. P: person trips by mode group. pairs: [(origin weights, destination weights)] whose outer
    products, times the car trips, weight the skims (one for a direction, two for both)."""
    T = S["T"][CAR]
    ws, skip, vals = [], [], {k: [] for k in ("car_min", "car_mi", "trn_min", "dtrn_min", "bike_min", "bike_mi")}
    for wo, wd in pairs:
        io_, id_ = np.nonzero(wo)[0], np.nonzero(wd)[0]
        if not len(io_) or not len(id_):
            continue
        ws.append((T[np.ix_(io_, id_)] * np.outer(wo[io_], wd[id_])).ravel())
        skip.append(S["trn_skip"][np.ix_(io_, id_)].ravel())
        for k in vals:
            vals[k].append(S[k][np.ix_(io_, id_)].ravel())
    if not ws:
        return [u] + [0] * 5 + [None] * 8 + [[0] * 4, [0] * 4, 0]
    w = np.concatenate(ws)
    wt = np.where(np.concatenate(skip), 0.0, w)   # transit: pairs within one zone left out
    # Trips within the area (own): pairs within one zone are left out of every figure, so the car and bike medians
    # are over the same trips as the transit one.
    m = {k: wmedian(np.concatenate(v), wt if own or k in ("trn_min", "dtrn_min") else w) for k, v in vals.items()}
    pc = lambda x: None if x is None else round(100 * x)  # noqa: E731
    return [u] + [int(round(x)) for x in P] + [r1(m["car_min"][0]), r1(m["car_mi"][0]), r1(m["trn_min"][0]), pc(m["trn_min"][1]),
                                              r1(m["dtrn_min"][0]) if with_drive else None, r1(m["bike_min"][0]), r1(m["bike_mi"][0]), pc(m["bike_min"][1])] + \
        eligible(pairs, S, P[CAR])


def eligible(pairs, S, car_total):
    """Bryan's eligibility line (2026-11-20): the trips on the zone pairs that pass
    each test, by mode group, and the car trips the tests are over. Returns
    [[car, transit, bike, walk] on the pairs where walk-to-transit is at most TRN_RATIO x the drive, in the period
     each trip leaves (S["E_trn"], from transit_eligible),
     [car, transit, bike, walk] where the bike path is BIKE_MI miles or less, car trips tested].
    A pair the skim has no path for fails its test, and a pair within one zone fails the transit test (no transit skim
    there) and is tested for bike like any other, in every row, so the car trips tested are the row's car trips."""
    T, E = S["T"], S["E_trn"]
    acc = np.zeros((2, 4))
    base = 0.0
    with np.errstate(invalid="ignore"):
        for wo, wd in pairs:
            io_, id_ = np.nonzero(wo)[0], np.nonzero(wd)[0]
            if not len(io_) or not len(id_):
                continue
            ix = np.ix_(io_, id_)
            ww = np.outer(wo[io_], wd[id_])
            bike_ok = S["bike_mi"][ix] <= BIKE_MI
            base += float((T[CAR][ix] * ww).sum())
            for j, gs in enumerate(((CAR,), (TW, TD), (BIKE,), (WALK,))):
                acc[0, j] += float(sum((E[g][ix] * ww).sum() for g in gs))
                acc[1, j] += float(sum((T[g][ix] * ww)[bike_ok].sum() for g in gs))
    if abs(base - car_total) > 1e-6 * max(1.0, car_total):
        sys.exit(f"CHECK FAILED: the eligibility tests' car trips {base:,.3f} against the row's {car_total:,.3f}")
    for k in range(2):
        if acc[k, 0] > base + 1e-4 * max(1.0, base):
            sys.exit(f"CHECK FAILED: more eligible car trips ({acc[k, 0]:,.3f}) than car trips tested ({base:,.3f})")
    b = int(round(base))
    return [[min(int(round(acc[k, 0])), b)] + [int(round(x)) for x in acc[k, 1:]] for k in range(2)] + [b]


def area_parts(hd, region, G, kind, i):
    """For an area (kind 'h' neighborhood i, 'd' district i): each zone's share inside it, and each zone's share in
    each of the G units and outside the area."""
    R = G - 41
    inA = hd[:, i, :N_DIST].sum(axis=1) if kind == "h" else hd[:, :41, i].sum(axis=1)
    out = np.zeros((NZ, G))
    if kind == "h":
        out[:, :41] = hd[:, :41, :N_DIST].sum(axis=2)
        out[:, i] = 0
    else:
        out[:, :41] = hd[:, :41, :N_DIST].sum(axis=2) - hd[:, :41, i]
    for r in range(R):
        out[region == r, 41 + r] = 1
    return inA, out


def build(S, hd, region, units):
    G = len(units["groups"])
    R = len(units["regions"])
    check(G == 41 + R, "41 neighborhoods and the regions")
    T = S["T"]
    areas = [("h", i, slug(n), n) for i, n in enumerate(units["groups"][:41])] + [("d", i, f"district-{i + 1}", f"District {i + 1}") for i in range(N_DIST)]
    files = {}
    for kind, i, sl, name in areas:
        inA, out = area_parts(hd, region, G, kind, i)
        check(np.abs(inA[:, None] + out.sum(axis=1, keepdims=True) - 1).max() < 1e-9, f"{name}: every zone is in the area or in one unit") if sl in ("sunset-parkside", "district-4") else None
        # P_from[m, u]: trips from unit u to the area; P_to[m, u]: from the area to unit u.
        P_from = np.stack([out.T @ (T[m] @ inA) for m in range(5)])
        P_to = np.stack([(inA @ T[m]) @ out for m in range(5)])
        P_own = np.array([inA @ T[m] @ inA for m in range(5)])
        ends_in = np.array([(T[m] @ inA).sum() + (inA @ T[m]).sum() - 2 * P_own[m] for m in range(5)])
        if abs((P_from + P_to).sum() - ends_in.sum()) > 1e-6 * max(1, ends_in.sum()):
            sys.exit(f"CHECK FAILED: {name}: the units' trips add to the trips with one end in the area")
        o = {"own": row(-1, P_own, [(inA, inA)], S, False, own=True), "from": [], "to": [], "both": []}
        for u in range(G):
            wu = out[:, u]
            reg = u >= 41
            o["from"].append(row(u, P_from[:, u], [(wu, inA)], S, reg))
            o["to"].append(row(u, P_to[:, u], [(inA, wu)], S, False))
            o["both"].append(row(u, P_from[:, u] + P_to[:, u], [(wu, inA), (inA, wu)], S, False))
        for k in ("from", "to", "both"):
            o[k] = [r for r in o[k] if sum(r[1:6]) > 0]
        # The eligibility line: never more car trips than the row's, and the two directions add to Both.
        for r in [o["own"]] + o["from"] + o["to"] + o["both"]:
            if not (r[14][0] <= r[16] <= r[1] + 1 and r[15][0] <= r[16]):
                sys.exit(f"CHECK FAILED: {name}, unit {r[0]}: eligible car trips {r[14][0]}, {r[15][0]} against {r[16]} tested, {r[1]} in the row")
        for t in (14, 15):
            fb = sum(r[t][0] for r in o["from"] + o["to"])
            bb = sum(r[t][0] for r in o["both"])
            if abs(fb - bb) > len(o["both"]) + 1:
                sys.exit(f"CHECK FAILED: {name}: eligible car trips from plus to {fb:,} against both {bb:,}")
        files[f"modes-{sl}.json"] = o
    return files


def published(by_mode, T, region):
    tot = by_mode.sum()
    print(f"person trips a weekday, region: {tot:,.0f}")
    bad = []
    for label, codes, pub in PUBLISHED:
        ours = 100 * by_mode[list(codes)].sum() / tot
        print(f"  {label:26s} ours {ours:5.2f}%   MTC {pub}%")
        if abs(ours - pub) > 1.0:
            bad.append(label)
    check(not bad, f"regional mode shares within a point of MTC's Figures 30 and 31 ({', '.join(bad) or 'all eight'})")
    sf = region < 0
    any_sf = T[:, sf, :].sum(axis=(1, 2)) + T[:, :, sf].sum(axis=(1, 2)) - T[:, sf][:, :, sf].sum(axis=(1, 2))
    within = T[:, sf][:, :, sf].sum(axis=(1, 2))
    one = any_sf - within
    for label, v in (("to, from and within SF", any_sf), ("one end in SF", one), ("within SF", within)):
        s = 100 * v / v.sum()
        print(f"  {label:24s} {v.sum():>11,.0f} trips: car {s[CAR]:.1f}%, transit {s[TW] + s[TD]:.1f}% (on foot {s[TW]:.1f}, by car {s[TD]:.1f}), walk {s[WALK]:.1f}%, bike {s[BIKE]:.1f}%")
    return {"any_sf": any_sf, "one": one, "within": within}


def thresholds(sl, S, hd, region, units):
    """Candidate could-shift tests for one area, to stdout only: nothing here is written to the site."""
    G = len(units["groups"])
    names = units["groups"]
    kind, i = ("d", int(sl.split("-")[1]) - 1) if sl.startswith("district-") else ("h", [slug(n) for n in names[:41]].index(sl))
    inA, out = area_parts(hd, region, G, kind, i)
    T = S["T"]
    anyu = out.sum(axis=1)
    # Every pair with one end in the area and one outside, both directions; times in the trip's own direction.
    W = np.outer(anyu, inA) + np.outer(inA, anyu)
    car, trn, bk, wk = T[CAR] * W, (T[TW] + T[TD]) * W, T[BIKE] * W, T[WALK] * W
    ratio = np.where(S["trn_skip"], np.inf, S["trn_min"] / S["car_min"])
    print(f"{sl}: person trips with one end in the area: car {car.sum():,.0f}, transit {trn.sum():,.0f}, bike {bk.sum():,.0f}, walk {wk.sum():,.0f}")

    def line(label, mask):
        c, t, b, w_ = car[mask].sum(), trn[mask].sum(), bk[mask].sum(), wk[mask].sum()
        allm = c + t + b + w_
        print(f"  {label:44s} car trips {c:>9,.0f} ({100 * c / car.sum():4.1f}% of car trips); on these pairs today transit {100 * t / allm:4.1f}%, bike {100 * b / allm:4.1f}%, car {100 * c / allm:4.1f}%")
    for cut in (1.2, 1.5, 2.0):
        line(f"transit (on foot) at most {cut} x car time", ratio <= cut)
    line("transit over 2.0 x car time", ratio > 2.0)
    line("no walk-to-transit path", np.isnan(ratio))
    for mi in (2, 3, 5, 9.3):
        line(f"bike path at most {mi} miles", S["bike_mi"] <= mi)
    line("bike path over 9.3 miles", S["bike_mi"] > 9.3)
    line("no bike path", np.isnan(S["bike_mi"]))
    line("bike within 5 min of the car", S["bike_min"] - S["car_min"] <= 5)
    line("transit within 15 min of the car", S["trn_min"] - S["car_min"] <= 15)
    print("  by unit (both directions): car trips, share of them with transit <= 1.5 x car, with bike <= 5 miles")
    for u in range(G):
        Wu = np.outer(out[:, u], inA) + np.outer(inA, out[:, u])
        c = T[CAR] * Wu
        if c.sum() < 500:
            continue
        print(f"    {names[u]:32s} {c.sum():>9,.0f}  {100 * c[ratio <= 1.5].sum() / c.sum():5.1f}%  {100 * c[S['bike_mi'] <= 5].sum() / c.sum():5.1f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--published", action="store_true", help="print the totals the source file reports, and stop")
    ap.add_argument("--thresholds", metavar="SLUG", help="print candidate could-shift tests for one area, and stop")
    ap.add_argument("--routing", default=str(RUNS / "routing.npz"), help="routing.npz with the zones stage in it")
    a = ap.parse_args()
    units = json.loads((OUT / "units.json").read_text())
    T, by_mode, rows = trips()
    check(by_mode[0] == 0 and by_mode.sum() > 2e7, f"person trips a weekday {by_mode.sum():,.0f} from {rows:,.0f} rows")
    check(abs(T.sum() - by_mode.sum()) < 1, "the zone table holds every trip")
    hd, region = memberships(units, a.routing)
    published(by_mode, T, region)
    if a.published:
        return
    S = skims()
    S["T"] = T
    Tp = trips_by_period()
    check(abs(float(Tp.sum(dtype=np.float64)) - T.sum()) < 1e-5 * T.sum(), "the trips by period add to the day's trips")
    check(np.abs(Tp.sum(axis=0, dtype=np.float64) - T).max() < 0.05, "every zone pair's trips by period add to its day")
    S["E_trn"] = transit_eligible(Tp, transit_ok())
    del Tp
    if a.thresholds:
        thresholds(a.thresholds, S, hd, region, units)
        return
    files = build(S, hd, region, units)
    check(len(files) == 41 + N_DIST, f"{len(files)} area files")
    n = 0
    for fn in sorted(files):
        n += bool(write_text(OUT / fn, dump(files[fn])))
    sp = files["modes-sunset-parkside.json"]
    names = units["groups"]
    print("Sunset/Parkside, both directions: unit, car, transit on foot, transit by car, bike, walk, car min, car mi, transit min, % no transit, drive-transit min, bike min, bike mi, % no bike", file=sys.stderr)
    for r in sorted(sp["both"], key=lambda r: -sum(r[1:6]))[:12]:
        print("  ", names[r[0]], r[1:], file=sys.stderr)
    print("   own", sp["own"][1:], file=sys.stderr)
    # The eligibility line's figures for the area as a whole, both directions: the worked example posted on thread
    # fi45m48imnoh (1,990 and 33,554 car trips) is what --thresholds prints.
    for t, label in ((14, f"transit at most {TRN_RATIO} x car time"), (15, f"bike path at most {BIKE_MI:g} miles")):
        e = [sum(r[t][j] for r in sp["both"]) for j in range(4)]
        car = sum(r[1] for r in sp["both"])
        print(f"Sunset/Parkside, {label}: {e[0]:,} car trips ({100 * e[0] / car:.1f}%); on them transit {100 * e[1] / sum(e):.0f}%, bike {100 * e[2] / sum(e):.0f}%, car {100 * e[0] / sum(e):.0f}%", file=sys.stderr)
    print(f"wrote {len(files)} files to {OUT} ({n} changed)", file=sys.stderr)


if __name__ == "__main__":
    main()
