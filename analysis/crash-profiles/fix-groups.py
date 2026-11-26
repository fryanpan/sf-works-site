#!/usr/bin/env python3
"""Spread every fix's people avoided over the crashes it reaches, then sum them by every grouping of SF's crashes, so any group shows the fixes that reach it and the stacked packages' effect on it.

    python3 analysis/crash-profiles/fix-groups.py    # writes out/crash-augment/profiles/fix-groups.json

Run after crash-profiles.py, fix-reach.py and fix-map.py. Standard library only. A second run on the same inputs
writes the same bytes. One-off analysis behind the fix explorer; no page reads it on a schedule.

INPUTS
  results.json     crash-profiles.py: the years, size_families and grouping_alternatives (the totals checked here).
  fix-map.json     fix-map.py: each fix's stack_terms, one list per mode x violation family it reaches, each term a
                   share of the family, an effect r (low, mid, high; scope all or KSI only) and the crashes it reaches
                   (a fix-reach.py place expression, or none for the whole family, and the movements, or none for all),
                   and the stacks' steps.
  crash tables     read through crash-profiles.py's load() and crash_records(), and placed by fix-reach.py's
                   compute(), so every crash's family, movement, place tags and grouping keys are the ones the
                   shares and the groupings were counted with.

COUNTING
  A fix's people avoided in a family is fix-map.py's: the family's people a year x (1 - product over its terms of
  (1 - share x r)), at low, mid and high, for people hurt and for KSI people. That number is spread over the family's
  crashes. A term reaches the crashes R in its place and movements, which hold the fraction f = people in R / people
  in the family, so on each crash in R it removes rho = share x r / f (r itself for a placed fix, times any
  not-yet-treated fraction). A crash's weight is its people x (1 - product over the terms reaching it of (1 - rho)),
  rho kept within -1 to 1, and the family's avoided people are split over its crashes in proportion to those weights,
  so the crashes' amounts add to the family's exactly. KSI people are spread the same way over KSI people (over all
  the reached crashes' KSI people when a term reaches none). A person grouping (victim role and age, role and
  violation family) splits a crash's people hurt avoided equally over its hurt victims and its KSI avoided over its
  KSI victims. A group's avoided people for a fix are the sum over its crashes, so each grouping's groups add to the
  fix's total, which must equal fix-map.json's hurt_avoided_per_year and ksi_avoided_per_year (checked at full
  precision, then rounded as fix-map.py rounds), or the run stops.

  Stacks: each stack in STACKS is replayed in fix-map.json's order. A step's people avoided in a family is fix-map.py's
  marginal (the family's people x the drop in its remaining fraction), spread over the family's crashes by each
  crash's people x what the steps before left on it x (1 - the step's product of (1 - rho)). Each step's sum over
  every group must equal fix-map.json's marginal at that step.

OUTPUT, out/crash-augment/profiles/fix-groups.json
  groupings[]      id, name, unit and every group: its key, people hurt and KSI people over the years (equal to
                   results.json's), and fixes: for each fix that reaches it, people hurt and KSI people avoided a year
                   [low, mid, high], the people hurt in the group's crashes it reaches, and the fix-map.json row
                   (fixes[].groups index) whose term carries most of it there. stacks: for each stack, people hurt and
                   KSI people avoided a year at each step (mid), the marginal, in step order.
  checks           the per-fix and per-step totals matched, and the family totals.
"""

import collections
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PROFILES = os.path.join(ROOT, "out", "crash-augment", "profiles")
OUT = os.path.join(PROFILES, "fix-groups.json")
STACKS = ["greedy_by_people_hurt", "greedy_by_ksi", "area_wide_only", "corner_and_corridor_only",
          "area_wide_and_corner_corridor"]
Q = ("low", "mid", "high")


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


cp = module("crash_profiles", "crash-profiles.py")
fr = module("fix_reach", "fix-reach.py")


def load(name):
    with open(os.path.join(PROFILES, name), encoding="utf-8") as f:
        return json.load(f)


