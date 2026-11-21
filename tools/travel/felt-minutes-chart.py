"""Felt minutes for one 3-mile SF trip by walk, bike, car and Muni at a bus every 5, 10 and 20 minutes: clock minutes per trip component, times the door-to-door weights, written as data and a <PlotChart> block for the whitepaper's Frameworks section.

Inputs:
  research/school-trips-2026-10/google-check/results-drive-{dropoff,pickup}.jsonl
      Google Routes API door-to-door drive times for SF home-to-school trips, queried 2026-10-08 for departures on 2026-10-13 at the morning and
      afternoon bells. Trips of 2 to 4 miles (Google's route length) are pooled into one speed with traffic (gMin)
      and one without (gStaticMin). Minutes over the no-traffic time count as driving in congestion.
  site/data/muni.json  windows["365"].speedByHour: Muni bus speed by hour over the last 365 days (511 stop
      observations, scripts/muni-ewt/trip_analyze.py: buses only, every day type), averaged as miles over hours
      across the local hours those Google trips departed, so bus and car share a time of day.
  Constants below, each with its source, for weights (research/whitepaper-2026-11/
  2026-11-13-door-to-door-time-resources.md, central column), walk to and from the stop, bike speed and the
  assumptions (parking search, walks to and from a parked car, bike unlock, walking speed, riding weights).
Outputs: data/extract/felt-minutes/felt-minutes.json and data/extract/felt-minutes/felt-minutes-chart.mdx.
Usage: python3 -I tools/travel/felt-minutes-chart.py
Idempotent: no run stamp; the same inputs write the same bytes.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import json, os, sys

ROOT = paths.ROOT
OUT = os.path.join(ROOT, "data", "extract", "felt-minutes")
O10 = ["#4269d0", "#efb118", "#ff725c", "#6cc5b0"]
STYLE = {"fontFamily": "inherit", "color": "#59626f"}

MILES = 3.0
HEADWAYS = (5, 10, 20)

# Weights: the resources note's central column. Wardman 2026's own means are walk 1.67, wait 1.72, transfer 1.65;
# the note takes 1.75 for both, which the review supports ("1.75 or 1.50"), and the chart uses the note's 1.75.
# Bike: Borjesson and Eliasson, Stockholm cycle commuters (CTS 2011:22; Transportation Research A 46(4), 2012), Table 3:
# a minute biking in mixed traffic against a minute on the next-best mode about 1.9, on a separated bike path about 1.3.
W = {"walk": 1.75, "wait": 1.75, "park": 1.60, "ride": 1.0, "drive_free": 1.0, "drive_cong": 1.33, "bike_traffic": 1.9,
     "bike_path": 1.3,
     "unlock": 1.75}  # unlock: no weight in the note; we treat it as out-of-vehicle time like walking (assumption)

# Muni walk to and from the stop: median minutes on the AM local Muni paths of our ActivitySim skims (SF zones,
# Muni GTFS, walking at 3 mph), research/notes/travel-model-2026-10/2026-11-06-asim-part4b-skims.md, row S3.
WALK_TO_STOP, WALK_FROM_STOP = 5.4, 4.1
# Bike: Google's median bike speed on 100 SF home-to-school trips, Routes API queried 2026-10-08,
# research/notes/school-trips-2026-10/2026-10-08-google-drive-bike-check.md. Includes hills.
BIKE_MPH = 9.0
# Assumptions, no source opened: shown as such on the chart.
WALK_MPH = 3.0          # the same walking speed our transit skims use
PARK_SEARCH = 3.0       # with the 2 min walk from the car, the low end of Liao et al. (2020)'s 5 to 10 min for parking
WALK_FROM_CAR = 2.0     # about a tenth of a mile at 3 mph
WALK_TO_CAR = 1.0       # a car parked on the block or in a garage at home
UNLOCK = 1.0            # each end: unlock at the start, lock at the end
GOOGLE = os.path.join(ROOT, "research", "school-trips-2026-10", "google-check")
MI = 1609.344


def google_drive():
    """Pooled speed with and without traffic over Google's 2 to 4 mile drives, and the local hours they departed."""
    rows = []
    for bell in ("dropoff", "pickup"):
        rows += [json.loads(l) for l in open(os.path.join(GOOGLE, f"results-drive-{bell}.jsonl")) if l.strip()]
    keep = [r for r in rows if r.get("gMeters") and r.get("gMin") and r.get("gStaticMin") and 2 <= r["gMeters"] / MI <= 4]
    if len(keep) < 50:
        sys.exit(f"felt-minutes: only {len(keep)} Google drives of 2 to 4 miles")
    if len({(r["row"], r["bell"]) for r in keep}) != len(keep):
        sys.exit("felt-minutes: duplicate Google trips")
    mi = sum(r["gMeters"] for r in keep) / MI
    traffic = mi / (sum(r["gMin"] for r in keep) / 60)
    free = mi / (sum(r["gStaticMin"] for r in keep) / 60)
    # departures are UTC; 2026-10-13 is daylight time in SF, UTC-7
    hours = sorted({(int(r["depart"][11:13]) - 7) % 24 for r in keep})
    days = sorted({r["depart"][:10] for r in keep})
    return {"n": len(keep), "mph": traffic, "free_mph": free, "hours": hours, "days": days}


