#!/usr/bin/env python3
"""Why the count of people severely hurt or killed in SF traffic went up: ten hypotheses tested against the police
crash reports, for the "Why More People Are Severely Hurt" section of the injury page
(site/src/injury-page.mjs).

    ~/.venvs/sf-works-geo/bin/python tools/street-safety/injury-severe-why.py      # writes site/data/injury-severe-why.json

Bryan, 2026-10-21, on the yearly trend chart: "Can you do a deep dive into why severe injuries and deaths are
increasing? What's the cause? Come up with ten different hypotheses then see if data confirms or denies."

STATUS UNDER THE INCREMENTAL-UPDATER RULE. A build step like injury-map.py, whose street snapping it reuses: it reads
the crash reads lib/street_safety_reads.py holds and step street-safety-crashes keeps current (nwes-mmgh
victims, 8gtc-pjc6 parties, dau3-4s8f fatalities), 3psu-pn9h centerlines through injury-map.Streets, and the tracked HIN extract, and has no --update of its own. It sits
in pipeline/transportation-update.py right after injury-map. Its output dates every figure from the read dates under
"source", never the wall clock, and is sorted, so a run on unchanged data rewrites nothing.

WHAT IS COUNTED. One row of nwes-mmgh is one person hurt (case_id_pkey + victim_id). "Severe" is the officer's
"Severe Injury" or "Fatal Injury", the page's own rule; "killed" is "Fatal Injury", which the dataset takes from the
Medical Examiner's cases under the Vision Zero fatality protocol. Years are calendar years of collision_datetime.
The comparison is BEFORE = 2015 to 2019 against AFTER = 2021 to 2025, each a yearly average, with 2020 left out as the
COVID year; EARLY = 2005 to 2014 is the decade before the December 2014 SFPD memo on head injuries. 2026 is partial and
is left out of every figure here.

GROUPS (each hypothesis's split):
  mode       the person hurt: walking (victim_role Pedestrian), on a bike or e-bike, on a motorcycle or moped, on a scooter
             or board (CHP "Go-ped, ZIP Electric Scooter, Motorboard" or "Electrically Motorized Board"), or in a car or
             truck (every other driver and passenger). The vehicle is the victim row's own stwd_vehicle_type.
  speed      the crash's vz_pcf_code is a speed section (injury-map.cause() == "speed").
  impaired   any party in the crash "Had Been Drinking, Under Influence" or "Under Drug Influence", or the primary
             collision factor is 23152 or 23153 (driving under the influence).
  dark       lighting starts "Dark" (with or without street lights).
  older      victim_age 65 or more.
  unknownDriver  a crash with a Driver party whose age the report leaves blank, our stand-in for a hit-and-run, since
             the public tables carry no hit-and-run field. Against Vision Zero SF's 2024 report it gives 5 fatal
             crashes in 2024 against the report's 5 hit-and-run collisions, and 5 in 2023 against its 7.
  ramp       primary_rd or secondary_rd names a ramp ("HWY 101 S OFF RAMP"); the data leaves out crashes on the freeway itself.
  hin        within 60 ft of SFMTA's 2022 High Injury Network (injury-map.ON_FT), main roads are centerline classes 2 to 4
             at the snapped point (injury-map's rule).
  vehicle    for people walking or biking, the biggest vehicle a driver was in, from the party table (a parked car
             or a vehicle of unknown type doesn't count): a bus or truck
             (any bus, truck, transit, paratransit, emergency or commercial type), an SUV, pickup or van, a car, or a
             motorcycle. SFPD's coding of "Sport Utility Vehicle" grows from 0% of drivers before 2013 to 21% in 2022,
             a jump no change in the fleet makes in a year [inference — mine], so SUVs against cars is compared only inside
             2022 to 2025.

THE RATING CHECK. SFDPH's trauma registry at Zuckerberg San Francisco General is a second count of severe injuries
that doesn't depend on the officer's call. Its yearly totals (HOSPITAL below, "ZSFG Severe", which includes critical)
are typed from SFDPH's Severe Traffic Injury Trends 2015-2022, Figure 14, read 2026-10-21, along with its police
series, which our counts reproduce. The independent death count is Vision Zero SF's 2024 End of Year Traffic Fatality
Report, Figure 1 (VZ_DEATHS), read 2026-10-21, against DataSF dau3-4s8f and nwes-mmgh.

A difference in counts between two five-year windows is tested as Poisson: z = (a - b) / sqrt(a + b) on the five-year
totals, and "clear" means |z| >= 1.96. [inference — mine, the method]
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections, importlib.util, json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
OUT = os.path.join(ROOT, "site", "data", "injury-severe-why.json")
import numpy as np
from lib import street_safety_reads

IM = paths.load("injury-map.py")

BEFORE, AFTER, EARLY = range(2015, 2020), range(2021, 2026), range(2005, 2015)
LAST_FULL = 2025
SEVERE = {"Severe Injury", "Fatal Injury"}
MINOR = {"Other Visible Injury", "Complaint of Pain"}
# SFDPH, Severe Traffic Injury Trends 2015-2022 (Dec 2024), Figure 14: ZSFG severe (critical included) and SFPD severe.
HOSPITAL = {2011: 492, 2012: 498, 2013: 517, 2014: 471, 2015: 578, 2016: 570, 2017: 574, 2018: 592, 2019: 533, 2020: 512, 2021: 577, 2022: 535}
HOSPITAL_POLICE = {2011: 198, 2012: 204, 2013: 201, 2014: 205, 2015: 230, 2016: 278, 2017: 261, 2018: 283, 2019: 307, 2020: 226, 2021: 271, 2022: 282}
# Vision Zero SF, 2024 End of Year Traffic Fatality Report (July 2025), Figure 1, N per year.
VZ_DEATHS = {2005: 27, 2006: 32, 2007: 41, 2008: 27, 2009: 30, 2010: 24, 2011: 28, 2012: 29, 2013: 34, 2014: 31, 2015: 31, 2016: 32,
             2017: 20, 2018: 23, 2019: 29, 2020: 30, 2021: 27, 2022: 39, 2023: 26, 2024: 43}

BIKE = {"Bicycle", "Electric Bicycle", "Motorized Bicycle"}
MOTO = {"Motorcycle", "Motor Driven Cycle/Scooter", "Moped"}
SCOOT = {"Go-ped, ZIP Electric Scooter, Motorboard", "Electrically Motorized Board"}
HEAVY_WORDS = ("Bus", "Truck", "Transit", "Paratransit", "Emergency", "Commercial", "Tractor", "Semi", "Ambulance", "Fire", "Garbage")
SUVPU = {"Sport Utility Vehicle", "Pickup or Panel Truck", "Minivan", "Van"}
VSIZE = [("heavy", 4), ("suv", 3), ("car", 2), ("moto", 1)]


def vclass(t):
    """A motor vehicle's size group from stwd_vehicle_type, or None for a non-motor party."""
    if not t or t in ("Pedestrian", "Not Stated", "Misc. Non-Motor Vehicle", "Unknown", "Unknown Hit and Run") or t in BIKE or t in SCOOT:
        return None
    if t in SUVPU:
        return "suv"     # "Pickup or Panel Truck" is a pickup or van, not a heavy truck
    if t in MOTO:
        return "moto"
    if t == "Passenger Car with Trailer":
        return "car"     # before the HEAVY_WORDS test, which would catch "Trailer"
    if any(w in t for w in HEAVY_WORDS):
        return "heavy"
    return "car"