def clamp(x):
    return max(-1.0, min(1.0, x))


class Family(object):
    """One mode x violation family's crashes: case ids, people hurt, KSI people, movement and place tags."""

    def __init__(self, name):
        self.name, self.cases, self.h, self.k, self.mv, self.tags = name, [], [], [], [], []

    def add(self, case, h, k, mv, tags):
        self.cases.append(case)
        self.h.append(h)
        self.k.append(k)
        self.mv.append(mv)
        self.tags.append(tags)

    def reached(self, place, movements):
        """Indexes of the crashes a term reaches."""
        out = []
        for i in range(len(self.cases)):
            if movements and self.mv[i] not in movements:
                continue
            if place and not ((place in self.tags[i]) if place in fr.BASE else fr.evaluate(place, self.tags[i])):
                continue
            out.append(i)
        return out


def term_rho(fam, term, idx, years):
    """(rho for people hurt, rho for KSI) per quantile on each reached crash, and the KSI index set used."""
    H, K = sum(fam.h), sum(fam.k)
    hr, kr = sum(fam.h[i] for i in idx), sum(fam.k[i] for i in idx)
    eff = term["effect"]
    rh, rk = {}, {}
    kidx = idx
    for q in Q:
        th = term["share_hurt"] * eff[q] if eff["scope"] == "all" else 0.0
        tk = term["share_ksi"] * eff[q]
        rh[q] = clamp(th / (hr / H)) if hr and H else 0.0
        rk[q] = clamp(tk / (kr / K)) if kr and K else 0.0
    if K and not kr and any(term["share_ksi"] * eff[q] for q in Q):
        kidx = [i for i in range(len(fam.cases)) if fam.k[i]] or idx
        kk = sum(fam.k[i] for i in kidx)
        for q in Q:
            rk[q] = clamp(term["share_ksi"] * eff[q] / (kk / K)) if kk else 0.0
    return rh, rk, kidx


def spread(total, weights, base):
    """total split over the crashes in proportion to weights {i: w}; base {i: people} when the weights sum to 0."""
    if not total:
        return {}
    s = sum(weights.values())
    if abs(s) < 1e-12:
        weights = base
        s = sum(base.values())
        if not s:
            raise SystemExit("fix-groups: %s people avoided with no people to spread them over" % total)
    return {i: total * w / s for i, w in weights.items()}


