#!/usr/bin/env python3
"""How small and how unstable a "top 40 worst locations" list is: share of severe and fatal injuries at the 40 worst places, churn of the list across 3-year windows back to 2007, and regression to the mean at each window's top 40, for Whitepaper Part 1.2.

    uv run --no-project --with numpy python tools/street-safety/hin-top40-churn.py

Writes scratch/runs/hin-top40/summary.json (every count below). One-off analysis behind a notes page; no page reads it
on a schedule, so the incremental-updater rule doesn't apply yet.

THE BASE. DataSF nwes-mmgh (police crash reports, one row per injured person, 2005 on), victim_degree_of_injury
'Severe Injury' or 'Fatal Injury', counted by collision_datetime year. One row is one person
(research/sources/datasf-traffic-crashes.md, whose published total, 283 severe in 2018, is re-checked here).

THE LOCATION UNIT. An intersection crash (intersection = 'Intersection <= 20ft') goes to its node, cnn_intrsctn_fkey.
Every other crash ('Midblock > 20ft', 'Intersection Rear End <= 150ft') goes to its block, cnn_sgmt_fkey, and falls back
to the node when the report has no block. These are the report's own keys on the city's centerline (DataSF 3psu-pn9h),
so the unit is the same in every year and covers every street, on the HIN or not. Each person counts once.

RANKING. Locations are ranked by people severely injured or killed in the window, ties broken by deaths, then by key.
The report also says how many locations tie at the 40th place's count, because a tie makes the list arbitrary.

WINDOWS. Six 3-year windows ending with 2022-24, the base of the rest of the page: 2007-09, 2010-12, 2013-15 (the data
window of the 2017 HIN), 2016-18, 2019-21, 2022-24. Also the 5-year windows of the 2022 HIN (2017-21) and the 2024 HIN
(2020-24), for the churn question asked of HIN editions. 2025-01 to 2026-08 is the partial follow-up for 2022-24.

REGRESSION TO THE MEAN. For each window's top 40, people hurt at those same places in that window and in the next
3-year window, against the citywide change between the two windows (Hauer, Observational Before-After Studies in Road
Safety, 1997; Hauer et al., TRR 1784, 2002). The "expected" next count is the top 40's count scaled by the citywide
change: what would happen if the top 40 simply followed the city. The gap is regression to the mean plus anything done
at those places; the data can't split the two.

ON THE HIN. For the share chart, within 60 ft of the 2024 HIN centerline, the rule tools/street-safety/hin-injury-kinds.py uses.

A STEP TO KNOW. An SFPD memo of December 2014 told officers to class head injuries as severe, which SFDPH says raised
police severe counts from 2015 on (research/sources/datasf-traffic-crashes.md). Comparing each top 40 with the citywide
change in the same pair of windows absorbs a citywide step like that.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections, importlib.util, json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
import sfdata

OUT = os.path.join(ROOT, "scratch", "runs", "hin-top40")
WINDOWS = [(2007, 2009), (2010, 2012), (2013, 2015), (2016, 2018), (2019, 2021), (2022, 2024)]
HIN_WINDOWS = {"2017 HIN": (2013, 2015), "2022 HIN": (2017, 2021), "2024 HIN": (2020, 2024)}
CURRENT = (2022, 2024)
FOLLOW = ("2025-01-01", "2026-08-31")
RADIUS_FT = 150
SHUFFLES = 200


def load_kinds():
    m = paths.load("hin-injury-kinds.py", "hin_kinds")
    return m


def loc(v):
    ixf = v.get("intersection") or ""
    node, seg = v.get("cnn_intrsctn_fkey"), v.get("cnn_sgmt_fkey")
    if ixf.startswith("Intersection <=") and node:
        return "node:%d" % int(float(node))
    if seg:
        return "block:%d" % int(float(seg))
    if node:
        return "node:%d" % int(float(node))
    return None


def wname(w):
    return "%d-%02d" % (w[0], w[1] % 100)


DARK, LIGHT = "#2f7d76", "#9cc7c1"   # --seq-3 and a lighter step of the same ramp


def plot(title, data, marks, options):
    j = lambda o: json.dumps(o, ensure_ascii=False)
    return "<PlotChart\n  title=%s\n  data={%s}\n  marks={%s}\n  options={%s}\n/>\n" % (j(title), j(data), j(marks), j(options))


def pct(a, b):
    return "%d%%" % round(100.0 * a / b)


def charts(S):
    """The three <PlotChart> blocks for the notes page, in its existing style (620 wide, teal, every mark labelled)."""
    s = S["share_2022_24"]
    n, k = s["all"]["people"], s["all"]["killed"]
    rows = []
    for g, d in (("Worst 40 places", s["top40"]), ("Worst 100 places", s["top100"]), ("Whole 2024 HIN", s["hin2024"])):
        tot = d.get("placed", n)
        rows.append({"d": "%s: people hurt" % g, "s": "People severely injured or killed", "v": round(100.0 * d["people"] / tot, 1),
                     "t": "%d of %d (%s)" % (d["people"], tot, pct(d["people"], tot))})
        rows.append({"d": "%s: deaths" % g, "s": "Deaths", "v": round(100.0 * d["killed"] / k, 1),
                     "t": "%d of %d (%s)" % (d["killed"], k, pct(d["killed"], k))})
    dom = [r["d"] for r in rows]
    c1 = plot("The Worst 40 Places Hold 14% of People Severely Hurt or Killed, 2022 to 2024", {"bars": rows},
              [{"mark": "barX", "data": "bars", "options": {"y": "d", "x": "v", "fill": "s", "fillOpacity": 0.9}},
               {"mark": "text", "data": "bars", "options": {"y": "d", "x": "v", "text": "t", "dx": 6, "textAnchor": "start", "fontSize": 11, "fill": "#333"}}],
              {"width": 620, "height": 250, "marginLeft": 200, "marginRight": 110, "marginTop": 30, "marginBottom": 36,
               "color": {"domain": ["People severely injured or killed", "Deaths"], "range": [DARK, LIGHT], "legend": True},
               "x": {"domain": [0, 100], "label": "Share of the citywide total (%)", "labelAnchor": "center", "labelArrow": False, "grid": True, "tickSize": 0},
               "y": {"domain": dom, "label": None, "tickSize": 0}})
    ch = S["churn"]["current_top40_in_window_top40"]
    hin = {"2013-15": "2013-15 (2017 HIN data)"}
    bars = [{"w": hin.get(w, w), "v": v, "t": "%d of 40" % v} for w, v in ch.items() if w != "2022-24"]
    c2 = plot("Almost None of Today's Worst 40 Were on Earlier Lists", {"bars": bars},
              [{"mark": "barY", "data": "bars", "options": {"x": "w", "y": "v", "fill": DARK, "fillOpacity": 0.9}},
               {"mark": "text", "data": "bars", "options": {"x": "w", "y": "v", "text": "t", "dy": -8, "fontSize": 11, "fill": "#333"}}],
              {"width": 620, "height": 240, "marginLeft": 40, "marginRight": 10, "marginTop": 24, "marginBottom": 44,
               "x": {"domain": [b["w"] for b in bars], "label": "Earlier 3-year window", "labelAnchor": "center", "labelArrow": False, "tickSize": 0},
               "y": {"domain": [0, 40], "label": "Of the 2022-24 worst 40, how many were in that window's worst 40", "grid": True, "tickSize": 0}})
    b4 = [{"d": "Worst 40 of %s" % r["selected"], "s": "In the 3 years they were picked", "v": r["before"], "t": str(r["before"])} for r in S["rtm"]]
    af = [{"d": "Worst 40 of %s" % r["selected"], "s": "In the next 3 years", "v": r["after"], "t": str(r["after"])} for r in S["rtm"]]
    c3 = plot("The Worst 40 Fall by Four Fifths in the Next Three Years", {"before": b4, "after": af},
              [{"mark": "barX", "data": "before", "options": {"y": "d", "x": "v", "fill": "s"}},
               {"mark": "barX", "data": "after", "options": {"y": "d", "x": "v", "fill": "s", "insetTop": 5, "insetBottom": 5}},
               {"mark": "text", "data": "before", "options": {"y": "d", "x": "v", "text": "t", "dx": 6, "textAnchor": "start", "fontSize": 11, "fill": "#333"}},
               {"mark": "text", "data": "after", "options": {"y": "d", "x": "v", "text": "t", "dx": 5, "textAnchor": "start", "fontSize": 11, "fontWeight": 600, "fill": "#1d4f4a"}}],
              {"width": 620, "height": 250, "marginLeft": 150, "marginRight": 40, "marginTop": 30, "marginBottom": 36,
               "color": {"domain": ["In the 3 years they were picked", "In the next 3 years"], "range": [LIGHT, DARK], "legend": True},
               "x": {"domain": [0, 130], "label": "People severely injured or killed at those 40 places", "labelAnchor": "center", "labelArrow": False, "grid": True, "tickSize": 0},
               "y": {"domain": [r["d"] for r in b4], "label": None, "tickSize": 0}})
    return "\n".join([c1, c2, c3])


def main():
    os.makedirs(OUT, exist_ok=True)
    V = sfdata.fetch("nwes-mmgh", select="case_id_pkey,victim_id,victim_degree_of_injury,collision_datetime,intersection,"
                     "cnn_intrsctn_fkey,cnn_sgmt_fkey,tb_latitude,tb_longitude",
                     where="victim_degree_of_injury in ('Severe Injury','Fatal Injury')", floor=5000)
    seen, people = set(), []
    for v in V.rows:
        k = (v["case_id_pkey"], v["victim_id"])
        assert k not in seen, k
        seen.add(k)
        people.append({"date": v["collision_datetime"][:10], "year": int(v["collision_datetime"][:4]),
                       "killed": v["victim_degree_of_injury"] == "Fatal Injury", "loc": loc(v), "ixf": v.get("intersection") or "",
                       "lon": float(v["tb_longitude"]) if v.get("tb_longitude") else None,
                       "lat": float(v["tb_latitude"]) if v.get("tb_latitude") else None})
    people.sort(key=lambda p: (p["date"], p["loc"] or "", p["killed"]))
    S = {"source": V.tag}

    # Published total (dataset-intake): SFDPH's Severe Injury Trends 2011-2018, Appendix A, Table A: 283 severe in 2018.
    sev = collections.Counter(p["year"] for p in people if not p["killed"])
    assert sev[2018] == 283 and sev[2017] == 261 and sev[2016] == 278, (sev[2016], sev[2017], sev[2018])
    S["published_total_check"] = {"severe_2016": sev[2016], "severe_2017": sev[2017], "severe_2018": sev[2018], "matches_sfdph": True}
    S["by_year"] = {y: {"severe_or_fatal": sum(1 for p in people if p["year"] == y), "killed": sum(1 for p in people if p["year"] == y and p["killed"])}
                    for y in sorted({p["year"] for p in people})}
    S["unplaced"] = {y: sum(1 for p in people if p["year"] == y and p["loc"] is None) for y in sorted({p["year"] for p in people})}
    kind = lambda p: (p["loc"] or "none:").split(":")[0]
    S["unit_mix"] = dict(sorted(collections.Counter("%s|%s" % (kind(p), p["ixf"]) for p in people).items()))

    def in_window(p, w):
        return w[0] <= p["year"] <= w[1]

    def counts(w):
        c, k = collections.Counter(), collections.Counter()
        for p in people:
            if in_window(p, w) and p["loc"]:
                c[p["loc"]] += 1
                k[p["loc"]] += p["killed"]
        return c, k

    def ranked(w):
        c, k = counts(w)
        return sorted(c, key=lambda x: (-c[x], -k[x], x)), c, k

    def topn(w, n=40):
        return ranked(w)[0][:n]

    # 1. Share at the top 40 and top 100 in 2022-24, against the HIN as a whole.
    base = [p for p in people if in_window(p, CURRENT)]
    n_all, n_k = len(base), sum(p["killed"] for p in base)
    assert n_all == 923 and n_k == 108, (n_all, n_k)
    order, c, k = ranked(CURRENT)
    share = {}
    for n in (40, 100):
        top = order[:n]
        cut = c[top[-1]]
        share["top%d" % n] = {"people": sum(c[x] for x in top), "killed": sum(k[x] for x in top), "cutoff": cut,
                              "tied_at_cutoff": sum(1 for x in c if c[x] == cut), "above_cutoff": sum(1 for x in c if c[x] > cut),
                              "nodes": sum(1 for x in top if x.startswith("node")), "blocks": sum(1 for x in top if x.startswith("block"))}
    hk = load_kinds()
    recs = json.load(open(os.path.join(ROOT, "data", "extract", "access", "hin-2024.json")))["records"]
    L = hk.Lines([([hk.xy(*q) for q in r["pts"]], {"id": r["id"]}) for r in recs])
    placed = [p for p in base if p["lon"] is not None]
    on = [p for p in placed if L.nearest(*hk.xy(p["lon"], p["lat"]))[1] <= hk.ON_FT]
    share["hin2024"] = {"people": len(on), "killed": sum(p["killed"] for p in on), "placed": len(placed),
                        "placed_killed": sum(p["killed"] for p in placed)}
    rest = [x for x in order[40:]]
    share["rest"] = {"people": sum(c[x] for x in rest), "killed": sum(k[x] for x in rest), "locations": len(rest),
                     "locations_with_one": sum(1 for x in rest if c[x] == 1), "unplaced": sum(1 for p in base if not p["loc"])}
    share["all"] = {"people": n_all, "killed": n_k, "locations_with_any": len(c)}
    share["top10"] = [[x, c[x], k[x]] for x in order[:10]]
    S["share_2022_24"] = share

    # 2. Churn: how many of one window's top 40 were in another's.
    tops = {wname(w): set(topn(w)) for w in WINDOWS}
    cur = tops[wname(CURRENT)]
    S["churn"] = {"current_top40_in_window_top40": {wname(w): len(cur & tops[wname(w)]) for w in WINDOWS},
                  "consecutive": {"%s->%s" % (wname(a), wname(b)): len(tops[wname(a)] & tops[wname(b)]) for a, b in zip(WINDOWS, WINDOWS[1:])},
                  "current_top40_in_hin_window_top40": {h: len(cur & set(topn(w))) for h, w in HIN_WINDOWS.items()},
                  "hin_windows_pairwise": {"2017 HIN->2022 HIN": len(set(topn(HIN_WINDOWS["2017 HIN"])) & set(topn(HIN_WINDOWS["2022 HIN"]))),
                                           "2022 HIN->2024 HIN": len(set(topn(HIN_WINDOWS["2022 HIN"])) & set(topn(HIN_WINDOWS["2024 HIN"])))}}
    # Tie-inclusive check: of the current top 40, how many had at least the 40th place's count in the earlier window.
    tie = {}
    for w in WINDOWS[:-1]:
        o, cw, _ = ranked(w)
        cut = cw[o[39]]
        tie[wname(w)] = {"cutoff": cut, "current_top40_at_or_above_cutoff": sum(1 for x in cur if cw[x] >= cut),
                         "current_top40_with_none": sum(1 for x in cur if cw[x] == 0)}
    S["churn"]["tie_inclusive"] = tie
    S["churn"]["current_top40_in_any_earlier_top40"] = len(cur & set().union(*[tops[wname(w)] for w in WINDOWS[:-1]]))

    # Key check: a key retired from the centerline would make one place look like two and inflate churn. Every top-40
    # key of every window should still be on the city's centerline (DataSF 3psu-pn9h, active or not).
    C = sfdata.fetch("3psu-pn9h", select="cnn,f_node_cnn,t_node_cnn,active", floor=15000)
    blocks = {int(float(r["cnn"])) for r in C.rows if r.get("cnn")}
    nodes = {int(float(r[f])) for r in C.rows for f in ("f_node_cnn", "t_node_cnn") if r.get(f)}
    known = lambda x: int(x.split(":")[1]) in (nodes if x.startswith("node") else blocks)
    S["key_check"] = {"centerlines": C.tag}
    for w in WINDOWS:
        cw, _ = counts(w)
        S["key_check"][wname(w)] = {"top40_known": sum(1 for x in tops[wname(w)] if known(x)),
                                    "people_at_known_keys_pct": round(100.0 * sum(v for x, v in cw.items() if known(x)) / sum(cw.values()), 1)}

    # 3. Regression to the mean: each window's top 40, that window vs the next.
    city = {wname(w): sum(1 for p in people if in_window(p, w)) for w in WINDOWS}
    rtm = []
    for a, b in zip(WINDOWS, WINDOWS[1:]):
        ta = topn(a)
        ca, _ = counts(a)
        cb, _ = counts(b)
        before, after = sum(ca[x] for x in ta), sum(cb[x] for x in ta)
        ratio = city[wname(b)] / city[wname(a)]
        rtm.append({"selected": wname(a), "next": wname(b), "before": before, "after": after,
                    "expected_if_followed_city": round(before * ratio, 1), "city_before": city[wname(a)], "city_after": city[wname(b)],
                    "top40_change_pct": round(100.0 * (after - before) / before, 1), "city_change_pct": round(100.0 * (ratio - 1), 1),
                    "places_with_none_next": sum(1 for x in ta if cb[x] == 0)})
    S["rtm"] = rtm
    # Robustness: 91 places tie at 2 in 2022-24, so the last places in a top 40 are picked by the tie-break. Rerun the
    # before/after on only the places strictly above each window's cutoff, where no tie-break is involved.
    rob = []
    for a, b in zip(WINDOWS, WINDOWS[1:]):
        o, ca, _ = ranked(a)
        cb, _ = counts(b)
        cut = ca[o[39]]
        sel = [x for x in o if ca[x] > cut]
        rob.append({"selected": wname(a), "next": wname(b), "places": len(sel), "min_count": cut + 1,
                    "before": sum(ca[x] for x in sel), "after": sum(cb[x] for x in sel)})
    S["rtm_above_cutoff"] = rob
    # And the 2022-24 share with ties broken by key alone, not by deaths, so deaths don't pick the last ten places.
    o2 = sorted(c, key=lambda x: (-c[x], x))[:40]
    S["share_2022_24"]["top40_key_tiebreak"] = {"people": sum(c[x] for x in o2), "killed": sum(k[x] for x in o2)}
    above = [x for x in order if c[x] > share["top40"]["cutoff"]]
    S["share_2022_24"]["above_cutoff"] = {"places": len(above), "people": sum(c[x] for x in above), "killed": sum(k[x] for x in above)}
    # Robustness to the key: count by distance instead. Each selected place is the mean point of its people in the
    # selection window; before and after are everyone within RADIUS_FT of it, so a geocoder that moved a crash to the
    # next node or block can't make the drop.
    pts = {}
    for p in people:
        if p["lon"] is not None:
            pts.setdefault(p["year"], []).append(hk.xy(p["lon"], p["lat"]))
    def near(w, cx, cy):
        return sum(1 for y in range(w[0], w[1] + 1) for (x2, y2) in pts.get(y, []) if (x2 - cx) ** 2 + (y2 - cy) ** 2 <= RADIUS_FT ** 2)
    rad = []
    for a, b in zip(WINDOWS, WINDOWS[1:]):
        bef = aft = 0
        for x in topn(a):
            P = [hk.xy(p["lon"], p["lat"]) for p in people if in_window(p, a) and p["loc"] == x and p["lon"] is not None]
            if not P:
                continue
            cx, cy = sum(q[0] for q in P) / len(P), sum(q[1] for q in P) / len(P)
            bef += near(a, cx, cy); aft += near(b, cx, cy)
        rad.append({"selected": wname(a), "next": wname(b), "before": bef, "after": aft})
    S["rtm_radius_%dft" % RADIUS_FT] = rad
    # What chance alone predicts: shuffle the crash year among people 2007-2024, keeping each person's place, and redo
    # the before/after for each pair of windows. If the observed fall matches the shuffled one, the data shows a fall
    # no bigger than regression to the mean, with nothing left over to credit to treatment. Seeded, so reruns match.
    import random
    rng = random.Random(0)
    pool = [p for p in people if WINDOWS[0][0] <= p["year"] <= WINDOWS[-1][1] and p["loc"]]
    years = [p["year"] for p in pool]
    drops = collections.defaultdict(list)
    for _ in range(SHUFFLES):
        rng.shuffle(years)
        byw = collections.defaultdict(collections.Counter)
        for p, y in zip(pool, years):
            for w in WINDOWS:
                if w[0] <= y <= w[1]:
                    byw[w][p["loc"]] += 1
        for a, b in zip(WINDOWS, WINDOWS[1:]):
            ta = sorted(byw[a], key=lambda x: (-byw[a][x], x))[:40]
            bef, aft = sum(byw[a][x] for x in ta), sum(byw[b][x] for x in ta)
            drops[wname(a)].append(100.0 * (bef - aft) / bef)
    S["rtm_shuffle"] = {"shuffles": SHUFFLES}
    for r in rtm:
        d = sorted(drops[r["selected"]])
        S["rtm_shuffle"][r["selected"]] = {"observed_drop_pct": -r["top40_change_pct"], "shuffled_mean_drop_pct": round(sum(d) / len(d), 1),
                                           "shuffled_2_5_pct": round(d[int(0.025 * len(d))], 1), "shuffled_97_5_pct": round(d[int(0.975 * len(d)) - 1], 1)}
    # The old worst 40 still above average: people per place in the next window against people per centerline unit.
    units = len(blocks) + len(nodes)
    S["next_window_rate"] = {"centerline_units": units}
    for r in rtm:
        S["next_window_rate"][r["selected"]] = {"per_top40_place": round(r["after"] / 40.0, 2), "per_unit_citywide": round(r["city_after"] / float(units), 3),
                                                "times": round((r["after"] / 40.0) / (r["city_after"] / float(units)), 1)}
    # Partial follow-up for the 2022-24 top 40: 2025-01 to 2026-08, per year.
    fol = [p for p in people if FOLLOW[0] <= p["date"] <= FOLLOW[1] and p["loc"]]
    yrs = 20 / 12.0
    fc = collections.Counter(p["loc"] for p in fol)
    S["rtm_2022_24_followup"] = {"window": "%s to %s" % FOLLOW, "years": round(yrs, 2),
                                 "top40_per_year_before": round(share["top40"]["people"] / 3.0, 1),
                                 "top40_per_year_after": round(sum(fc[x] for x in cur) / yrs, 1),
                                 "top40_after_people": sum(fc[x] for x in cur),
                                 "city_per_year_before": round(n_all / 3.0, 1), "city_per_year_after": round(len([p for p in people if FOLLOW[0] <= p["date"] <= FOLLOW[1]]) / yrs, 1)}

    with open(os.path.join(OUT, "charts.mdx"), "w") as f:
        f.write(charts(S))
    with open(os.path.join(OUT, "summary.json"), "w") as f:
        json.dump(S, f, indent=1, sort_keys=True); f.write("\n")
    print(json.dumps({k: S[k] for k in ("published_total_check", "share_2022_24", "churn", "rtm", "rtm_2022_24_followup", "unit_mix")}, indent=1))


if __name__ == "__main__":
    main()
