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
  fix-map.py counts every fix crash by crash, and this script recounts it from fix-map.json's stack_terms and its own
  reading of the crashes. A term reaches the crashes R in its place and movements (for a text share, the crashes its
  text names, or its movement, or the whole family, as fix-map.json records). R holds the fraction f of the family's
  people hurt (fk of its KSI people), so on each crash in R the term removes rho = share x r / f of the crash's other
  people hurt (r the effect's all-injury value, effect.hurt; none for a KSI-only effect) and rho = share x r / fk of
  its KSI people (every value of the effect), each at most fix-map.json's counting.rho_max, with no floor. When R holds no KSI
  people, the KSI share is spread over the family's crashes with KSI people in the term's movements (all of them, if
  none). A crash keeps the product over the terms reaching it of (1 - rho) of each pool, at least 0, and
  a fix's people avoided on it are its KSI people avoided plus its other people hurt avoided. The rho recounted here
  must equal fix-map.json's for every term, and the sum over every crash must equal fix-map.json's
  hurt_avoided_per_year and ksi_avoided_per_year (at its rounding), or the run stops; nothing is scaled to make
  them match. A person grouping (victim role and age, role and violation family) splits a crash's KSI people
  avoided equally over its KSI victims and its other people hurt avoided equally over its other hurt victims. Every grouping's groups must add
  to each fix's total, and no crash or group may have more KSI people or other people hurt avoided than it holds
  (harm added has no ceiling), or the run stops.

  Stacks: each stack in STACKS is replayed in fix-map.json's order, crash by crash at mid: a step's people avoided on
  a crash are its people x what the steps before left on it x (1 - the step's factor). Each step's sum must equal
  fix-map.json's marginal at that step, and the same allocation bounds hold for every group at every step. After
  the last step, the traffic lever (fix-map.json's traffic_lever, network built, mid) multiplies what is left on each
  crash by its road-user group's factor, written as the stack's "|traffic30" and "|traffic20" entries. Their sums, less the
  people hurt on new transit trips (which have no crash, so are in no group), must equal fix-map.json's traffic marginal.

OUTPUT, out/crash-augment/profiles/fix-groups.json
  groupings[]      id, name, unit and every group: its key, people hurt and KSI people over the years (equal to
                   results.json's), and fixes: for each fix that reaches it, people hurt and KSI people avoided a year
                   [low, mid, high], the people hurt in the group's crashes it reaches, and the fix-map.json row
                   (fixes[].groups index) whose term carries most of it there. stacks: for each stack, people hurt and
                   KSI people avoided a year at each step (mid), the marginal, in step order.
  checks           the per-fix and per-step totals matched, the family totals, and the allocation bounds.
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
fmap = module("fix_map", "fix-map.py")


def load(name):
    with open(os.path.join(PROFILES, name), encoding="utf-8") as f:
        return json.load(f)


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


def term_rho(fam, t, rho_max):
    """(R, KSI crashes, rho other {q}, rho KSI {q}) for one stack term, recounted from this script's crashes."""
    idx = fam.reached(t["place"], t["movements"])
    H, K = sum(fam.h), sum(fam.k)
    fh = sum(fam.h[i] for i in idx) / H if H else 0.0
    fk = sum(fam.k[i] for i in idx) / K if K else 0.0
    eff = t["effect"]
    kidx = idx
    if not fk and t["share_ksi"] and any(eff[q] for q in Q):
        kidx = [i for i in range(len(fam.cases)) if fam.k[i] and (not t["movements"] or fam.mv[i] in t["movements"])] \
            or [i for i in range(len(fam.cases)) if fam.k[i]]
        fk = sum(fam.k[i] for i in kidx) / K if K else 0.0
    ro = {q: min(rho_max, t["share_hurt"] * eff["hurt"][q] / fh) if eff["hurt"] and fh else 0.0 for q in Q}
    rk = {q: min(rho_max, t["share_ksi"] * eff[q] / fk) if fk else 0.0 for q in Q}
    return idx, kidx, ro, rk


def within(amount, held, what):
    """Allocation check: an amount avoided is at most what is held. Harm added has no ceiling."""
    if not amount <= held + 1e-6:
        raise SystemExit("fix-groups: %s: %.6f avoided against %s held" % (what, amount, held))


def near(x, rounded, places):
    """x matches fix-map.json's figure rounded to places: within half a unit of the last place, so a sum that lands on
    a rounding tie in floating point (18.3375 to 18.337 or 18.338) still matches."""
    return abs(x - rounded) <= 0.5 * 10 ** -places + 1e-9


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
    users = {r["case"]: r["users"] for r in fr_recs}
    lever = json.load(open(fmap.TRAFFIC_FILE, encoding="utf-8"))
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
        name = "%s | %s" % (r["mode"], r["violation (fine)"])
        fams.setdefault(name, Family(name)).add(r["case"], r["injured"], r["people"], r["movement (fine)"], tags[r["case"]])
    want = {g["group"]: (g["people_hurt"], g["ksi"]) for g in fm["groups"]}
    got = {n: (sum(f.h), sum(f.k)) for n, f in fams.items()}
    if want != got:
        raise SystemExit("fix-groups: family totals differ from fix-map.json: %s" % sorted(k for k in set(want) | set(got) if want.get(k) != got.get(k))[:5])
    if sum(h for h, _ in got.values()) != fm["inputs"]["people_hurt_total"] or sum(k for _, k in got.values()) != fm["inputs"]["ksi_total"]:
        raise SystemExit("fix-groups: the families do not add to everyone hurt")
    rho_max = fm["counting"]["rho_max"]
    held = {}  # case -> (people hurt, KSI people)
    for f in fams.values():
        for i, c in enumerate(f.cases):
            held[c] = (f.h[i], f.k[i])

    # ---- each fix, crash by crash
    fixes = sorted((f for f in fm["fixes"] if f.get("stack_terms")), key=lambda f: f["id"])
    per_fix = {}       # fid -> {case: [h low, mid, high, k low, mid, high]}
    main_row = {}      # fid -> {case: (term weight, row)} for the term that carries most on each crash
    factors = {}       # fid -> {q: {case: (KSI factor, other factor)}}
    checks = {"fixes": len(fixes), "fix_totals_match_fix_map": True, "rho_match_fix_map": True,
              "stack_steps_match_fix_map": True, "allocation_within_people": True}
    for f in fixes:
        fid = f["id"]
        alloc, best = {}, {}
        fac = {q: {} for q in Q}
        for gname, terms in f["stack_terms"].items():
            fam = fams[gname]
            fk_, fo_ = {q: {} for q in Q}, {q: {} for q in Q}
            for t in terms:
                idx, kidx, ro, rk = term_rho(fam, t, rho_max)
                if len(idx) != t["crashes_reached"] or any(abs(ro[q] - t["rho_other"][q]) > 1e-8 or abs(rk[q] - t["rho_ksi"][q]) > 1e-8 for q in Q):
                    raise SystemExit("fix-groups: %s in %s reaches %d crashes with rho %s / %s; fix-map.json has %d, %s / %s"
                                     % (fid, gname, len(idx), ro["mid"], rk["mid"], t["crashes_reached"], t["rho_other"]["mid"], t["rho_ksi"]["mid"]))
                for q in Q:
                    for i in idx:
                        fo_[q][i] = fo_[q].get(i, 1.0) * (1 - ro[q])
                    for i in kidx:
                        fk_[q][i] = fk_[q].get(i, 1.0) * (1 - rk[q])
                for i in idx:
                    w = fam.h[i] * abs(ro["mid"]) + fam.k[i] * abs(rk["mid"])
                    c = fam.cases[i]
                    if c not in best or w > best[c][0] + 1e-12:
                        best[c] = (w, t["row"])
            for q in Q:
                for i in sorted(set(fk_[q]) | set(fo_[q])):
                    a = max(0.0, fk_[q].get(i, 1.0))
                    b = max(0.0, fo_[q].get(i, 1.0))
                    c = fam.cases[i]
                    fac[q][c] = (a, b)
                    dk = fam.k[i] * (1 - a) / n_years
                    do = (fam.h[i] - fam.k[i]) * (1 - b) / n_years
                    within(dk, fam.k[i] / n_years, "%s on crash %s (KSI)" % (fid, c))
                    within(do, (fam.h[i] - fam.k[i]) / n_years, "%s on crash %s (other hurt)" % (fid, c))
                    v = alloc.setdefault(c, [0.0] * 6)
                    v[Q.index(q)] += dk + do
                    v[3 + Q.index(q)] += dk
        for q in Q:
            fh, fk = f["hurt_avoided_per_year"][q], f["ksi_avoided_per_year"][q]
            sh = sum(a[Q.index(q)] for a in alloc.values())
            sk = sum(a[3 + Q.index(q)] for a in alloc.values())
            if not (near(sh, fh, 2) and near(sk, fk, 3)):
                raise SystemExit("fix-groups: %s %s counts %.6f hurt and %.6f KSI crash by crash; fix-map.json has %s and %s"
                                 % (fid, q, sh, sk, fh, fk))
        per_fix[fid], main_row[fid], factors[fid] = alloc, best, fac

    # ---- stacks, step by step at mid
    fixes_by_id = {f["id"]: f for f in fixes}
    stack_alloc = {}
    for sname in STACKS:
        st = fm["stacks"][sname]
        remk = collections.defaultdict(lambda: 1.0)
        remo = collections.defaultdict(lambda: 1.0)
        steps = []
        for s in st["steps"]:
            step = {}
            for c, (a, b) in sorted(factors[s["id"]]["mid"].items()):
                h, k = held[c]
                x, y = remk[c] * a, remo[c] * b
                step[c] = [(k * (remk[c] - x) + (h - k) * (remo[c] - y)) / n_years, k * (remk[c] - x) / n_years]
                remk[c], remo[c] = x, y
                within(k * (1 - x), k, "%s step %d on crash %s (KSI)" % (sname, s["step"], c))
                within((h - k) * (1 - y), h - k, "%s step %d on crash %s (other hurt)" % (sname, s["step"], c))
            sh = sum(v[0] for v in step.values())
            sk = sum(v[1] for v in step.values())
            if not (near(sh, s["marginal_hurt_avoided"], 2) and near(sk, s["marginal_ksi_avoided"], 3)):
                raise SystemExit("fix-groups: %s step %d (%s) counts %.4f hurt and %.4f KSI; fix-map.json has %s and %s"
                                 % (sname, s["step"], s["id"], sh, sk, s["marginal_hurt_avoided"], s["marginal_ksi_avoided"]))
            steps.append(step)
        stack_alloc[sname] = steps
        # the traffic lever after the stack's street fixes, network built, mid: "<stack>|traffic<car share>"
        for scen, cell in sorted((st.get("traffic") or {}).items()):
            F = lever["scenarios"][scen]["network_built"]["factors"]
            add = lever["scenarios"][scen]["network_built"]["transit_riders_added_a_year"]
            step = {}
            for c in sorted(held):
                h, k = held[c]
                a, b = fmap.crash_traffic_factor(users[c], F, "mid")
                step[c] = [(k * remk[c] * (1 - a) + (h - k) * remo[c] * (1 - b)) / n_years, k * remk[c] * (1 - a) / n_years]
            sh = sum(v[0] for v in step.values()) - add["hurt"]["mid"]
            sk = sum(v[1] for v in step.values()) - add["ksi"]["mid"]
            if not (near(sh, cell["network_built"]["marginal_hurt_avoided"]["mid"], 2) and \
                    near(sk, cell["network_built"]["marginal_ksi_avoided"]["mid"], 3)):
                raise SystemExit("fix-groups: %s's traffic step at %s%% counts %.4f hurt and %.4f KSI; fix-map.json has %s and %s"
                                 % (sname, scen, sh, sk, cell["network_built"]["marginal_hurt_avoided"]["mid"],
                                    cell["network_built"]["marginal_ksi_avoided"]["mid"]))
            stack_alloc["%s|traffic%s" % (sname, scen)] = [step]

    # ---- sum by grouping
    def crash_key(gid, key):
        return lambda r: [(key(r), r["injured"], r["people"], r["case"], 1.0, 1.0)]

    def person_key(key):
        def f(r):
            vs = hurt_v.get(r["case"], [])
            nk = sum(v["victim_degree_of_injury"] in cp.KSI_PERSON for v in vs)
            no = len(vs) - nk
            out = []
            for v in vs:
                is_k = v["victim_degree_of_injury"] in cp.KSI_PERSON
                out.append((key(v, r), 1, int(is_k), r["case"], (1.0 / nk) if is_k else 0.0, 0.0 if is_k else 1.0 / no))
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
        parts = {}  # case -> [(key, share of the crash's KSI people, share of its other people hurt)]
        for r in recs:
            for key, h, k, case, sk_, so_ in split(r):
                g = groups.setdefault(key, {"people_hurt": 0, "ksi": 0})
                g["people_hurt"] += h
                g["ksi"] += k
                parts.setdefault(case, []).append((key, sk_, so_))
        check = fam_want if gid == "family" else alt_bars.get(gid, {})
        for key, (h, k) in check.items():
            if (groups.get(key) or {}).get("people_hurt") != h or groups[key]["ksi"] != k:
                raise SystemExit("fix-groups: %s group %s differs from results.json" % (gid, key))
        fx = {key: {} for key in groups}
        for fid in sorted(per_fix):
            acc = {}
            for case, a in per_fix[fid].items():
                row = main_row[fid].get(case)
                for key, sk_, so_ in parts.get(case, []):
                    e = acc.setdefault(key, {"v": [0.0] * 6, "reached": 0, "rows": collections.Counter()})
                    for j in range(3):
                        e["v"][j] += a[3 + j] * sk_ + (a[j] - a[3 + j]) * so_
                        e["v"][3 + j] += a[3 + j] * sk_
                    e["reached"] += rec_of[case]["injured"] if unit == "crash" else 1
                    if row is not None:
                        e["rows"][row[1]] += row[0] * max(sk_, so_)
            tot = [sum(e["v"][j] for e in acc.values()) for j in range(6)]
            for j, q in enumerate(Q):
                if abs(tot[j] - sum(a[j] for a in per_fix[fid].values())) > 1e-6 or abs(tot[3 + j] - sum(a[3 + j] for a in per_fix[fid].values())) > 1e-6:
                    raise SystemExit("fix-groups: %s's groups in %s add to %.4f, not its total" % (fid, gid, tot[j]))
            for key, e in acc.items():
                v = e["v"]
                g = groups[key]
                for j in range(3):
                    within(v[3 + j], g["ksi"] / n_years, "%s in %s %s (KSI)" % (fid, gid, key))
                    within(v[j] - v[3 + j], (g["people_hurt"] - g["ksi"]) / n_years, "%s in %s %s (other hurt)" % (fid, gid, key))
                fx[key][fid] = {"hurt": [round(x, 3) for x in v[:3]], "ksi": [round(x, 4) for x in v[3:]],
                                "reached_hurt": round(e["reached"], 3) if unit == "person" else int(round(e["reached"])),
                                "row": min(e["rows"].items(), key=lambda kv: (-kv[1], kv[0]))[0] if e["rows"] else None}
        stk = {key: {} for key in groups}
        for sname, steps in stack_alloc.items():
            for key in groups:
                stk[key][sname] = {"hurt": [0.0] * len(steps), "ksi": [0.0] * len(steps)}
            for j, step in enumerate(steps):
                for case, (h, k) in step.items():
                    for key, sk_, so_ in parts.get(case, []):
                        stk[key][sname]["hurt"][j] += k * sk_ + (h - k) * so_
                        stk[key][sname]["ksi"][j] += k * sk_
            for key in groups:
                d = stk[key][sname]
                ch = ck = 0.0
                for x, y in zip(d["hurt"], d["ksi"]):
                    ch, ck = ch + x, ck + y
                    within(ck, groups[key]["ksi"] / n_years, "%s in %s %s (KSI)" % (sname, gid, key))
                    within(ch - ck, (groups[key]["people_hurt"] - groups[key]["ksi"]) / n_years, "%s in %s %s (other hurt)" % (sname, gid, key))
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
