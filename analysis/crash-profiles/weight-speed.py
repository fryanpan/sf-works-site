#!/usr/bin/env python3
"""Does the vehicle-weight effect on pedestrian KSI hold once the posted speed limit and an unsafe-speed primary collision factor are taken into account? Mantel-Haenszel odds ratios, over 5,000 lb against under 3,500 lb, with the n in every stratum.

    python3 analysis/crash-profiles/weight-speed.py                 # 2017-2024, writes out/crash-augment/profiles/weight-speed.json
    python3 analysis/crash-profiles/weight-speed.py --years 2018 2024

Standard library only. It imports crash-profiles.py for its loaders, bands and Mantel-Haenszel estimator, and selects
exactly the pedestrians its vehicle_weight section does: pedestrians hurt in a crash with one moving motor vehicle
(motor_vehicle_parties 1, parked cars left out), by that vehicle's estimated_vehicle_weight_lb band. Its first
stratification (street class x light) must reproduce results.json's vehicle_weight odds ratios, and the JSON says
whether it does.

STRATIFICATIONS (each per pedestrian and per crash, for every weighted vehicle and for model-matched weights)
  class_light              street class x light, as crash-profiles.py does.
  class_light_limit        x posted_speed_limit_mph band (20 or under, 25, 30, 35 or more, unknown).
  class_light_limit_pcf    x whether the primary collision factor (vz_pcf_group) is in the unsafe speed group
                           (CVC 22350 and the other speed sections in crash-profiles.py's VIOLATION).
  limit_only               posted limit band alone.
  and class_light_limit within crashes whose primary collision factor is not unsafe speed.
For each posted-limit band the JSON gives people hurt and KSI people by weight band, and the heavy-vs-light odds
ratio within the band (Mantel-Haenszel over street class x light inside it).

LIKE FOR LIKE
  Every vehicle over 5,000 lb has a model-matched weight, and about half the under-3,500 lb side of all_weighted is a
  body-type average, so model_matched is the like-for-like comparison and all_weighted the larger one.

LIMITS
  posted_speed_limit_mph is dated only for blocks now at 20 mph with an install date (pipeline/crash-augment/street);
  every other block carries today's limit for every year. Each band reports its basis mix. The posted limit is not
  the speed driven, and the primary collision factor is one party's violation as the officer coded it, so neither is
  an impact speed: this is adjustment for proxies of speed, not for speed. A stratum with no heavy or no light
  pedestrian adds nothing to a Mantel-Haenszel estimate; each table says how many strata contributed.
"""

import argparse
import collections
import importlib.util
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("crash_profiles", os.path.join(HERE, "crash-profiles.py"))
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)

OUT = os.path.join(cp.ROOT, "out", "crash-augment", "profiles", "weight-speed.json")
RESULTS = os.path.join(cp.ROOT, "out", "crash-augment", "profiles", "results.json")
MODEL_METHODS = {"exact_make_model_year", "model_10yr_avg"}
BANDS = ("under 3,500 lb", "3,500 to 5,000 lb", "over 5,000 lb", "no weight")
LIMIT_BANDS = ("20 or under", "25", "30", "35 or more", "unknown")


def limit_band(v):
    try:
        v = int(v)
    except ValueError:
        return "unknown"
    return "20 or under" if v <= 20 else ("25" if v == 25 else ("30" if v == 30 else "35 or more"))