def main():
    res = load("results.json")
    fm = load("fix-map.json")
    years = res["years"]
    n_years = years[1] - years[0] + 1
    if fm["inputs"]["years"] != years:
        raise SystemExit("fix-map.json is for %s, results.json for %s; rerun fix-reach.py and fix-map.py" % (fm["inputs"]["years"], years))

    fr_out, fr_recs, _classes = fr.compute()
    if fr_out["years"] != years:
        raise SystemExit("fix-reach years differ from results.json")
    tags = {r["case"]: r["tags"] for r in fr_recs}
    crashes, parties, victims = cp.load(*years)
    bci, _ = cp.bci_blocks()
    recs, _, _ = cp.crash_records(crashes, parties, victims, bci)
    recs.sort(key=lambda r: (len(r["case"]), r["case"]))
    rec_of = {r["case"]: r for r in recs}
    hurt_v = collections.defaultdict(list)
    for v in victims:
        if v["victim_degree_of_injury"] not in cp.NOT_HURT and v["case_id_pkey"] in rec_of:
            hurt_v[v["case_id_pkey"]].append(v)

    fams = {}
    for r in recs:
        if r["mode"] == "not stated":
            continue
        name = "%s | %s" % (r["mode"], r["violation (fine)"])
        fams.setdefault(name, Family(name)).add(r["case"], r["injured"], r["people"], r["movement (fine)"], tags[r["case"]])
    want = {g["group"]: (g["people_hurt"], g["ksi"]) for g in fm["groups"]}
    got = {n: (sum(f.h), sum(f.k)) for n, f in fams.items()}
    if want != got:
        raise SystemExit("fix-groups: family totals differ from fix-map.json: %s" % sorted(k for k in set(want) | set(got) if want.get(k) != got.get(k))[:5])

    # ---- each fix, crash by crash
    fixes = sorted((f for f in fm["fixes"] if f.get("stack_terms")), key=lambda f: f["id"])
    per_fix = {}       # fid -> {case: [h low, mid, high, k low, mid, high]}
    main_row = {}      # fid -> {case: (term weight, row)} for the term that carries most on each crash
    term_cache = {}    # fid -> {family: [(idx set, rho h, rho k, ksi idx)]}
    checks = {"fixes": len(fixes), "fix_totals_match_fix_map": True, "stack_steps_match_fix_map": True}
    for f in fixes:
        fid = f["id"]
        alloc, best, cache = {}, {}, {}
        tot_h = {q: 0.0 for q in Q}
        tot_k = {q: 0.0 for q in Q}
        for gname, terms in f["stack_terms"].items():
            fam = fams[gname]
            hy, ky = sum(fam.h) / n_years, sum(fam.k) / n_years
            ts = []
            for t in terms:
                idx = fam.reached(t["place"], t["movements"])
                rh, rk, kidx = term_rho(fam, t, idx, n_years)
                ts.append((set(idx), rh, rk, set(kidx), t))
            cache[gname] = ts
            reach_any = sorted(set().union(*[x[0] for x in ts]))
            ksi_any = sorted(set().union(*[x[3] for x in ts]))
            for q in Q:
                rem_h = rem_k = 1.0
                for t in terms:
                    e = t["effect"]
                    rem_h *= 1 - (t["share_hurt"] * e[q] if e["scope"] == "all" else 0.0)
                    rem_k *= 1 - t["share_ksi"] * e[q]
                ah, ak = hy * (1 - rem_h), ky * (1 - rem_k)
                tot_h[q] += ah
                tot_k[q] += ak
                wh, wk = {}, {}
                for i in reach_any:
                    p = 1.0
                    for idx, rh, _rk, _ki, _t in ts:
                        if i in idx:
                            p *= 1 - rh[q]
                    wh[i] = fam.h[i] * (1 - p)
                for i in ksi_any:
                    p = 1.0
                    for _idx, _rh, rk, kidx, _t in ts:
                        if i in kidx:
                            p *= 1 - rk[q]
                    wk[i] = fam.k[i] * (1 - p)
                for i, v in spread(ah, wh, {i: fam.h[i] for i in reach_any}).items():
                    alloc.setdefault(fam.cases[i], [0.0] * 6)[Q.index(q)] += v
                for i, v in spread(ak, wk, {i: fam.k[i] for i in ksi_any}).items():
                    alloc.setdefault(fam.cases[i], [0.0] * 6)[3 + Q.index(q)] += v
            for idx, rh, _rk, _ki, t in ts:
                for i in idx:
                    w = fam.h[i] * abs(rh["mid"])
                    c = fam.cases[i]
                    if c not in best or w > best[c][0] + 1e-12:
                        best[c] = (w, t["row"])
            for i in reach_any:
                alloc.setdefault(fam.cases[i], [0.0] * 6)
        for q in Q:
            fh, fk = f["hurt_avoided_per_year"][q], f["ksi_avoided_per_year"][q]
            sh = sum(a[Q.index(q)] for a in alloc.values())
            sk = sum(a[3 + Q.index(q)] for a in alloc.values())
            if abs(sh - tot_h[q]) > 1e-6 or abs(sk - tot_k[q]) > 1e-6 or round(tot_h[q], 2) != fh or round(tot_k[q], 3) != fk:
                raise SystemExit("fix-groups: %s %s spreads %.6f hurt and %.6f KSI; fix-map.json has %s and %s"
                                 % (fid, q, sh, sk, fh, fk))
        per_fix[fid], main_row[fid], term_cache[fid] = alloc, best, cache

    # ---- stacks, step by step at mid
    fixes_by_id = {f["id"]: f for f in fixes}
    stack_alloc = {}
    for sname in STACKS:
        st = fm["stacks"][sname]
        rem = {g: [1.0, 1.0] for g in fams}
        left_h = collections.defaultdict(lambda: 1.0)
        left_k = collections.defaultdict(lambda: 1.0)
        steps = []
        for s in st["steps"]:
            f = fixes_by_id[s["id"]]
            step = {}
            dh = dk = 0.0
            for gname, terms in f["stack_terms"].items():
                fam = fams[gname]
                hy, ky = sum(fam.h) / n_years, sum(fam.k) / n_years
                nh, nk = rem[gname]
                for t in terms:
                    e = t["effect"]
                    nh *= 1 - (t["share_hurt"] * e["mid"] if e["scope"] == "all" else 0.0)
                    nk *= 1 - t["share_ksi"] * e["mid"]
                mh, mk = hy * (rem[gname][0] - nh), ky * (rem[gname][1] - nk)
                dh += mh
                dk += mk
                ts = term_cache[f["id"]][gname]
                reach_any = sorted(set().union(*[x[0] for x in ts]))
                ksi_any = sorted(set().union(*[x[3] for x in ts]))
                wh, wk, ph, pk = {}, {}, {}, {}
                for i in reach_any:
                    p = 1.0
                    for idx, rh, _rk, _ki, _t in ts:
                        if i in idx:
                            p *= 1 - rh["mid"]
                    c = fam.cases[i]
                    wh[i] = fam.h[i] * left_h[c] * (1 - p)
                    ph[i] = p
                for i in ksi_any:
                    p = 1.0
                    for _idx, _rh, rk, kidx, _t in ts:
                        if i in kidx:
                            p *= 1 - rk["mid"]
                    c = fam.cases[i]
                    wk[i] = fam.k[i] * left_k[c] * (1 - p)
                    pk[i] = p
                for i, v in spread(mh, wh, {i: fam.h[i] * left_h[fam.cases[i]] for i in reach_any}).items():
                    step.setdefault(fam.cases[i], [0.0, 0.0])[0] += v
                for i, v in spread(mk, wk, {i: fam.k[i] * left_k[fam.cases[i]] for i in ksi_any}).items():
                    step.setdefault(fam.cases[i], [0.0, 0.0])[1] += v
                for i, p in ph.items():
                    left_h[fam.cases[i]] *= p
                for i, p in pk.items():
                    left_k[fam.cases[i]] *= p
                rem[gname] = [nh, nk]
            sh = sum(v[0] for v in step.values())
            sk = sum(v[1] for v in step.values())
            if abs(sh - dh) > 1e-6 or abs(sk - dk) > 1e-6 or round(dh, 2) != s["marginal_hurt_avoided"] or round(dk, 3) != s["marginal_ksi_avoided"]:
                raise SystemExit("fix-groups: %s step %d (%s) spreads %.4f hurt; fix-map.json has %s"
                                 % (sname, s["step"], s["id"], sh, s["marginal_hurt_avoided"]))
            steps.append(step)
        stack_alloc[sname] = steps

    # ---- sum by grouping
    def crash_key(gid, key):
        return lambda r: [(key(r), r["injured"], r["people"], r["case"], 1.0, 1.0)]

    def person_key(key):
        def f(r):
            vs = hurt_v.get(r["case"], [])
            nk = sum(v["victim_degree_of_injury"] in cp.KSI_PERSON for v in vs)
            out = []
            for v in vs:
                is_k = v["victim_degree_of_injury"] in cp.KSI_PERSON
                out.append((key(v, r), 1, int(is_k), r["case"], 1.0 / len(vs), (1.0 / nk) if is_k else 0.0))
            return out
        return f

    groupings = [("family", "family: mode x violation family (size_families)", "crash",
                  crash_key("family", lambda r: (r["mode"], r["violation (fine)"])))]
    for gid, name, unit, key in cp.GROUPINGS:
        groupings.append((gid, name, unit, person_key(key) if unit == "person" else crash_key(gid, key)))
    alt_bars = {g["id"]: {tuple(b["group"]): (b["people_injured"], b["ksi_people"]) for b in g["top_bars"]}
                for g in res["grouping_alternatives"]["groupings"]}
    fam_want = {(f["mode"], f["violation"]): (f["people_injured"], f["ksi_people"]) for f in res["size_families"]["families"]}

    out_groupings = []
    for gid, name, unit, split in groupings:
        groups = {}
        parts = {}  # case -> [(key, h share, k share)]
        for r in recs:
            if gid == "family" and r["mode"] == "not stated":
                continue
            for key, h, k, case, fh, fk in split(r):
                g = groups.setdefault(key, {"people_hurt": 0, "ksi": 0})
                g["people_hurt"] += h
                g["ksi"] += k
                parts.setdefault(case, []).append((key, fh, fk))
        check = fam_want if gid == "family" else alt_bars.get(gid, {})
        for key, (h, k) in check.items():
            if (groups.get(key) or {}).get("people_hurt") != h or groups[key]["ksi"] != k:
                raise SystemExit("fix-groups: %s group %s differs from results.json" % (gid, key))
        fx = {key: {} for key in groups}
        for fid in sorted(per_fix):
            acc = {}
            for case, a in per_fix[fid].items():
                row = main_row[fid].get(case)
                for key, fh, fk in parts.get(case, []):
                    e = acc.setdefault(key, {"v": [0.0] * 6, "reached": 0, "rows": collections.Counter()})
                    for j in range(3):
                        e["v"][j] += a[j] * fh
                        e["v"][3 + j] += a[3 + j] * fk
                    e["reached"] += rec_of[case]["injured"] * fh if unit == "crash" else (1 if fh else 0)
                    if row is not None:
                        e["rows"][row[1]] += row[0] * fh
            for key, e in acc.items():
                v = e["v"]
                fx[key][fid] = {"hurt": [round(x, 3) for x in v[:3]], "ksi": [round(x, 4) for x in v[3:]],
                                "reached_hurt": round(e["reached"], 3) if unit == "person" else int(round(e["reached"])),
                                "row": min(e["rows"].items(), key=lambda kv: (-kv[1], kv[0]))[0] if e["rows"] else None}
        stk = {key: {} for key in groups}
        for sname, steps in stack_alloc.items():
            for key in groups:
                stk[key][sname] = {"hurt": [0.0] * len(steps), "ksi": [0.0] * len(steps)}
            for j, step in enumerate(steps):
                for case, (h, k) in step.items():
                    for key, fh, fk in parts.get(case, []):
                        stk[key][sname]["hurt"][j] += h * fh
                        stk[key][sname]["ksi"][j] += k * fk
            for key in groups:
                d = stk[key][sname]
                d["hurt"] = [round(x, 3) for x in d["hurt"]]
                d["ksi"] = [round(x, 4) for x in d["ksi"]]
        rows = []
        for key in sorted(groups, key=lambda k: (-groups[k]["people_hurt"], -groups[k]["ksi"], k)):
            rows.append({"key": list(key), "people_hurt": groups[key]["people_hurt"], "ksi": groups[key]["ksi"],
                         "fixes": dict(sorted(fx[key].items())), "stacks": stk[key]})
        out_groupings.append({"id": gid, "name": name, "unit": unit, "groups": rows})

    out = {
        "about": __doc__.split("\n")[0],
        "years": years,
        "stacks": {s: [x["id"] for x in fm["stacks"][s]["steps"]] for s in STACKS},
        "groupings": out_groupings,
        "checks": checks,
    }
    text = json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    old = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else None
    if text != old:
        with open(OUT, "w", encoding="utf-8") as f:
            f.write(text)
    print("fixes %d spread over %d groupings; wrote %s%s" % (len(fixes), len(out_groupings), os.path.relpath(OUT, ROOT),
          "" if text != old else " (unchanged)"), file=sys.stderr)


if __name__ == "__main__":
    main()
