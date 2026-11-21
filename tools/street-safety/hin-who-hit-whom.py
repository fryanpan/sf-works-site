#!/usr/bin/env python3
"""Every person severely injured or killed on SF streets in 2022 to 2024, sorted by who hit whom (car occupants alone or with another vehicle, motorcyclists, people walking, people biking or scooting), with each group's causes, crash types, late-night share and share on the 2024 HIN, for Whitepaper Part 1.2 section 6.

    uv run --no-project --with numpy python tools/street-safety/hin-who-hit-whom.py

Reads the same cached DataSF pulls as tools/street-safety/hin-injury-kinds.py (run that first: its points.geojson carries each
person's 2024 HIN flag) and writes scratch/runs/hin-injuries/who-hit-whom.json. One-off analysis behind a notes page;
no page reads it on a schedule, so the incremental-updater rule doesn't apply yet.

THE BASE. DataSF nwes-mmgh (victims, one row per injured person), victim_degree_of_injury 'Severe Injury' or 'Fatal
Injury', collision_datetime 2022-01-01 to 2024-12-31. Each victim row names its own party (party_number_ckey); the
parties table DataSF 8gtc-pjc6 lists every party in the crash, one row per driver, pedestrian, bicyclist, parked
vehicle or other.

A PARTY'S MODE, from party_type and stwd_vehicle_type:
  walk     party_type Pedestrian.
  parked   party_type Parked Vehicle. Not in transport, so it never makes a crash "multi-vehicle" (FARS's rule).
  bike     Bicycle, Electric Bicycle, Motorized Bicycle, Go-ped/ZIP scooter/Motorboard, Electrically Motorized Board.
  moto     Motorcycle, Motor Driven Cycle/Scooter (mopeds), Police Motorcycle.
  other    Misc. Non-Motor Vehicle.
  car      everything else: cars, SUVs, pickups, vans, trucks, buses, paratransit, 'Unknown Hit and Run' and a driver
           whose vehicle is 'Not Stated' (a hit-and-run or unrecorded vehicle is assumed to be a motor vehicle).

THE PERSON'S MODE. victim_role Pedestrian is walk; otherwise the mode of the victim's own party (an occupant of a
parked car is a car occupant). THE GROUP, from the person's mode and the modes of the OTHER parties in the crash:
  car occupant      another car or moto party in the crash -> "with another motor vehicle", else "single vehicle"
                    (fixed object, parked car, overturn, or a bike or pedestrian as the only other party).
  motorcyclist      same split: with a car or another motorcycle, else solo.
  walking           a car or moto party -> "hit by a motor vehicle"; a bike party only -> "hit by a bike or scooter".
  biking/scooting   a car or moto party -> "with a motor vehicle", else "no moving motor vehicle": a fall, another
                    rider, a pedestrian, or a parked car (doorings, pcf 22517, are counted per group).
PAIRING, for the Where in the Intersection panels: counted by the person hurt, the pairing is the set of modes of every
moving party in their crash (parked vehicles left out; a crash's victims all share its pairing). One mode with two or
more parties is "X on X" (car on car); one moving party alone is solo (into an object, a parked car, or a fall; a pedestrian alone is listed apart); two
modes are "X on Y"; three modes are "three or more kinds". Pairings under MERGE_BELOW people go to one Other panel,
listed in the chart's caption. PLACE is hin-injury-kinds.py's own `place` for the person, read from its
points.geojson (that script's rule, not a copy of it); the one person with no coordinates is Other.
LATE NIGHT is 10 pm to 4 am, the hour of collision_time, as in hin-injury-kinds.py. CAUSE is hin-injury-kinds.py's
cause() over vz_pcf_code (SFPD Focus on the Five groups; the code-to-group match is ours). ALCOHOL is any party in the
crash other than a pedestrian with party_sobriety 'Had Been Drinking, Under Influence' (a drinking pedestrian or a
'Not Under Influence' coding does not count; unknown sobriety counts as no).
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections, importlib.util, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
import sfdata

hik = paths.load("hin-injury-kinds.py", "hik")

OUT = os.path.join(ROOT, "scratch", "runs", "hin-injuries")
BIKE = {"Bicycle", "Electric Bicycle", "Motorized Bicycle", "Go-ped, ZIP Electric Scooter, Motorboard", "Electrically Motorized Board"}
MOTO = {"Motorcycle", "Motor Driven Cycle/Scooter", "Moped", "Police Motorcycle"}
GROUPS = [
    "Car occupant, single vehicle",
    "Car occupant, with another motor vehicle",
    "Motorcyclist, solo",
    "Motorcyclist, with another motor vehicle",
    "Walking, hit by a motor vehicle",
    "Biking or scooting, with a motor vehicle",
    "Biking or scooting, no moving motor vehicle",
    "Other",
]


def mode(p):
    t, v = p.get("party_type"), p.get("stwd_vehicle_type") or ""
    if t == "Pedestrian":
        return "walk"
    if t == "Parked Vehicle":
        return "parked"
    if v in BIKE:
        return "bike"
    if v in MOTO:
        return "moto"
    if v == "Misc. Non-Motor Vehicle":
        return "other"
    return "car"


def group(me, others):
    motor = bool(others & {"car", "moto"})
    if me in ("car", "parked"):
        return "Car occupant, " + ("with another motor vehicle" if motor else "single vehicle")
    if me == "moto":
        return "Motorcyclist, " + ("with another motor vehicle" if motor else "solo")
    if me == "walk":
        return "Walking, hit by a motor vehicle" if motor else "Other"
    if me == "bike":
        return "Biking or scooting, " + ("with a motor vehicle" if motor else "no moving motor vehicle")
    return "Other"


def main():
    V = sfdata.fetch("nwes-mmgh", where="victim_degree_of_injury in ('Severe Injury','Fatal Injury') and "
                     "collision_datetime between '2022-01-01T00:00:00' and '2024-12-31T23:59:59'", floor=800)
    rows = {}
    for v in V.rows:
        rows[(v["case_id_pkey"], v["victim_id"])] = v
    rows = [rows[k] for k in sorted(rows)]
    ids = sorted({r["case_id_pkey"] for r in rows})
    # Same select and where as hin-injury-kinds.py, so the cached pull is shared.
    P = sfdata.fetch("8gtc-pjc6", select="case_id_pkey,party_number_ckey,party_type,at_fault,street_of_travel,move_pre_acc,"
                     "stwd_vehicle_type,party_sobriety,party_age", where="case_id_pkey in (%s)" % ",".join("'%s'" % i for i in ids))
    parties = collections.defaultdict(dict)
    for p in P.rows:
        parties[p["case_id_pkey"]][p["party_number_ckey"]] = p
    pts = json.load(open(os.path.join(OUT, "points.geojson")))
    hin = {(f["properties"]["case"], f["properties"]["victim"]): f["properties"]["hin2024"] for f in pts["features"]}
    place = {(f["properties"]["case"], f["properties"]["victim"]): f["properties"]["place"] for f in pts["features"]}

    out, unlinked = [], 0
    for r in rows:
        ps = parties[r["case_id_pkey"]]
        own = ps.get(r["party_number_ckey"])
        if own is None:
            unlinked += 1
        me = "walk" if r.get("victim_role") == "Pedestrian" else mode(own) if own else mode(r)
        others = {mode(p) for k, p in ps.items() if k != r["party_number_ckey"]} - {"parked"}
        g = group(me, others)
        if g == "Other":
            sub = ("Walking, hit by a bike or scooter" if me == "walk" and "bike" in others
                   else "Walking, no other party recorded" if me == "walk" else "Other party type")
        else:
            sub = None
        h = hik.hour(r)
        moving = [mode(p) for p in ps.values() if mode(p) != "parked"]
        kinds = sorted(set(moving), key=NAME_ORDER.index)
        if moving == ["walk"]:
            pair = "Pedestrian, no vehicle recorded"
        elif len(moving) == 1:
            pair = "Solo"
        elif len(kinds) == 1:
            pair = "%s on %s" % (NAME[kinds[0]].capitalize(), NAME[kinds[0]])
        elif len(kinds) == 2:
            pair = "%s on %s" % (NAME[kinds[0]].capitalize(), NAME[kinds[1]])
        else:
            pair = "Three or more kinds"
        out.append({"pair": pair, "place": PLACE.get(place.get((r["case_id_pkey"], r["victim_id"])), "Other"), "group": g, "sub": sub, "killed": r["victim_degree_of_injury"] == "Fatal Injury",
                    "late": h is not None and (h >= 22 or h < 4), "hour_known": h is not None,
                    "cause": hik.cause(r.get("vz_pcf_code")), "type": r.get("type_of_collision") or "Not Stated",
                    "alcohol": any(p.get("party_type") != "Pedestrian" and (p.get("party_sobriety") or "").startswith("Had Been Drinking, Under")
                                   for p in ps.values()),
                    "dooring": (r.get("vz_pcf_code") or "").startswith("22517"),
                    "parked": any(p.get("party_type") == "Parked Vehicle" for p in ps.values()),
                    "hin2024": hin.get((r["case_id_pkey"], r["victim_id"]))})

    # ---- Checks.
    n, killed = len(out), sum(o["killed"] for o in out)
    assert 900 <= n <= 950 and 100 <= killed <= 115, (n, killed)
    assert unlinked == 0, unlinked                      # every victim's own party is in the parties table
    assert len(parties) == len(ids), (len(parties), len(ids))   # every case has its parties
    assert all(o["group"] in GROUPS for o in out)
    placed = [o for o in out if o["hin2024"] is not None]
    assert len(placed) >= n - 5, len(placed)

    def pct(a, b):
        return round(100.0 * a / b, 1) if b else None

    G = []
    for g in GROUPS:
        b = [o for o in out if o["group"] == g]
        k = sum(o["killed"] for o in b)
        pl = [o for o in b if o["hin2024"] is not None]
        tk = [o for o in b if o["hour_known"]]
        G.append({"group": g, "people": len(b), "killed": k, "severe": len(b) - k,
                  "pct_of_people": pct(len(b), n), "pct_of_killed": pct(k, killed),
                  "on_hin2024": sum(o["hin2024"] for o in pl), "pct_on_hin2024": pct(sum(o["hin2024"] for o in pl), len(pl)),
                  "late_night": sum(o["late"] for o in tk), "pct_late_night": pct(sum(o["late"] for o in tk), len(tk)),
                  "alcohol": sum(o["alcohol"] for o in b), "pct_alcohol": pct(sum(o["alcohol"] for o in b), len(b)),
                  "parked_vehicle_involved": sum(o["parked"] for o in b), "dooring": sum(o["dooring"] for o in b),
                  "causes": collections.Counter(o["cause"] for o in b).most_common(5),
                  "crash_types": collections.Counter(o["type"] for o in b).most_common(5),
                  "other_breakdown": dict(collections.Counter(o["sub"] for o in b if o["sub"]))})
    assert sum(x["people"] for x in G) == n and sum(x["killed"] for x in G) == killed
    allpl = [o for o in out if o["hin2024"] is not None]
    alltk = [o for o in out if o["hour_known"]]
    S = {"sources": {"victims": V.tag, "parties": P.tag, "hin_flag": "scratch/runs/hin-injuries/points.geojson (hin-injury-kinds.py)"},
         "people": n, "killed": killed, "placed": len(allpl),
         "all": {"pct_on_hin2024": pct(sum(o["hin2024"] for o in allpl), len(allpl)),
                 "pct_late_night": pct(sum(o["late"] for o in alltk), len(alltk)),
                 "pct_alcohol": pct(sum(o["alcohol"] for o in out), n)},
         "groups": G}
    with open(os.path.join(OUT, "who-hit-whom.json"), "w") as f:
        json.dump(S, f, indent=1, sort_keys=True); f.write("\n")
    write_chart(G, n, killed)
    write_place_chart(out)
    w = max(len(g) for g in GROUPS)
    print("%-*s %6s %6s %6s %6s %6s %6s %6s" % (w, "group", "people", "killed", "%ppl", "%kill", "%HIN", "%late", "%alc"))
    for x in G:
        print("%-*s %6d %6d %6.1f %6.1f %6.1f %6.1f %6.1f" % (w, x["group"], x["people"], x["killed"], x["pct_of_people"],
              x["pct_of_killed"], x["pct_on_hin2024"] or 0, x["pct_late_night"] or 0, x["pct_alcohol"]))
        print("   causes:", x["causes"]); print("   types: ", x["crash_types"])
        if x["other_breakdown"]:
            print("   other: ", x["other_breakdown"])
        print("   dooring:", x["dooring"], "alcohol (driver/rider under influence):", x["alcohol"])
        if x["parked_vehicle_involved"]:
            print("   parked vehicle involved:", x["parked_vehicle_involved"])
    print("all:", S["all"], "people", n, "killed", killed)


NAME = {"car": "car", "moto": "motorcycle", "bike": "bike", "walk": "pedestrian", "other": "other vehicle"}
NAME_ORDER = ["car", "moto", "bike", "walk", "other"]
MERGE_BELOW = 10
PLACE = {"main x main": "Corner, two main streets", "main x residential": "Corner, main and local",
         "residential x residential": "Corner, two local streets", "main midblock": "Midblock, main street",
         "residential midblock": "Midblock, local street"}
PLACES = ["Corner, main and local", "Corner, two main streets", "Midblock, main street",
          "Corner, two local streets", "Midblock, local street", "Other"]


def write_place_chart(out):
    """Small multiples: one panel per pairing (largest first), place on y, each bar labelled people (killed)."""
    n = len(out)
    size = collections.Counter(o["pair"] for o in out)
    small = sorted(k for k, v in size.items() if v < MERGE_BELOW)
    merged = {k: ("Other pairings" if k in small else k) for k in size}
    for o in out:
        o["panel"] = merged[o["pair"]]
    psize = collections.Counter(o["panel"] for o in out)
    panels = sorted(psize, key=lambda k: (k == "Other pairings", -psize[k], k))
    flab = {k: "%s\n%d people" % (k, psize[k]) for k in panels}
    c = collections.Counter((o["panel"], o["place"]) for o in out)
    ck = collections.Counter((o["panel"], o["place"]) for o in out if o["killed"])
    bars = []
    for k in panels:
        for pl in PLACES:
            v = c[(k, pl)]
            bars.append({"f": flab[k], "d": pl, "v": v, "t": ("%d (%d killed)" % (v, ck[(k, pl)]) if ck[(k, pl)] else str(v)) if v else ""})
    top = max(b["v"] for b in bars)
    caption = "Other pairings: " + ", ".join("%s %d" % (k.lower() if k != "Solo" else k, size[k]) for k in sorted(small, key=lambda k: -size[k]))
    chart = {
        "title": "Cars Hitting People Walking Lead at Every Kind of Corner, and Solo Crashes Lead Midblock",
        "data": {"bars": bars},
        "marks": [{"mark": "barX", "data": "bars", "options": {"y": "d", "fy": "f", "x": "v", "fill": "#4269d0", "fillOpacity": 0.85}},
                  {"mark": "text", "data": "bars", "options": {"y": "d", "fy": "f", "x": "v", "text": "t", "dx": 5, "textAnchor": "start", "fontSize": 10, "fill": "#333"}}],
        "options": {"width": 620, "height": 92 * len(panels) + 50, "marginLeft": 150, "marginRight": 130, "marginTop": 10, "marginBottom": 40,
                    "x": {"domain": [0, round(top * 1.3)], "label": "People severely injured or killed (%d), counted by the person hurt" % n,
                          "labelAnchor": "center", "labelArrow": False, "grid": True, "tickSize": 0},
                    "y": {"domain": PLACES, "label": None, "tickSize": 0},
                    "fy": {"domain": [flab[k] for k in panels], "label": None, "axis": "right", "tickSize": 0}},
        "caption": caption}
    j = lambda o: json.dumps(o, sort_keys=False)
    with open(os.path.join(OUT, "who-hit-whom-place-chart.mdx"), "w") as f:
        f.write("<PlotChart\n  title=%s\n  data={%s}\n  marks={%s}\n  options={%s}\n/>\n\n%s.\n" % (
            j(chart["title"]), j(chart["data"]), j(chart["marks"]), j(chart["options"]), caption))
    with open(os.path.join(OUT, "who-hit-whom-place-chart.json"), "w") as f:
        json.dump(chart, f, indent=1); f.write("\n")
    print("pairings:", dict(size.most_common()))
    for k in panels:
        print("  %-26s %4d killed %3d  " % (k, psize[k], sum(o["killed"] for o in out if o["panel"] == k)) +
              ", ".join("%s %d" % (pl, c[(k, pl)]) for pl in PLACES if c[(k, pl)]))
    mm = [o for o in out if o["place"] == "Corner, two main streets"]
    print("  main x main corner:", dict(collections.Counter(o["pair"] for o in mm).most_common()), len(mm))


LABEL = {"Car occupant, with another motor vehicle": "Car occupant, with another vehicle",
         "Motorcyclist, with another motor vehicle": "Motorcyclist, with another vehicle",
         "Walking, hit by a motor vehicle": "Walking, hit by a vehicle",
         "Biking or scooting, with a motor vehicle": "Biking or scooting, with a vehicle",
         "Biking or scooting, no moving motor vehicle": "Biking or scooting, no moving vehicle"}


def write_chart(G, n, killed):
    """The <PlotChart> block for the notes doc: people by group, deaths stacked first, each bar labelled."""
    lab = lambda g: LABEL.get(g, g) if g != "Other" else "Other (mostly walking, hit by a bike)"
    bars, labels = [], []
    for x in G:
        bars.append({"d": lab(x["group"]), "s": "Killed", "v": x["killed"]})
        bars.append({"d": lab(x["group"]), "s": "Severely injured", "v": x["severe"]})
        labels.append({"d": lab(x["group"]), "v": x["people"], "t": "%d (%d killed)" % (x["people"], x["killed"])})
    top = max(x["people"] for x in G)
    chart = {
        "title": "People in Cars and on Motorcycles Are 342 of 923 Severely Hurt or Killed, and 36 of 108 Killed",
        "data": {"bars": bars, "labels": labels},
        "marks": [{"mark": "barX", "data": "bars", "options": {"y": "d", "x": "v", "fill": "s"}},
                  {"mark": "text", "data": "labels", "options": {"y": "d", "x": "v", "text": "t", "dx": 5, "textAnchor": "start", "fontSize": 11, "fill": "#333"}}],
        "options": {"width": 620, "height": 330, "marginLeft": 235, "marginRight": 95, "marginTop": 10, "marginBottom": 36,
                    "color": {"legend": True, "domain": ["Killed", "Severely injured"], "range": ["#2f7d76", "#a9cfc9"]},
                    "x": {"domain": [0, top], "label": "People (%d, %d killed)" % (n, killed), "labelAnchor": "center",
                          "labelArrow": False, "grid": True, "tickSize": 0},
                    "y": {"domain": [lab(x["group"]) for x in G], "label": None, "tickSize": 0}}}
    j = lambda o: json.dumps(o, sort_keys=False)
    mdx = "<PlotChart\n  title=%s\n  data={%s}\n  marks={%s}\n  options={%s}\n/>\n" % (
        j(chart["title"]), j(chart["data"]), j(chart["marks"]), j(chart["options"]))
    with open(os.path.join(OUT, "who-hit-whom-chart.mdx"), "w") as f:
        f.write(mdx)
    with open(os.path.join(OUT, "who-hit-whom-chart.json"), "w") as f:
        json.dump(chart, f, indent=1); f.write("\n")


if __name__ == "__main__":
    main()