def records(y0, y1):
    """One record per pedestrian hurt by a single moving motor vehicle, with every field a stratum reads."""
    crashes, parties, victims = cp.load(y0, y1)
    peds = collections.defaultdict(list)
    for v in victims:
        if v["victim_role"] == "Pedestrian":
            peds[v["case_id_pkey"]].append(v)
    out = []
    for cid, vs in sorted(peds.items()):
        c = crashes.get(cid)
        if c is None or c["motor_vehicle_parties"] != "1":
            continue
        mv = [p for p in parties.get(cid, {}).values()
              if p["vehicle_match_method"] != "not_applicable" and p["party_type"] != "Parked Vehicle"]
        if len(mv) != 1:
            continue
        p = mv[0]
        hurt = [v["victim_degree_of_injury"] in cp.KSI_PERSON for v in vs]
        out.append({
            "case": cid,
            "band": cp.weight_band(p["estimated_vehicle_weight_lb"]),
            "model": p["vehicle_match_method"] in MODEL_METHODS,
            "cls": c["street_class"] or "unknown",
            "light": cp.light_band(c["lighting"]),
            "limit": limit_band(c["posted_speed_limit_mph"]),
            "limit_basis": c["posted_speed_limit_mph_basis"] or "unknown",
            "speed_pcf": cp.violation_group(c["vz_pcf_group"]) == "unsafe speed",
            "n": len(hurt), "ksi": sum(hurt),
        })
    return out


def side(band):
    return "heavy" if band == "over 5,000 lb" else ("light" if band == "under 3,500 lb" else None)


def odds_ratio(recs, key):
    """Mantel-Haenszel heavy vs light, per pedestrian and per crash, stratified by key(rec)."""
    res = {}
    for unit in ("pedestrian", "crash"):
        strata = collections.defaultdict(lambda: {"heavy": [0, 0], "light": [0, 0]})
        for r in recs:
            s = side(r["band"])
            if not s:
                continue
            cell = strata[key(r)][s]
            if unit == "pedestrian":
                cell[0] += r["n"]
                cell[1] += r["ksi"]
            else:
                cell[0] += 1
                cell[1] += 1 if r["ksi"] else 0
        mh = [(s_["heavy"][1], s_["heavy"][0] - s_["heavy"][1], s_["light"][1], s_["light"][0] - s_["light"][1])
              for _, s_ in sorted(strata.items())]
        contributing = sum(1 for a, b, c, d in mh if (a + b) and (c + d))
        informative = sum(1 for a, b, c, d in mh if (a * d) or (b * c))
        hn = sum(s_["heavy"][0] for s_ in strata.values())
        hk = sum(s_["heavy"][1] for s_ in strata.values())
        ln = sum(s_["light"][0] for s_ in strata.values())
        lk = sum(s_["light"][1] for s_ in strata.values())
        crude = (hk / (hn - hk)) / (lk / (ln - lk)) if hn > hk and ln > lk and hk and lk else None
        est, lo, hi = cp.mantel_haenszel(mh)
        res[unit] = {"heavy": [hn, hk], "light": [ln, lk],
                     "crude": round(crude, 2) if crude else None,
                     "mantel_haenszel": round(est, 2) if est else None,
                     "ci95": [round(lo, 2), round(hi, 2)] if est else None,
                     "strata": len(mh), "strata_with_both_sides": contributing,
                     "strata_informative": informative}
    return res