def inputs():
    g = google_drive()
    muni = json.load(open(os.path.join(ROOT, "site", "data", "muni.json")))
    byh = {r["hour"]: r["mph"] for r in muni["windows"]["365"]["speedByHour"]}
    miss = [h for h in g["hours"] if byh.get(h) is None]
    if miss:
        sys.exit(f"felt-minutes: no Muni speed for hours {miss}")
    # miles over hours across the hours, each hour weighted alike: the harmonic mean of the hourly speeds
    bus = len(g["hours"]) / sum(1 / byh[h] for h in g["hours"])
    for name, v, lo, hi in (("bus", bus, 5, 15), ("car", g["mph"], 8, 30), ("car free", g["free_mph"], 8, 35)):
        if not lo <= v <= hi:
            sys.exit(f"felt-minutes: {name} speed {v:.2f} mph out of range")
    if g["free_mph"] < g["mph"]:
        sys.exit("felt-minutes: Google's no-traffic speed is below its traffic speed")
    return {"bus_mph": round(bus, 2), "bus_hours": g["hours"], "bus_window": "last 365 days, site/data/muni.json",
            "car_mph": round(g["mph"], 2), "car_free_mph": round(g["free_mph"], 2), "car_trips": g["n"],
            "car_days": g["days"]}


def seg(mode, comp, group, clock, weight, note):
    return {"mode": mode, "comp": comp, "group": group, "clock": round(clock, 2), "weight": weight,
            "felt": round(clock * weight, 2), "note": note}


def build(x):
    mins = lambda mph: MILES / mph * 60
    S = []
    drive = mins(x["car_mph"])
    free = mins(x["car_free_mph"])
    S += [seg("Car", "Driving", "Moving", drive, round((free * W["drive_free"] + (drive - free) * W["drive_cong"]) / drive, 3),
              f"{drive:.1f} min at {x['car_mph']} mph, Google's SF door-to-door speed with traffic; {drive - free:.1f} of them are traffic delay, weighted {W['drive_cong']}")]
    S.insert(0, seg("Car", "Walk to the car", "Walking", WALK_TO_CAR, W["walk"], "Assumed"))
    S += [seg("Car", "Parking search", "Parking or unlocking", PARK_SEARCH, W["park"], "Assumed"),
          seg("Car", "Walk from the parked car", "Walking", WALK_FROM_CAR, W["walk"], "Assumed")]
    for m, w in (("Bike in traffic", W["bike_traffic"]), ("Bike on a path", W["bike_path"])):
        S += [seg(m, "Unlock", "Parking or unlocking", UNLOCK, W["unlock"], "Assumed"),
              seg(m, "Riding", "Moving", mins(BIKE_MPH), w, f"{BIKE_MPH} mph"),
              seg(m, "Lock", "Parking or unlocking", UNLOCK, W["unlock"], "Assumed")]
    for h in HEADWAYS:
        m = f"Muni every {h} min"
        S += [seg(m, "Walk to the stop", "Walking", WALK_TO_STOP, W["walk"], "Median in our transit model"),
              seg(m, "Wait", "Waiting", h / 2, W["wait"], f"Half of a {h} min headway"),
              seg(m, "On board", "Moving", mins(x["bus_mph"]), W["ride"], f"{x['bus_mph']} mph, Muni's citywide bus speed at the hours the car trips ran"),
              seg(m, "Walk from the stop", "Walking", WALK_FROM_STOP, W["walk"], "Median in our transit model")]
    S.append(seg("Walk", "Walking", "Walking", mins(WALK_MPH), W["walk"], f"{WALK_MPH} mph, assumed"))
    return S