def mode_of(v):
    r, t = v.get("victim_role"), v.get("stwd_vehicle_type")
    if r == "Pedestrian":
        return "walk"
    if r == "Bicyclist" or t in BIKE:
        return "bike"
    if t in MOTO:
        return "moto"
    if t in SCOOT:
        return "scoot"
    return "car"


def z(a, b):
    """Poisson z for two counts over equal spans."""
    return (a - b) / math.sqrt(a + b) if a + b else 0.0


def load():
    V = street_safety_reads.read("severe-why-victims")
    P = street_safety_reads.read("severe-why-parties")
    F = street_safety_reads.read("severe-why-deaths")
    return V, P, F


def main():
    V, P, F = load()
    # One party row per (case, party number); the table repeats a few.
    parties = collections.defaultdict(dict)
    for p in P.rows:
        parties[p["case_id_pkey"]][p.get("party_number_ckey")] = p
    impaired_case, unknown_case, biggest = set(), set(), {}
    UNKNOWN_SOBER = {None, "", "Not Stated", "Impairment Not Known", "Impairment Unknown"}
    for case, ps in parties.items():
        best = None
        for p in ps.values():
            if p.get("party_sobriety") == "Had Been Drinking, Under Influence" or p.get("party_drug_physical") == "Under Drug Influence":
                impaired_case.add(case)
            if p.get("party_type") == "Driver" and not p.get("party_age"):
                unknown_case.add(case)
            # Only a vehicle someone was driving: a parked car (a door, or a cyclist riding into it) isn't "hit by".
            c = vclass(p.get("stwd_vehicle_type")) if p.get("party_type") == "Driver" else None
            if c and (best is None or dict(VSIZE)[c] > dict(VSIZE)[best]):
                best = c
        biggest[case] = best

    S = IM.Streets()
    hin_file = json.load(open(os.path.join(ROOT, "data", "extract", "access", "hin-2022.json")))
    H = np.array([(a[0], a[1], b[0], b[1]) for r in hin_file["records"] for a, b in
                  zip([IM.xy(*q) for q in r["pts"]], [IM.xy(*q) for q in r["pts"]][1:])])

    rows, seen = [], set()
    for v in V.rows:
        deg, dts = v.get("victim_degree_of_injury"), v.get("collision_datetime") or ""
        if deg in (None, "No Injury") or len(dts) < 4 or not dts[:4].isdigit():
            continue
        y = int(dts[:4])
        if y > LAST_FULL:
            continue
        key = (v["case_id_pkey"], v.get("victim_id"))
        assert key not in seen, "victim row repeated: %r" % (key,)
        seen.add(key)
        try:
            age = int(float(v.get("victim_age") or ""))
        except ValueError:
            age = None
        code = v.get("vz_pcf_code") or ""
        case = v["case_id_pkey"]
        try:
            lo, la = float(v["tb_longitude"]), float(v["tb_latitude"])
            pt = IM.xy(lo, la) if (37.6 < la < 37.85 and -122.53 < lo < -122.35) else None
        except (KeyError, TypeError, ValueError):
            pt = None
        rows.append({"y": y, "sev": deg in SEVERE, "fat": deg == "Fatal Injury", "minor": deg in MINOR, "mode": mode_of(v),
                     "speed": IM.cause(code) == "speed", "nocause": IM.cause(code) == "unknown", "impaired": case in impaired_case or code.startswith(("23152", "23153")),
                     "dark": (v.get("lighting") or "").startswith("Dark"), "older": age is not None and age >= 65,
                     "unknownDriver": case in unknown_case, "big": biggest.get(case), "pt": pt,
                     "ix": (v.get("intersection") or "").startswith("Intersection"),
                     "ramp": any("RAMP" in (v.get(k) or "").upper() for k in ("primary_rd", "secondary_rd"))})

    # Where: HIN and main road at the snapped point, as injury-map does.
    pts = [r for r in rows if r["pt"] is not None]
    px, py = np.array([r["pt"][0] for r in pts]), np.array([r["pt"][1] for r in pts])
    hd = np.full(len(pts), 1e9)
    for row in H:
        np.minimum(hd, IM.seg_dist(px, py, *row), out=hd)
    RANK = {"1": 6, "2": 5, "3": 4, "4": 3, "6": 2, "5": 1, "0": 0}
    for i, r in enumerate(pts):
        r["hin"] = bool(hd[i] <= IM.ON_FT)
        n = S.nearest(px[i], py[i])
        if n is None or n[1] > IM.SNAP_FT:
            r["cls"] = None
            continue
        cnn, _, node, dnode = n
        r["cls"] = (max((S.seg[c]["cls"] for c in S.at_node[node]), key=lambda k: RANK[k])
                    if (r["ix"] or dnode <= IM.NODE_FT) else S.seg[cnn]["cls"])
    for r in rows:
        r.setdefault("hin", None); r.setdefault("cls", None)
        r["main"] = None if r["cls"] is None else r["cls"] in IM.MAIN

    # Yearly series.
    years = list(range(2005, LAST_FULL + 1))
    yr = {y: {"hurt": 0, "severe": 0, "fatal": 0, "minor": 0, "fatalDark": 0} for y in years}
    for r in rows:
        o = yr[r["y"]]; o["hurt"] += 1; o["severe"] += r["sev"]; o["fatal"] += r["fat"]; o["minor"] += r["minor"]; o["fatalDark"] += r["fat"] and r["dark"]
    fat_ds = collections.Counter()
    for f in F.rows:
        y = (f.get("collision_datetime") or f.get("collision_year") or "")[:4]
        if y.isdigit() and int(y) <= LAST_FULL:
            fat_ds[int(y)] += 1

    def tot(span, key, pred=lambda r: True):
        return sum(1 for r in rows if r["y"] in span and r[key] and pred(r))

    def split(name, pred, label):
        """Severe and killed in BEFORE and AFTER for one group, with the severe share of everyone hurt in it."""
        b, a = tot(BEFORE, "sev", pred), tot(AFTER, "sev", pred)
        hb = sum(1 for r in rows if r["y"] in BEFORE and pred(r)); ha = sum(1 for r in rows if r["y"] in AFTER and pred(r))
        fb, fa = tot(BEFORE, "fat", pred), tot(AFTER, "fat", pred)
        return {"k": name, "label": label, "sevBefore": b / 5, "sevAfter": a / 5, "z": round(z(a, b), 2), "fatZ": round(z(fa, fb), 2),
                "fatBefore": fb / 5, "fatAfter": fa / 5, "fatEarly": tot(EARLY, "fat", pred) / 10,
                "hurtBefore": hb / 5, "hurtAfter": ha / 5,
                "shareBefore": b / hb if hb else None, "shareAfter": a / ha if ha else None,
                "sevEarly": tot(EARLY, "sev", pred) / 10}

    modes = [split(k, (lambda k: lambda r: r["mode"] == k)(k), lab) for k, lab in
             (("walk", "Walking"), ("bike", "On a bike or e-bike"), ("car", "In a car or truck"),
              ("moto", "On a motorcycle or moped"), ("scoot", "On a scooter or board"))]
    flags = {k: split(k, (lambda k: lambda r: bool(r[k]))(k), lab) for k, lab in
             (("speed", "Unsafe speed named as the cause"), ("impaired", "A party under the influence"),
              ("dark", "After dark"), ("older", "People 65 and older"), ("unknownDriver", "Driver unidentified"),
              ("hin", "On the High Injury Network"), ("main", "On main roads"), ("ramp", "At a freeway ramp"))}
    flags["darkWalk"] = split("darkWalk", lambda r: r["dark"] and r["mode"] == "walk", "Walking, after dark")
    everyone = split("all", lambda r: True, "Everyone")

    # Vehicle size, for people walking or biking, within 2022 to 2025 when SUV coding is steady.
    vs = {}
    for k in ("heavy", "suv", "car", "moto", None):
        sub = [r for r in rows if 2022 <= r["y"] <= LAST_FULL and r["mode"] in ("walk", "bike") and r["big"] == k]
        vs[k or "none"] = {"hurt": len(sub), "severe": sum(r["sev"] for r in sub), "fatal": sum(r["fat"] for r in sub)}
    # SUV share of driver parties by year (the coding check).
    dc = collections.defaultdict(collections.Counter)
    for ps in parties.values():
        for p in ps.values():
            y = (p.get("collision_datetime") or "")[:4]
            if p.get("party_type") == "Driver" and y.isdigit() and 2005 <= int(y) <= LAST_FULL:
                dc[int(y)]["all"] += 1; dc[int(y)]["suv"] += p.get("stwd_vehicle_type") == "Sport Utility Vehicle"
    suv_coded = {y: round(dc[y]["suv"] / dc[y]["all"], 4) for y in years if dc[y]["all"]}

    # The 2015 step by quarter.
    qs = collections.Counter(); qa = collections.Counter()
    for v in V.rows:
        deg, dts = v.get("victim_degree_of_injury"), v.get("collision_datetime") or ""
        if deg in (None, "No Injury") or len(dts) < 7:
            continue
        if "2013" <= dts[:4] <= "2017":
            q = "%sQ%d" % (dts[:4], (int(dts[5:7]) - 1) // 3 + 1)
            qa[q] += 1; qs[q] += deg in SEVERE

    fatal_case_year = {}
    for r_ in V.rows:
        if r_.get("victim_degree_of_injury") == "Fatal Injury" and (r_.get("collision_datetime") or "")[:4].isdigit():
            fatal_case_year[r_["case_id_pkey"]] = int(r_["collision_datetime"][:4])
    sober = {}
    for nm, span in (("early", EARLY), ("before", BEFORE), ("after", AFTER)):
        ds = [p for c, y in fatal_case_year.items() if y in span for p in parties.get(c, {}).values() if p.get("party_type") == "Driver"]
        sober[nm] = {"drivers": len(ds), "unknown": sum(1 for p in ds if p.get("party_sobriety") in UNKNOWN_SOBER)}
    nocause = {nm: sum(1 for r in rows if r["y"] in span and r["fat"] and r["nocause"]) for nm, span in (("early", EARLY), ("before", BEFORE), ("after", AFTER))}

    out = {
        "source": {"victimsFetched": V.fetched_on.isoformat(), "partiesFetched": P.fetched_on.isoformat(),
                   "fatalFetched": F.fetched_on.isoformat(), "centerlinesFetched": S.fetched, "hinFetched": hin_file.get("fetched_on"),
                   "hospitalRead": "2026-10-21", "vzRead": "2026-10-21", "victims": len(rows)},
        "periods": {"before": [BEFORE[0], BEFORE[-1]], "after": [AFTER[0], AFTER[-1]], "early": [EARLY[0], EARLY[-1]]},
        "yearly": {str(y): yr[y] for y in years},
        "deaths": {"nwes": {str(y): yr[y]["fatal"] for y in years}, "fatalTable": {str(y): fat_ds[y] for y in years if fat_ds[y]},
                   "vz": {str(y): n for y, n in VZ_DEATHS.items()}},
        "hospital": {"zsfg": {str(y): n for y, n in HOSPITAL.items()}, "police": {str(y): n for y, n in HOSPITAL_POLICE.items()},
                     "ours": {str(y): yr[y]["severe"] - yr[y]["fatal"] for y in HOSPITAL}},
        "quarters": {q: {"hurt": qa[q], "severe": qs[q]} for q in sorted(qa)},
        "everyone": everyone, "modes": modes, "flags": flags,
        "vehicle": vs, "soberUnknownFatal": sober, "deathsNoCause": nocause, "suvCoded": {str(y): s for y, s in suv_coded.items()},
    }
    # Quality checks: a short read or a broken join stops the step before the file is written.
    assert len(rows) > 75000, "too few victims: %d" % len(rows)
    assert all(yr[y]["hurt"] > 2000 for y in years), "a year with under 2,000 people hurt"
    assert all(sum(tot(span, "sev", (lambda k: lambda r: r["mode"] == k)(m["k"])) for m in modes) == tot(span, "sev") for span in (BEFORE, AFTER)), "modes don't sum"
    assert sum(1 for r in rows if r["cls"] is not None) > 0.98 * len([r for r in rows if r["pt"]]), "snapping dropped points"
    for y in range(2014, 2025):
        assert abs(yr[y]["fatal"] - VZ_DEATHS.get(y, yr[y]["fatal"])) <= 3, "deaths %d far from Vision Zero's count" % y
    for y in (2016, 2017, 2018):
        assert abs(yr[y]["severe"] - yr[y]["fatal"] - HOSPITAL_POLICE[y]) <= 2, "police severe %d far from SFDPH's table" % y
    def rnd(o):
        if isinstance(o, float):
            return round(o, 4)
        if isinstance(o, dict):
            return {k: rnd(x) for k, x in o.items()}
        if isinstance(o, list):
            return [rnd(x) for x in o]
        return o
    text = json.dumps(rnd(out), indent=1, sort_keys=True) + "\n"
    if not os.path.exists(OUT) or open(OUT).read() != text:
        open(OUT, "w").write(text)
        print("wrote", OUT, len(rows), "victims")
    else:
        print("unchanged", OUT)


if __name__ == "__main__":
    main()