def band_table(recs):
    t = collections.defaultdict(lambda: [0, 0])
    for r in recs:
        t[r["band"]][0] += r["n"]
        t[r["band"]][1] += r["ksi"]
    return [{"band": b, "pedestrians_hurt": t[b][0], "pedestrians_ksi": t[b][1],
             "ksi_rate": round(t[b][1] / t[b][0], 4) if t[b][0] else None} for b in BANDS]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--years", nargs=2, type=int, default=[2017, 2024])
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    recs = records(*a.years)

    strat = {
        "class_light": lambda r: (r["cls"], r["light"]),
        "class_light_limit": lambda r: (r["cls"], r["light"], r["limit"]),
        "class_light_limit_pcf": lambda r: (r["cls"], r["light"], r["limit"], r["speed_pcf"]),
        "limit_only": lambda r: r["limit"],
    }
    out_sets = {}
    for name, sel in (("all_weighted", lambda r: True), ("model_matched", lambda r: r["model"])):
        rs = [r for r in recs if sel(r)]
        ors = {k: odds_ratio(rs, f) for k, f in strat.items()}
        not_speed = [r for r in rs if not r["speed_pcf"]]
        ors["class_light_limit_excluding_unsafe_speed_pcf"] = odds_ratio(not_speed, strat["class_light_limit"])
        by_limit = []
        for lb in LIMIT_BANDS:
            sub = [r for r in rs if r["limit"] == lb]
            basis = collections.Counter()
            for r in sub:
                basis[r["limit_basis"]] += r["n"]
            by_limit.append({"limit": lb, "pedestrians_hurt": sum(r["n"] for r in sub),
                             "pedestrians_ksi": sum(r["ksi"] for r in sub),
                             "basis_people": dict(sorted(basis.items())),
                             "bands": band_table(sub),
                             "heavy_vs_light": odds_ratio(sub, strat["class_light"])})
        by_pcf = []
        for flag in (True, False):
            sub = [r for r in rs if r["speed_pcf"] == flag]
            by_pcf.append({"primary_collision_factor": "unsafe speed" if flag else "any other or not stated",
                           "pedestrians_hurt": sum(r["n"] for r in sub),
                           "pedestrians_ksi": sum(r["ksi"] for r in sub),
                           "bands": band_table(sub),
                           "heavy_vs_light": odds_ratio(sub, strat["class_light_limit"])})
        heavy_mix = []
        for lb in LIMIT_BANDS:
            sub = [r for r in rs if r["limit"] == lb and side(r["band"])]
            h = sum(r["n"] for r in sub if side(r["band"]) == "heavy")
            n = sum(r["n"] for r in sub)
            heavy_mix.append({"limit": lb, "heavy_or_light_pedestrians": n, "heavy": h,
                              "heavy_share": round(h / n, 4) if n else None})
        out_sets[name] = {"bands": band_table(rs), "odds_ratios": ors, "by_posted_limit": by_limit,
                          "by_unsafe_speed_pcf": by_pcf, "heavy_share_by_posted_limit": heavy_mix}

    check = {}
    if os.path.exists(RESULTS):
        with open(RESULTS) as f:
            vw = json.load(f).get("vehicle_weight", {})
        for name in out_sets:
            want = vw.get(name, {}).get("heavy_vs_light_odds_ratio", {})
            got = out_sets[name]["odds_ratios"]["class_light"]
            check[name] = {u: {"results_json": [want.get(u, {}).get("mantel_haenszel"), want.get(u, {}).get("ci95"),
                                                want.get(u, {}).get("heavy"), want.get(u, {}).get("light")],
                               "here": [got[u]["mantel_haenszel"], got[u]["ci95"], got[u]["heavy"], got[u]["light"]],
                               "same": [want.get(u, {}).get(k) for k in ("mantel_haenszel", "ci95", "heavy", "light")]
                               == [got[u][k] for k in ("mantel_haenszel", "ci95", "heavy", "light")]}
                           for u in ("pedestrian", "crash")}

    out = {"about": __doc__.split("\n")[0], "years": a.years,
           "selection": "pedestrians hurt in crashes with exactly one moving motor vehicle (crash-profiles.py vehicle_weight)",
           "compares": "over 5,000 lb vs under 3,500 lb; Mantel-Haenszel (Robins, Breslow and Greenland 1986 interval)",
           "like_for_like": "model_matched (every heavy vehicle is model-matched; about half the light side of all_weighted is a body-type average)",
           "reproduces_results_json_class_light": check,
           "sets": out_sets}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
        f.write("\n")
    for name, s in out_sets.items():
        for k, v in s["odds_ratios"].items():
            p, c = v["pedestrian"], v["crash"]
            print(name, k, "ped", p["mantel_haenszel"], p["ci95"], "crash", c["mantel_haenszel"], c["ci95"],
                  "strata", p["strata"], p["strata_with_both_sides"])
    print(json.dumps(check))


if __name__ == "__main__":
    main()