def chart(S):
    modes = list(dict.fromkeys(s["mode"] for s in S))
    tot = {m: {"clock": sum(s["clock"] for s in S if s["mode"] == m), "felt": sum(s["felt"] for s in S if s["mode"] == m)}
           for m in modes}
    order = sorted(modes, key=lambda m: tot[m]["felt"])
    bars, segl = [], []
    for m in order:
        x0 = 0.0
        for s in (s for s in S if s["mode"] == m):
            x1 = x0 + s["felt"]
            assumed = " (assumed)" if s["note"].startswith("Assumed") or "assumed" in s["note"] else ""
            bars.append({"m": m, "x1": round(x0, 2), "x2": round(x1, 2), "g": s["group"],
                         "t": f"{m}: {s['comp']}{assumed}, {s['clock']:.1f} clock min x {s['weight']} = {s['felt']:.1f} felt min." + ("" if s["note"] == "Assumed" else f" {s['note']}")})
            if s["felt"] >= 8:
                segl.append({"m": m, "x": round((x0 + x1) / 2, 2), "lab": f"{s['felt']:.0f}",
                             "c": "#ffffff" if s["group"] == "Moving" else "#15181c"})
            x0 = x1
    ends = [{"m": m, "x": round(tot[m]["felt"], 2), "c1": round(tot[m]["clock"] - 0.3, 2), "c2": round(tot[m]["clock"] + 0.3, 2),
             "lab": f"{tot[m]['felt']:.0f} felt, {tot[m]['clock']:.0f} clock"} for m in order]
    groups = ["Moving", "Walking", "Waiting", "Parking or unlocking"]
    data = {"b": bars, "s": segl, "e": ends}
    marks = [
        {"mark": "barX", "data": "b", "options": {"y": "m", "x1": "x1", "x2": "x2", "fill": "g", "stroke": "#ffffff",
                                                   "strokeWidth": 1, "title": "t"}},
        {"mark": "text", "data": "s", "options": {"y": "m", "x": "x", "text": "lab", "fill": "c", "fontSize": 11}},
        # clock-minutes tick: a narrow barX, since the board's renderer is only known to draw barX with x1/x2
        {"mark": "barX", "data": "e", "options": {"y": "m", "x1": "c1", "x2": "c2", "fill": "#15181c",
                                                   "insetTop": -3, "insetBottom": -3}},
        {"mark": "text", "data": "e", "options": {"y": "m", "x": "x", "text": "lab", "dx": 5, "textAnchor": "start",
                                                   "fontSize": 11, "fill": "#15181c"}},
    ]
    opts = {"style": STYLE, "width": 360, "height": 300, "marginLeft": 108, "marginRight": 92, "marginTop": 8,
            "marginBottom": 40, "fontSize": 12,
            "x": {"label": "Felt minutes, door to door. Black tick: clock minutes", "labelAnchor": "left",
                  "labelArrow": False, "domain": [0, 110], "ticks": [0, 30, 60, 90], "grid": True, "tickSize": 0},
            "y": {"label": None, "domain": order, "tickSize": 0},
            "color": {"legend": True, "domain": groups, "range": O10}}
    j = lambda o: json.dumps(o, ensure_ascii=False)
    gap = round(tot["Muni every 5 min"]["felt"]) - round(tot["Car"]["felt"])
    title = f"Even With a Bus Every 5 Minutes, a 3-Mile Muni Trip Feels {gap} Minutes Longer Than Driving"
    block = (f'<PlotChart\n  title="{title}"\n  data={{{j(data)}}}\n  marks={{{j(marks)}}}\n  options={{{j(opts)}}}\n/>\n')
    return title, block, tot


def main():
    x = inputs()
    S = build(x)
    title, block, tot = chart(S)
    os.makedirs(OUT, exist_ok=True)
    rec = {"miles": MILES, "inputs": x, "weights": W,
           "constants": {"walk_to_car_min": WALK_TO_CAR, "walk_to_stop_min": WALK_TO_STOP, "walk_from_stop_min": WALK_FROM_STOP, "bike_mph": BIKE_MPH,
                         "walk_mph": WALK_MPH, "park_search_min": PARK_SEARCH, "walk_from_car_min": WALK_FROM_CAR,
                         "unlock_min_each_end": UNLOCK},
           "segments": S,
           "totals": {m: {k: round(v, 1) for k, v in t.items()} for m, t in tot.items()}}
    with open(os.path.join(OUT, "felt-minutes.json"), "w") as f:
        json.dump(rec, f, indent=1, sort_keys=True)
        f.write("\n")
    with open(os.path.join(OUT, "felt-minutes-chart.mdx"), "w") as f:
        f.write(block)
    for m, t in sorted(tot.items(), key=lambda kv: kv[1]["felt"]):
        print(f"{m:24s} clock {t['clock']:5.1f}  felt {t['felt']:5.1f}")


if __name__ == "__main__":
    main()
