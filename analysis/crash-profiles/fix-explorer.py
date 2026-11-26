#!/usr/bin/env python3
"""Build the crash fix explorer, one self-contained HTML page of SF crash groups, the fixes mapped to them, their cost per person hurt avoided and stacked packages.

Reads out/crash-augment/profiles/fix-map.json, fix-reach.json and results.json
(written by fix-map.py, fix-reach.py and crash-profiles.py) and writes
out/crash-augment/profiles/fix-explorer.html with the data inlined as JSON and
plain SVG and HTML for the charts, so it opens with no network.

    python3 analysis/crash-profiles/fix-explorer.py [--profiles DIR] [--out FILE]

--profiles names the folder holding the three inputs (default this repo's
out/crash-augment/profiles), so the page can be rebuilt on revised numbers.

The three stacks come from fix-map.json's stacks (area_wide_only,
corner_and_corridor_only, area_wide_and_corner_corridor), which carry the mid
only. The low and high band is recounted here in the same order with the same
sequential rule (remaining = product of 1 - share x r within each of the 45
mode x family groups), from each fix's used family pairs, with its "all other
families" entry spread over the families it does not map itself and placed by
fix-reach.json where reach.json places the fix. The recount must reproduce
fix-map.json's mid at every step to 0.05 people and 0.005 KSI people, or the
script stops: a band that does not match the line it surrounds would be wrong.

Standard library only. A second run on the same inputs writes the same bytes.
"""

import argparse
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_PROFILES = os.path.join(ROOT, "out", "crash-augment", "profiles")
REACH_CFG = os.path.join(ROOT, "analysis", "crash-profiles", "fixes", "reach.json")
YEARS = 8

STACKS = [
    ("area", "area_wide_only", "Area-wide only"),
    ("corner", "corner_and_corridor_only", "Corner and corridor only"),
    ("both", "area_wide_and_corner_corridor", "Both"),
]
LEVERS = [
    ("street design", "Street Design"),
    ("signals", "Signals"),
    ("speed management", "Speed"),
    ("traffic volume and filtering", "Traffic Volume and Filtering"),
    ("pricing", "Pricing"),
    ("vehicles and fleets", "Vehicles and Fleets"),
    ("automated enforcement", "Enforcement"),
    ("behaviour programs", "Behavior"),
    ("transit and land use", "Transit and Land Use"),
    ("policy and law", "Policy"),
]
MODES = {"vehicles only": "Vehicles only", "pedestrian involved": "Someone walking", "bicycle involved": "Someone biking"}
VIOLATIONS = {
    "DUI": "Driving under the influence",
    "not stated": "Cause not stated",
    "failure to yield to pedestrian": "Failure to yield to someone walking",
    "pedestrian violation": "Violation by the person walking",
}
WHERE = [("signalized", "At a signalized corner"), ("hin", "On the High Injury Network"),
         ("ltn_cell", "Inside a residential cell"), ("school_zone", "In a school zone"), ("dark", "After dark")]
REASONS = [
    ("no effect size", "No study gives its effect on crashes"),
    ("text says the reachable share", "We can't yet count how much of this group it reaches"),
    ("same reach as the entry before", "We can't yet count how much of this group it reaches"),
    ("target share not parseable", "We can't yet count how much of this group it reaches"),
    ("group has no SF count", "SF has no count for this group"),
    ("effect is not a crash or injury outcome", "Its studies measure speed or behaviour, not crashes"),
    ("effect unit does not name a crash outcome", "Its studies measure speed or behaviour, not crashes"),
    ("effect is for pedestrians", "Its effect was measured for people walking only"),
    ("effect outside a plausible range", "Its study's effect is outside a plausible range"),
    ("reach is the share", "No record gives the share it would reach"),
    ("reach:", "We can't place it on SF's street map yet"),
    ("enabler", "A law that allows another fix; its benefit is counted with that fix"),
    ("no computable fix x group pair", "No crash group it reaches can be counted yet"),
    ("no cost", "No cost estimate"),
    ("per-unit cost", "Priced per unit, and SF has no count of the places it would go"),
    ("one-time cost", "One-time cost with no service life to spread it over"),
]


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def plain_reason(r):
    if not r:
        return None
    for key, text in REASONS:
        if r.startswith(key) or key in r[:60]:
            return text
    return r[0].upper() + r[1:]


def family_label(name):
    if name == "all other families":
        return "All other crashes", ""
    mode, _, viol = name.partition(" | ")
    v = VIOLATIONS.get(viol, viol[:1].upper() + viol[1:])
    return v, MODES.get(mode, mode)


US_WORDS = [
    (r"\bneighbourhood", "neighborhood"), (r"\bNeighbourhood", "Neighborhood"), (r"behaviour", "behavior"),
    (r"Behaviour", "Behavior"), (r"channelis", "channeliz"), (r"ignalis", "ignaliz"), (r"categoris", "categoriz"),
    (r"\bcentre", "center"), (r"\bcentres", "centers"), (r"colour", "color"), (r"\blicence", "license"),
    (r"\bHIN\b", "High Injury Network"), (r"\bKSI\b", "killed or seriously hurt"),
]


def feet(text):
    """Metres in record text to feet and British spellings and acronyms to the site's US words."""
    if not text:
        return text
    text = re.sub(r"(?<![$\d.])(\d+(?:\.\d+)?) m\b(?![\w/])",
                  lambda m: "%d ft" % round(float(m.group(1)) * 3.281), text)
    for a, b in US_WORDS:
        text = re.sub(a, b, text)
    return text


def short_name(name):
    """The fix's name without a trailing list of example cities or programs."""
    m = re.match(r"^(.*\S)\s*\(([^()]*)\)$", name)
    if m and re.search(r"[,;\d]", m.group(2)):
        name = m.group(1)
    return feet(name)


def r3(x):
    return None if x is None else round(x, 4)


def q3(d):
    return None if not d else {k: r3(d[k]) for k in ("low", "mid", "high")}


def effect_text(eff):
    """The study's effect as a fraction removed, low to high, from effect_fraction."""
    if not eff:
        return None
    return {"l": r3(eff["low"]), "m": r3(eff["mid"]), "h": r3(eff["high"]), "ksi_only": eff.get("scope") == "ksi"}


def source_link(fix, src_text):
    """The fix's source whose title starts with the effect source's first word, else its first linked source."""
    srcs = [s for s in fix.get("sources") or [] if s.get("url", "").startswith("http")]
    if not srcs:
        return None
    word = re.split(r"[ ,(]", (src_text or "").strip())[0].lower()
    if word:
        for s in srcs:
            if s["title"].lower().startswith(word):
                return s["url"]
    return srcs[0]["url"]


# ---------------------------------------------------------------- stack recount
def stack_terms(fix, fam_names, remainder, reach_cfg, fr):
    rows = [r for r in fix["groups"] if r.get("used") and r.get("computable")]
    direct = {r["group"] for r in rows if r["kind"] == "family"}
    terms = {}
    for r in rows:
        eff = r["effect_fraction"]
        if r["kind"] == "family":
            terms.setdefault(r["group"], []).append((r["share_hurt"], r["share_ksi"], eff))
        elif r["kind"] == "remainder":
            for m in remainder:
                if m in direct:
                    continue
                if r.get("reach_place"):
                    c = reach_cfg[fix["id"]]
                    if r.get("movement") or c.get("text") == "multiply" or ((c.get("by_group") or {}).get(m) or {}).get("text") == "multiply":
                        raise SystemExit("fix-explorer: %s has a remainder entry this recount does not handle" % fix["id"])
                    place = ((c.get("by_group") or {}).get(m) or {}).get("place") or c["place"]
                    g = fr["groups"][m]
                    p = g["places"][place]
                    sh = p["people_hurt"] / g["people_hurt"] if g["people_hurt"] else 0.0
                    sk = p["ksi"] / g["ksi"] if g["ksi"] else sh
                    sc = c.get("share_scale", 1.0)
                    sh, sk = sh * sc, sk * sc
                else:
                    sh, sk = r["share_hurt"], r["share_ksi"]
                terms.setdefault(m, []).append((sh, sk, eff))
    return terms


def recount(order, fixes, fam, remainder, reach_cfg, fr, q):
    rem = {g: [1.0, 1.0] for g in fam}
    out, ch, ck = [], 0.0, 0.0
    for fid in order:
        dh = dk = 0.0
        for g, ts in stack_terms(fixes[fid], fam, remainder, reach_cfg, fr).items():
            hy, ky = fam[g]["people_hurt"] / YEARS, fam[g]["ksi"] / YEARS
            nh, nk = rem[g]
            for sh, sk, e in ts:
                nh *= 1 - (sh * e[q] if e["scope"] == "all" else 0.0)
                nk *= 1 - sk * e[q]
            dh += hy * (rem[g][0] - nh)
            dk += ky * (rem[g][1] - nk)
            rem[g] = [nh, nk]
        ch += dh
        ck += dk
        out.append((ch, ck))
    return out


# ---------------------------------------------------------------- build data
def build(profiles):
    fm = load(os.path.join(profiles, "fix-map.json"))
    fr = load(os.path.join(profiles, "fix-reach.json"))
    res = load(os.path.join(profiles, "results.json"))
    reach_cfg = load(REACH_CFG)["fixes"]
    fixes = {f["id"]: f for f in fm["fixes"]}
    fam = {g["group"]: g for g in fm["groups"]}
    remainder = sorted(g for g, v in fam.items() if not v["in_chart"])
    year_h = fm["inputs"]["people_hurt_total"] / YEARS
    year_k = fm["inputs"]["ksi_total"] / YEARS

    stacks = {}
    for key, src, label in STACKS:
        st = fm["stacks"][src]
        order = [s["id"] for s in st["steps"]]
        mid = recount(order, fixes, fam, remainder, reach_cfg, fr, "mid")
        for s, (h, k) in zip(st["steps"], mid):
            if abs(h - s["cumulative_hurt_avoided"]) > 0.05 or abs(k - s["cumulative_ksi_avoided"]) > 0.005:
                raise SystemExit("fix-explorer: recount of %s step %d (%s) gives %.2f hurt, fix-map.json %.2f; band not drawn"
                                 % (src, s["step"], s["id"], h, s["cumulative_hurt_avoided"]))
        lo = recount(order, fixes, fam, remainder, reach_cfg, fr, "low")
        hi = recount(order, fixes, fam, remainder, reach_cfg, fr, "high")
        steps = []
        for s, l, h in zip(st["steps"], lo, hi):
            steps.append({
                "id": s["id"], "cost": s["cumulative_annual_cost"], "add": s["annual_cost"],
                "h": [r3(l[0] / year_h), s["share_of_people_hurt_avoided"], r3(h[0] / year_h)],
                "k": [r3(l[1] / year_k), s["share_of_ksi_avoided"], r3(h[1] / year_k)],
                "dh": round(s["marginal_hurt_avoided"], 1), "dk": round(s["marginal_ksi_avoided"], 2),
            })
        stacks[key] = {"label": label, "steps": steps, "not_added": st["not_added"]}

    # groups and the fixes mapped to each
    def where_of(names):
        tot_h = sum(fr["groups"][n]["people_hurt"] for n in names)
        out = []
        for place, label in WHERE:
            ph = sum(fr["groups"][n]["places"][place]["people_hurt"] for n in names)
            out.append([label, r3(ph / tot_h) if tot_h else None])
        return out

    group_rows = {}

    def add_row(gkey, fix, r):
        group_rows.setdefault(gkey, {}).setdefault(fix["id"], []).append(r)

    for f in fm["fixes"]:
        for r in f["groups"]:
            g = r["group"]
            if g in fam or g == "all other families":
                add_row(g, f, r)
            elif g.startswith("place | "):
                add_row(g, f, r)
            elif g.startswith("who | "):
                add_row(g, f, r)
            elif g.startswith("pedestrian | "):
                m = re.match(r"pedestrian \| (.*?) \(cross-cut", g)
                if m:
                    add_row("who | pedestrian | " + m.group(1), f, r)

    def fix_list(gkey):
        out = []
        for fid, rows in sorted(group_rows.get(gkey, {}).items()):
            fix = fixes[fid]
            used = [r for r in rows if r.get("computable") and r.get("used")]
            if not used:
                used = [r for r in rows if r.get("computable")][:1]
            if used:
                ah = {q: sum((r.get("hurt_avoided_per_year") or {}).get(q, 0.0) for r in used) for q in ("low", "mid", "high")}
                ak = {q: sum((r.get("ksi_avoided_per_year") or {}).get(q, 0.0) for r in used) for q in ("low", "mid", "high")}
                if not any((r.get("hurt_avoided_per_year") or None) for r in used):
                    ah = None
                r0 = used[0]
                out.append({
                    "id": fid, "ah": q3(ah), "ak": q3(ak),
                    "share": r3(sum(r.get("share_hurt") or 0.0 for r in used)),
                    "mech": feet(r0.get("mechanism") or fix.get("how_it_works")),
                    "eff": effect_text(r0.get("effect_fraction")),
                    "src": feet((r0.get("effect") or {}).get("source")),
                    "url": source_link(fix, (r0.get("effect") or {}).get("source")),
                    "why": None,
                })
            else:
                r0 = rows[0]
                out.append({"id": fid, "ah": None, "ak": None, "share": None,
                            "mech": feet(r0.get("mechanism") or fix.get("how_it_works")), "eff": None,
                            "src": None, "url": None, "why": plain_reason(r0.get("reason"))})
        out.sort(key=lambda x: (x["why"] is not None, -((x["ah"] or {}).get("mid") or 0.0),
                                -((x["ak"] or {}).get("mid") or 0.0), x["id"]))
        return out

    groupings = {}
    fams = []
    for c in res["size_families"]["chart"]:
        name = "all other families" if c["mode"] == "all other families" else "%s | %s" % (c["mode"], c["violation"])
        label, sub = family_label(name)
        members = remainder if name == "all other families" else [name]
        fams.append({"key": name, "label": label, "sub": sub,
                     "h": round(c["people_injured"] / YEARS), "k": round(c["ksi_people"] / YEARS, 1),
                     "where": where_of(members), "fixes": fix_list(name)})
    groupings["family"] = fams
    alts = {g["name"].split(":")[0]: g for g in res["grouping_alternatives"]["groupings"]}
    for gkey, alt, prefix in (("place", "place", "place | "), ("who", "who was hurt", "who | ")):
        rows = []
        for b in alts[alt]["top_bars"]:
            if b.get("catch_all"):
                continue
            key = prefix + " | ".join(b["group"])
            if gkey == "place":
                stress, cls, where = b["group"]
                label = "%s %s" % (cls[:1].upper() + cls[1:], where)
                sub = "High traffic stress" if stress.startswith("high") else "Low traffic stress"
            else:
                role, age = b["group"]
                label = "%s, %s" % (role[:1].upper() + role[1:], age)
                sub = ""
            rows.append({"key": key, "label": label, "sub": sub, "h": round(b["people_injured"] / YEARS),
                         "k": round(b["ksi_people"] / YEARS, 1), "where": None, "fixes": fix_list(key)})
        groupings[gkey] = rows

    # fixes
    fx = {}
    for f in fm["fixes"]:
        reasons = f.get("not_computable_reasons") or []
        ranked_reason = None
        if not (f["computable"] and f["avoided_basis"] == "families" and f.get("cost_per_person_hurt_avoided")):
            ranked_reason = plain_reason(reasons[0]) if reasons else (
                "Reaches only groups that overlap the crash families, so it is not ranked" if f["avoided_basis"] else "Not counted")
        top = sorted(((r["group"], (r.get("hurt_avoided_per_year") or {}).get("mid") or 0.0)
                      for r in f["groups"] if r.get("used") and r.get("computable") and r["kind"] == "family"),
                     key=lambda x: -x[1])
        fx[f["id"]] = {
            "name": short_name(f["name"]), "full": feet(f["name"]), "lever": f["lever"], "area": f["scope"] == "area-wide",
            "how": feet(f.get("how_it_works")), "grade": feet(f.get("evidence_grade")),
            "cost": q3(f.get("annual_cost")) if f.get("annual_cost") else None,
            "cph": q3(f.get("cost_per_person_hurt_avoided")), "cpk": q3(f.get("cost_per_ksi_avoided")),
            "ah": q3(f.get("hurt_avoided_per_year")) if f["avoided_basis"] == "families" else None,
            "ak": q3(f.get("ksi_avoided_per_year")) if f["avoided_basis"] == "families" else None,
            "sf": feet(f.get("sf_evidence")) if f["id"] in fm["sf_evidence"] else None,
            "top": [[("%s (%s)" % (family_label(g)[0], family_label(g)[1].lower())) if family_label(g)[1] else family_label(g)[0], round(v, 1)] for g, v in top[:3] if v > 0],
            "sources": [{"t": s["title"], "u": s["url"]} for s in f.get("sources") or [] if s.get("url", "").startswith("http")][:4],
            "why": ranked_reason,
            "lowconf": feet(((f.get("reach_confidence") or {}).get("why") or "").replace("Low confidence on reach: ", "")) or None
            if (f.get("reach_confidence") or {}).get("level") == "low" else None,
            "most": (f.get("reach_treated") or "").startswith("most it could reach"),
        }
    ranking = [r["id"] for r in fm["ranking"]]
    unranked = sorted((i for i in fx if i not in set(ranking)), key=lambda i: fx[i]["name"])

    # about
    sf_by_what = {}
    for fid, evs in sorted(fm["sf_evidence"].items()):
        for e in evs:
            sf_by_what.setdefault(e["what"], {"what": e["what"], "low": e["low_it_sets"], "fixes": []})["fixes"].append(short_name(fixes[fid]["name"]))
    sf_rows = sorted(sf_by_what.values(), key=lambda x: x["what"])
    reason_counts = {}
    for n in fm["not_computable"]:
        t = plain_reason(n["reason"])
        reason_counts[t] = reason_counts.get(t, 0) + 1
    about = {
        "people_year": round(year_h), "ksi_year": round(year_k), "years": fm["inputs"]["years"],
        "fixes": len(fm["fixes"]), "computable": fm["summary"]["fixes_computable"], "ranked": len(ranking),
        "sf": sf_rows,
        "gaps": sorted(([k, v] for k, v in reason_counts.items()), key=lambda x: (-x[1], x[0]))[:6],
        "values": [{"t": s["title"], "u": s["url"]} for s in fm["inputs"]["value_sources"]],
        "read": sorted(set(fr["sources"].values()))[-1],
    }
    return {"stack_order": [k for k, _, _ in STACKS], "stacks": stacks, "groupings": groupings, "fixes": fx, "ranking": ranking,
            "unranked": unranked, "levers": LEVERS, "about": about}


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stacking Fixes for SF Crashes</title>
<style>
:root { --ink:#15181c; --muted:#59626f; --line:#d9dde2; --soft:#f4f6f8; --teal:#2f7d76; --teal-soft:#d4e6e4; --brown:#9c5f3c; --gold:#efb118; --link:#b8322a; }
* { box-sizing: border-box; }
html, body { margin:0; height:100%; }
body { color:var(--ink); background:#fff; font: 14px/1.4 "Public Sans", ui-sans-serif, system-ui, -apple-system, sans-serif; }
a { color:var(--link); text-underline-offset:2px; }
header { height:56px; display:flex; align-items:center; gap:20px; padding:0 16px; border-bottom:1px solid var(--line); }
header h1 { font: 700 17px/1.2 Archivo, "Public Sans", sans-serif; margin:0; white-space:nowrap; }
nav { display:flex; gap:4px; }
nav button, .chips button { font:inherit; border:1px solid var(--line); background:#fff; color:var(--ink); border-radius:16px; padding:5px 12px; cursor:pointer; white-space:nowrap; }
nav button[aria-pressed=true], .chips button[aria-pressed=true] { background:var(--ink); border-color:var(--ink); color:#fff; }
main { display:grid; grid-template-columns: 230px minmax(0,1fr) 380px; height:calc(100vh - 56px); }
#left { border-right:1px solid var(--line); padding:14px; overflow:auto; }
#mid { padding:14px 18px; overflow:auto; }
#right { border-left:1px solid var(--line); padding:14px; overflow:auto; background:#fcfcfd; }
h2 { font: 700 15px/1.25 Archivo, "Public Sans", sans-serif; margin:0 0 6px; }
h3 { font: 600 13px/1.3 "Public Sans", sans-serif; margin:14px 0 6px; color:var(--muted); text-transform:none; }
.label { font-size:12px; color:var(--muted); margin:0 0 6px; }
.chips { display:flex; flex-direction:column; gap:6px; margin-bottom:16px; align-items:flex-start; }
.note { color:var(--muted); font-size:12.5px; margin:6px 0 0; }
svg text { font-family: inherit; }
.view { display:none; } .view.on { display:block; }
.ctl { display:none; } .ctl.on { display:block; }
/* stack list */
.steps { list-style:none; margin:0; padding:0; }
.steps li { display:grid; grid-template-columns: 24px 1fr auto; gap:6px; padding:6px 4px; border-bottom:1px solid var(--line); cursor:pointer; align-items:baseline; }
.steps li .n { font-weight:700; color:var(--teal); }
.steps li .v { font-variant-numeric: tabular-nums; text-align:right; white-space:nowrap; }
.steps li.sel { background:var(--teal-soft); }
.steps li .more { grid-column: 2 / 4; display:none; color:var(--muted); font-size:12.5px; }
.steps li.sel .more { display:block; }
.tag.q { background:#eef0f3; color:#59626f; }
.tag { display:inline-block; font-size:11px; padding:0 6px; border-radius:8px; background:#fdf1d3; color:#6b4e00; margin-left:4px; white-space:nowrap; vertical-align:1px; }
/* group bars */
.gb { width:100%; border-collapse:collapse; }
.gb th { text-align:left; font-weight:600; font-size:12px; color:var(--muted); padding:0 6px 6px 0; }
.gb td { padding:3px 6px 3px 0; vertical-align:middle; }
.gb tr.row { cursor:pointer; }
.gb tr.row:hover td { background:var(--soft); }
.gb tr.sel td { background:var(--teal-soft); }
.gb .name { width:38%; } .gb .name small { display:block; color:var(--muted); font-size:11.5px; }
.bar { display:flex; align-items:center; gap:6px; }
.bar i { display:block; height:14px; border-radius:2px; background:var(--teal); min-width:1px; }
.bar.k i { background:var(--brown); }
.bar b { font-weight:500; font-variant-numeric:tabular-nums; font-size:12.5px; }
/* fix rows in panels */
.fx { border-bottom:1px solid var(--line); padding:7px 0; }
.fx summary { list-style:none; cursor:pointer; display:grid; grid-template-columns: 1fr auto; gap:8px; align-items:baseline; }
.fx summary::-webkit-details-marker { display:none; }
.fx .v { font-variant-numeric:tabular-nums; white-space:nowrap; font-weight:600; }
.fx.off summary { color:var(--muted); }
.fx.off .v { font-weight:400; font-size:12px; }
.fx dl { margin:6px 0 2px; display:grid; grid-template-columns: 118px 1fr; gap:3px 8px; font-size:12.5px; }
.fx dt { color:var(--muted); } .fx dd { margin:0; }
.where { display:grid; grid-template-columns: 1fr 90px; gap:3px 8px; font-size:12.5px; align-items:center; }
.where .bar i { height:10px; background:var(--teal); }
/* ranking */
.rk { width:100%; border-collapse:collapse; }
.rk td { padding:3px 6px 3px 0; vertical-align:middle; }
.rk tr.row { cursor:pointer; } .rk tr.row:hover td { background:var(--soft); } .rk tr.sel td { background:var(--teal-soft); }
.rk .name { width:42%; font-size:13px; }
.rk .v { text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; width:86px; }
.rk svg { display:block; }
.big { font: 700 30px/1.1 Archivo, "Public Sans", sans-serif; color:var(--teal); margin:4px 0 2px; }
details.about summary { cursor:pointer; font-weight:600; }
details.about { font-size:12.5px; border-top:1px solid var(--line); padding-top:10px; margin-top:8px; }
details.about p, details.about li { margin:4px 0; }
details.about ul { padding-left:16px; margin:4px 0; }
.unr { color:var(--muted); font-size:12.5px; }
.unr li { margin:3px 0; }
@media (max-width: 760px) {
  header { height:auto; flex-wrap:wrap; gap:8px; padding:10px 12px; }
  nav { overflow-x:auto; max-width:100%; }
  main { display:block; height:auto; }
  #left, #mid, #right { border:0; overflow:visible; padding:10px 12px; }
  #left { padding-bottom:0; }
  .chips { flex-direction:row; flex-wrap:wrap; margin-bottom:6px; }
  .chips button { padding:4px 10px; }
  .phoneOnly { display:block !important; }
  #right { border-top:1px solid var(--line); }
  #left details.about { display:none; }
  #aboutPhone { display:block; padding:0 12px 20px; }
  .gb .name { width:44%; }
  .rk .name { width:auto; font-size:12.5px; }
  .rk td:nth-child(2), .wideOnly { display:none; }
  .rk .v { width:64px; font-size:12.5px; }
}
#aboutPhone { display:none; }
.phoneOnly { display:none; }
</style>
</head>
<body>
<header>
  <h1>Stacking Fixes for SF Crashes</h1>
  <nav aria-label="Views">
    <button data-view="stack" aria-pressed="true">Stacking Fixes</button>
    <button data-view="groups" aria-pressed="false">Crash Groups</button>
    <button data-view="rank" aria-pressed="false">Fixes Ranked</button>
  </nav>
</header>
<main>
  <section id="left">
    <div class="ctl on" data-for="stack">
      <p class="label">Which fixes</p>
      <div class="chips" id="stackChips"></div>
      <p class="label">Count</p>
      <div class="chips" id="measureChips"></div>
    </div>
    <div class="ctl" data-for="groups">
      <p class="label">Group crashes by</p>
      <div class="chips" id="groupChips"></div>
    </div>
    <div class="ctl" data-for="rank">
      <p class="label">Kind of fix</p>
      <div class="chips" id="leverChips"></div>
    </div>
    <details class="about" id="aboutBox"><summary>About the Data</summary><div class="aboutBody"></div></details>
  </section>
  <section id="mid">
    <div class="view on" data-for="stack">
      <h2 id="stackTitle"></h2>
      <div id="stackChart"></div>
      <p class="note">Each fix acts only on the people the fixes before it left, within each crash group, so no one is counted twice. Shaded band: the studies' low to high effects.</p>
    </div>
    <div class="view" data-for="groups">
      <h2>Who Gets Hurt, a Year</h2>
      <table class="gb" id="groupTable"></table>
      <p class="note">SF crashes 2017 to 2024, a yearly average. Tap a group to see the fixes that reach it.</p>
    </div>
    <div class="view" data-for="rank">
      <h2>Cost per Person Hurt Avoided</h2>
      <table class="rk" id="rankTable"></table>
      <p class="note">Each fix on its own, at every place of its kind in SF.<span class="wideOnly"> Dot: middle estimate; line: low to high.</span></p>
      <h3 id="unrTitle"></h3>
      <ul class="unr" id="unrList"></ul>
    </div>
  </section>
  <section id="right">
    <div class="view on" data-for="stack"><h2>Fixes in the Order Added</h2><ol class="steps" id="stepList"></ol></div>
    <div class="view" data-for="groups"><div id="groupDetail"></div></div>
    <div class="view" data-for="rank"><div id="fixDetail"></div></div>
  </section>
</main>
<details class="about" id="aboutPhone"><summary>About the Data</summary><div class="aboutBody"></div></details>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const F = D.fixes;
const S = { view:'stack', stack:'both', measure:'h', grouping:'family', group:null, lever:'all', fix:null, step:0 };
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function sig(x, n=2) { if (x === 0) return '0'; const a = Math.abs(x); const e = Math.floor(Math.log10(a)) - n + 1; const v = Math.round(x / Math.pow(10, e)) * Math.pow(10, e); return e < 0 ? v.toFixed(-e) : String(Math.round(v)); }
function num(x) { if (x == null) return ''; const a = Math.abs(x); if (a >= 100) return Number(sig(x)).toLocaleString('en-US'); if (a >= 10) return sig(x); if (a >= 1) return Number(sig(x)).toFixed(a < 10 && Number(sig(x)) % 1 ? 1 : 0); return Number(sig(x)).toString(); }
function money(x) { if (x == null) return ''; if (x === 0) return '$0'; const a = Math.abs(x);
  if (a >= 1e9) return '$' + sig(x / 1e9) + 'B'; if (a >= 1e6) return '$' + sig(x / 1e6) + 'M'; if (a >= 1e3) return '$' + Number(sig(x)).toLocaleString('en-US'); return '$' + sig(x); }
function pct(x) { return (x == null) ? '' : (Math.round(x * 1000) / 10 >= 10 || Math.abs(x) < 0.001 ? Math.round(x * 100) : (Math.round(x * 1000) / 10)) + '%'; }
function effText(e) { if (!e) return ''; const f = v => v >= 0 ? pct(v) + ' fewer' : pct(-v) + ' more';
  const lo = e.l, hi = e.h; return f(e.m) + ' (' + (lo < 0 ? pct(-lo) + ' more' : pct(lo)) + ' to ' + (hi < 0 ? pct(-hi) + ' more' : pct(hi) + ' fewer') + ')' + (e.ksi_only ? ', killed or seriously hurt only' : ''); }
const rg = (q, paren) => num(q.low) === num(q.high) ? '' : (paren ? ` (${num(q.low)} to ${num(q.high)})` : `, ${num(q.low)} to ${num(q.high)}`);
const areaTag = id => (F[id].area ? '<span class="tag" title="Covers whole neighborhoods or the city">Area-wide</span>' : '') + (F[id].lowconf ? '<span class="tag q" title="The city data on where it could go is shaky">Reach uncertain</span>' : '') + (F[id].most ? '<span class="tag q" title="Places already treated are not netted out">At most</span>' : '');

function chips(el, items, key, after) {
  const box = document.getElementById(el);
  box.innerHTML = items.map(([v, t]) => `<button data-v="${esc(v)}" aria-pressed="${S[key] === v}">${esc(t)}</button>`).join('');
  box.onclick = e => { const b = e.target.closest('button'); if (!b) return; S[key] = b.dataset.v;
    [...box.children].forEach(c => c.setAttribute('aria-pressed', c.dataset.v === S[key])); after(); };
}

/* ---------- view 1: stacked curve ---------- */
function drawStack() {
  const st = D.stacks[S.stack], m = S.measure, steps = st.steps;
  const last = steps[steps.length - 1];
  document.getElementById('stackTitle').textContent = (m === 'h' ? 'Share of SF People Hurt Avoided a Year' : 'Share of SF People Killed or Seriously Hurt Avoided a Year');
  const box = document.getElementById('stackChart');
  const W = Math.max(300, box.clientWidth || 600), phone = W < 520;
  const H = phone ? 300 : Math.min(470, Math.max(320, window.innerHeight - 56 - 150));
  const ml = 44, mr = phone ? 74 : 84, mt = 12, mb = 40;
  const iw = W - ml - mr, ih = H - mt - mb;
  let first = 1e9; for (const k of D.stack_order) first = Math.min(first, D.stacks[k].steps[0].cost);
  const lx0 = Math.floor(Math.log10(first)), x0 = Math.pow(10, lx0), x1 = 1e9;
  const X = v => ml + (Math.log10(Math.max(v, x0)) - lx0) / (9 - lx0) * iw;
  let ylo = 0, yhi = 0.4;
  for (const k of ['area','corner','both']) for (const s of D.stacks[k].steps) { ylo = Math.min(ylo, s.h[0], s.k[0]); yhi = Math.max(yhi, s.h[2], s.k[2]); }
  ylo = Math.floor(ylo * 10) / 10; yhi = Math.ceil(yhi * 10) / 10;
  const Y = v => mt + (yhi - v) / (yhi - ylo) * ih;
  let g = '';
  for (let v = ylo; v <= yhi + 1e-9; v += 0.1) { const y = Y(v); g += `<line x1="${ml}" x2="${ml + iw}" y1="${y}" y2="${y}" stroke="${Math.abs(v) < 1e-9 ? '#9aa3ad' : '#eceff2'}"/><text x="${ml - 6}" y="${y + 4}" text-anchor="end" font-size="11" fill="#59626f">${Math.round(v * 100)}%</text>`; }
  [[1e4,'$10,000'],[1e5,'$100,000'],[1e6,'$1M'],[1e7,'$10M'],[1e8,'$100M'],[1e9,'$1B']].filter(([v]) => v >= x0).forEach(([v, t], i, arr) => { if (phone && arr.length > 4 && i % 2) return; const x = X(v); g += `<line x1="${x}" x2="${x}" y1="${mt}" y2="${mt + ih}" stroke="#eceff2"/><text x="${x}" y="${mt + ih + 16}" text-anchor="middle" font-size="11" fill="#59626f">${t}</text>`; });
  g += `<text x="${ml + iw / 2}" y="${H - 4}" text-anchor="middle" font-size="12" fill="#15181c">Cost a year, all fixes so far (log scale)</text>`;
  // step path: start at the first cost with 0, then up at each step
  const pts = steps.map(s => [X(s.cost), s[m]]);
  const up = [], dn = [];
  let px = X(x0);
  up.push(`M${px},${Y(0)}`);
  steps.forEach((s, i) => { const x = X(s.cost); up.push(`L${x},${Y(i ? steps[i-1][m][2] : 0)}`, `L${x},${Y(s[m][2])}`); });
  up.push(`L${ml + iw},${Y(last[m][2])}`, `L${ml + iw},${Y(last[m][0])}`);
  for (let i = steps.length - 1; i >= 0; i--) { const x = X(steps[i].cost); dn.push(`L${x},${Y(steps[i][m][0])}`, `L${x},${Y(i ? steps[i-1][m][0] : 0)}`); }
  dn.push(`L${px},${Y(0)}Z`);
  g += `<path d="${up.join('') + dn.join('')}" fill="#d4e6e4" opacity="0.9"/>`;
  let line = `M${px},${Y(0)}`;
  steps.forEach((s, i) => { const x = X(s.cost); line += `L${x},${Y(i ? steps[i-1][m][1] : 0)}L${x},${Y(s[m][1])}`; });
  line += `L${ml + iw},${Y(last[m][1])}`;
  g += `<path d="${line}" fill="none" stroke="#2f7d76" stroke-width="2.2"/>`;
  let lastLab = -1e9;
  steps.forEach((s, i) => { const x = X(s.cost), y = Y(s[m][1]), sel = i === S.step;
    const lab = sel || x - lastLab >= 26; if (lab && !sel) lastLab = x;
    g += `<g class="pt" data-i="${i}" style="cursor:pointer"><circle cx="${x}" cy="${y}" r="12" fill="transparent"/>` + (lab
      ? `<circle cx="${x}" cy="${y}" r="${sel ? 9 : 7.5}" fill="${sel ? '#15181c' : '#fff'}" stroke="${sel ? '#15181c' : '#2f7d76'}" stroke-width="1.6"/><text x="${x}" y="${y + 3.6}" text-anchor="middle" font-size="${i >= 9 ? 8.5 : 10}" font-weight="700" fill="${sel ? '#fff' : '#2f7d76'}">${i + 1}</text>`
      : `<circle cx="${x}" cy="${y}" r="3" fill="#2f7d76"/>`) + `</g>`; });
  const ey = Y(last[m][1]);
  const cnt = steps.reduce((a, s) => a + (m === 'h' ? s.dh : s.dk), 0);
  g += `<text x="${ml + iw + 6}" y="${ey - 2}" font-size="${phone ? 15 : 18}" font-weight="700" fill="#2f7d76">${num(cnt)}</text><text x="${ml + iw + 6}" y="${ey + 13}" font-size="10.5" fill="#59626f">fewer, ${pct(last[m][1])}</text>`;
  box.innerHTML = `<svg width="${W}" height="${H}" role="img" aria-label="Share avoided against cost a year">${g}</svg>`;
  box.querySelectorAll('.pt').forEach(p => p.onclick = () => { S.step = +p.dataset.i; drawStack(); drawSteps(true); if (window.innerWidth <= 760) document.querySelector('#stepList .sel').scrollIntoView({ behavior: 'smooth', block: 'center' }); });
}
function drawSteps(scroll) {
  const st = D.stacks[S.stack], m = S.measure;
  const ol = document.getElementById('stepList');
  ol.innerHTML = st.steps.map((s, i) => { const f = F[s.id];
    const v = m === 'h' ? num(s.dh) + ' fewer hurt' : num(s.dk) + ' fewer';
    const per = m === 'h' ? money(s.add / Math.max(s.dh, 1e-9)) + ' per person hurt avoided' : money(s.add / Math.max(s.dk, 1e-9)) + ' per person killed or seriously hurt avoided';
    return `<li data-i="${i}" class="${i === S.step ? 'sel' : ''}"><span class="n">${i + 1}</span><span>${esc(f.name)}${areaTag(s.id)}</span><span class="v">${v}</span>
      <span class="more">${esc(f.how)}<br>About ${per} at this step.</span></li>`; }).join('')
    + (st.not_added.length ? `<li style="cursor:default;display:block;color:#59626f;font-size:12.5px">Not added, because a version of them is already in or they avoid no one on what is left: ${st.not_added.map(i => esc(F[i].name)).join('; ')}.</li>` : '');
  ol.onclick = e => { const li = e.target.closest('li[data-i]'); if (!li) return; S.step = +li.dataset.i; drawStack(); drawSteps(false); };
  if (scroll) { const sel = ol.querySelector('.sel'); if (sel && window.innerWidth > 760) sel.scrollIntoView({ block: 'nearest' }); }
}

/* ---------- view 2: groups ---------- */
function drawGroups() {
  const rows = D.groupings[S.grouping];
  if (!rows.some(r => r.key === S.group)) S.group = rows[0].key;
  const mh = Math.max(...rows.map(r => r.h)), mk = Math.max(...rows.map(r => r.k));
  const t = document.getElementById('groupTable');
  t.innerHTML = `<tr><th></th><th>People hurt</th><th>Killed or seriously hurt</th></tr>` + rows.map(r => `<tr class="row ${r.key === S.group ? 'sel' : ''}" data-k="${esc(r.key)}"><td class="name">${esc(r.label)}${r.sub ? `<small>${esc(r.sub)}</small>` : ''}</td>
    <td><div class="bar"><i style="width:${(r.h / mh * 70).toFixed(1)}%"></i><b>${num(r.h)}</b></div></td>
    <td><div class="bar k"><i style="width:${(r.k / mk * 60).toFixed(1)}%"></i><b>${num(r.k)}</b></div></td></tr>`).join('');
  t.onclick = e => { const tr = e.target.closest('tr.row'); if (!tr) return; S.group = tr.dataset.k; drawGroups(); if (window.innerWidth <= 760) document.getElementById('right').scrollIntoView({ behavior: 'smooth' }); };
  const g = rows.find(r => r.key === S.group);
  let h = `<h2>${esc(g.label)}${g.sub ? ` <span style="font-weight:400;color:#59626f">· ${esc(g.sub)}</span>` : ''}</h2>`;
  if (g.where) h += `<h3>Where These Crashes Happen</h3><p class="note" style="margin:0 0 4px">Places overlap, so the shares add to more than 100%.</p><div class="where">` + g.where.map(([l, v]) => `<span>${esc(l)}</span><div class="bar"><i style="width:${Math.round((v || 0) * 50)}px"></i><b>${pct(v)}</b></div>`).join('') + `</div>`;
  const on = g.fixes.filter(x => !x.why), off = g.fixes.filter(x => x.why);
  h += `<h3>Fixes That Reach It, Most People First</h3>`;
  if (!g.fixes.length) h += `<p class="note">No fix in the research is mapped to this group yet.</p>`;
  h += on.map(x => fixRow(x)).join('') + off.map(x => fixRow(x)).join('');
  document.getElementById('groupDetail').innerHTML = h;
}
function fixRow(x) {
  const f = F[x.id];
  if (x.why) return `<details class="fx off"><summary><span>${esc(f.name)}${areaTag(x.id)}</span><span class="v">Can't count yet</span></summary><dl><dt>Why</dt><dd>${esc(x.why)}</dd><dt>How it works here</dt><dd>${esc(x.mech)}</dd></dl></details>`;
  const v = x.ah ? num(x.ah.mid) + ' a year' : num(x.ak.mid) + ' killed or seriously hurt a year';
  const rng = x.ah ? `${num(x.ah.low)} to ${num(x.ah.high)} people hurt a year` : `${num(x.ak.low)} to ${num(x.ak.high)} killed or seriously hurt a year`;
  const cost = f.cost ? `${money(f.cost.mid)} a year citywide` : 'Not priced';
  const cph = f.cph ? `${money(f.cph.mid)} (${money(f.cph.low)} to ${money(f.cph.high)}), all groups together` : (f.why ? esc(f.why) : 'Not computed');
  return `<details class="fx"><summary><span>${esc(f.name)}${areaTag(x.id)}</span><span class="v">${v}</span></summary><dl>
    <dt>How it works here</dt><dd>${esc(x.mech)}</dd>
    <dt>Reaches</dt><dd>${x.share != null ? pct(x.share) + ' of the group\'s people hurt' : ''}</dd>
    <dt>Effect</dt><dd>${effText(x.eff)}. ${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.src)}</a>` : esc(x.src)}</dd>
    <dt>Range</dt><dd>${rng}</dd>
    <dt>Cost</dt><dd>${cost}</dd>
    <dt>Per person hurt avoided</dt><dd>${cph}</dd></dl></details>`;
}

/* ---------- view 3: ranking ---------- */
function drawRank() {
  const ids = D.ranking.filter(i => S.lever === 'all' || F[i].lever === S.lever);
  if (!ids.includes(S.fix)) S.fix = ids[0] || null;
  const W = window.innerWidth <= 760 ? 112 : 180, lo = 1e2, hi = 1e8, X = v => 18 + (Math.log10(Math.min(Math.max(v, lo), hi)) - 2) / 6 * (W - 36);
  const t = document.getElementById('rankTable');
  t.innerHTML = ids.length ? `<tr><td></td><td style="font-size:11px;color:#59626f"><svg width="${W}" height="14">${[[1e2,'$100'],[1e4,'$10,000'],[1e6,'$1M'],[1e8,'$100M']].filter((_, j) => W > 150 || j !== 0).map(([v,l]) => `<text x="${X(v)}" y="11" text-anchor="middle" font-size="10" fill="#59626f">${l}</text>`).join('')}</svg></td><td></td></tr>` + ids.map(i => { const f = F[i], c = f.cph;
    const zero = c.mid === 0;
    const svg = `<svg width="${W}" height="16"><line x1="${X(lo)}" x2="${X(hi)}" y1="8" y2="8" stroke="#eceff2"/>${zero ? '' : `<line x1="${X(c.low || lo)}" x2="${X(c.high)}" y1="8" y2="8" stroke="#2f7d76" stroke-width="2.5" opacity="0.6"/><circle cx="${X(c.mid)}" cy="8" r="4.5" fill="#2f7d76"/>`}</svg>`;
    return `<tr class="row ${i === S.fix ? 'sel' : ''}" data-i="${i}"><td class="name">${esc(f.name)}${areaTag(i)}</td><td>${svg}</td><td class="v">${zero ? 'No public cost' : money(c.mid)}</td></tr>`; }).join('') : '';
  t.onclick = e => { const tr = e.target.closest('tr.row'); if (!tr) return; S.fix = tr.dataset.i; drawRank(); if (window.innerWidth <= 760) document.getElementById('right').scrollIntoView({ behavior: 'smooth' }); };
  const un = D.unranked.filter(i => S.lever === 'all' || F[i].lever === S.lever);
  document.getElementById('unrTitle').textContent = un.length ? `Not Ranked Yet (${un.length})` : '';
  document.getElementById('unrList').innerHTML = un.map(i => `<li>${esc(F[i].name)}${areaTag(i)}: ${esc(F[i].why)}</li>`).join('');
  const d = document.getElementById('fixDetail');
  if (!S.fix) { d.innerHTML = '<p class="note">No ranked fix of this kind yet; the list under the chart says why.</p>'; return; }
  const f = F[S.fix];
  d.innerHTML = `<p class="note phoneOnly"><a href="#" id="backToList">Back to the list</a></p><h2>${esc(f.full)}${areaTag(S.fix)}</h2><p>${esc(f.how)}</p>
    <div class="fx" style="border:0"><dl>
    <dt>People hurt</dt><dd>${num(f.ah.mid)} fewer a year${rg(f.ah, true)}</dd>
    <dt>Killed or seriously hurt</dt><dd>${num(f.ak.mid)} fewer a year${rg(f.ak, true)}</dd>
    ${f.cost.mid === 0 ? '' : `<dt>Cost</dt><dd>${money(f.cost.mid)} a year (${money(f.cost.low)} to ${money(f.cost.high)})</dd>`}
    ${f.top.length > 1 ? `<dt>Groups it helps most</dt><dd>${f.top.map(([g]) => esc(g)).join('; ')}</dd>` : f.top.length ? `<dt>Group it helps most</dt><dd>${esc(f.top[0][0])}</dd>` : ''}
    ${f.lowconf ? `<dt>Reach uncertain</dt><dd>${esc(f.lowconf)}</dd>` : ''}
    ${f.sf ? `<dt>SF's own result</dt><dd>${esc(f.sf)}</dd>` : ''}
    <dt>Evidence</dt><dd>${esc(f.grade)}</dd>
    <dt>Sources</dt><dd>${f.sources.map(s => `<a href="${esc(s.u)}" target="_blank" rel="noopener">${esc(s.t.length > 90 ? s.t.slice(0, 88) + '…' : s.t)}</a>`).join('<br>')}</dd></dl></div>`;
}

/* ---------- about ---------- */
document.addEventListener('click', e => { if (e.target.id !== 'backToList') return; e.preventDefault();
  const r = document.querySelector('#rankTable tr.sel'); if (r) r.scrollIntoView({ behavior: 'smooth', block: 'center' }); });
function about() {
  const a = D.about;
  const h = `<p>Crashes are SF's injury crashes ${a.years[0]} to ${a.years[1]} from the Transportation Injury Mapping System and DataSF, about ${a.people_year.toLocaleString('en-US')} people hurt and ${a.ksi_year} killed or seriously hurt a year. Places come from DataSF street, signal, stop sign and High Injury Network data read ${esc(a.read)}.</p>
  <p><b>What is stacked.</b> The stacks hold the fixes that go in places: area-wide fixes and corner or corridor fixes. Citywide laws, fleet rules and programs, such as stop-as-yield for people biking, are ranked on their own but not stacked.</p>
  <p><b>Counting rule.</b> A fix's effect comes from its studies, applied to the share of each crash group it reaches. In a stack, each fix acts only on the people the fixes before it left in each group (TRL PPR844), which assumes the effects are independent. Costs are a year: a build cost is spread over its service life, and a fix is priced at every place of its kind in SF. Dollar years are as each source gives them.</p>
  <p><b>What SF's own results did.</b> Where SF has tested a fix on its own streets, its result sets the low end where the studies were more hopeful:</p>
  <ul>${a.sf.map(s => `<li>${esc(s.fixes.join('; '))}: ${esc(s.what)}. Low end set to ${s.low < 0 ? pct(-s.low) + ' more crashes' : s.low === 0 ? 'no effect' : pct(s.low) + ' fewer'}.</li>`).join('')}</ul>
  <p><b>Markers.</b> <i>Area-wide</i>: the fix covers whole neighborhoods or the city rather than chosen corners or streets. <i>At most</i>: SF has no count of the places already treated, so none are netted out and the figure is the most the fix could reach. <i>Reach uncertain</i>: the city data that decides where the fix could go is shaky, so how much of each group it reaches is a rough figure.</p>
  <p><b>Gaps.</b> ${a.computable} of ${a.fixes} fixes can be counted and ${a.ranked} ranked, so the stacks understate what a full package could do. The most common reasons a fix and group can't be counted:</p>
  <ul>${a.gaps.map(([t, n]) => `<li>${esc(t)}: ${n}</li>`).join('')}</ul>
  <p><b>Injury values.</b> ${a.values.map(v => v.u.startsWith('http') ? `<a href="${esc(v.u)}" target="_blank" rel="noopener">${esc(v.t)}</a>` : esc(v.t)).join('; ')}.</p>`;
  document.querySelectorAll('.aboutBody').forEach(b => b.innerHTML = h);
}

/* ---------- wiring ---------- */
function setView(v) { S.view = v;
  document.querySelectorAll('nav button').forEach(x => x.setAttribute('aria-pressed', x.dataset.view === S.view));
  document.querySelectorAll('.view, .ctl').forEach(x => x.classList.toggle('on', x.dataset.for === S.view)); }
document.querySelector('nav').onclick = e => { const b = e.target.closest('button'); if (!b) return; setView(b.dataset.view);
  history.replaceState(null, '', S.view === 'stack' ? location.pathname : '#' + S.view); render(); };
if (['groups', 'rank'].includes(location.hash.slice(1))) setView(location.hash.slice(1));
chips('stackChips', D.stack_order.map(k => [k, D.stacks[k].label]), 'stack', () => { S.step = 0; render(); });
chips('measureChips', [['h', 'People hurt'], ['k', 'Killed or seriously hurt']], 'measure', render);
chips('groupChips', [['family', 'Crash type'], ['place', 'Place'], ['who', 'Who was hurt']], 'grouping', () => { S.group = null; render(); });
chips('leverChips', [['all', 'All']].concat(D.levers.filter(([k]) => D.ranking.some(i => F[i].lever === k))), 'lever', render);
function render() { if (S.view === 'stack') { drawStack(); drawSteps(false); } else if (S.view === 'groups') drawGroups(); else drawRank(); }
about(); render();
let rt; window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(render, 120); });
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--profiles", default=DEFAULT_PROFILES, help="folder with fix-map.json, fix-reach.json, results.json")
    ap.add_argument("--out", default=None, help="output HTML (default <profiles>/fix-explorer.html)")
    a = ap.parse_args()
    data = build(a.profiles)
    blob = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    out = a.out or os.path.join(a.profiles, "fix-explorer.html")
    page = PAGE.replace("__DATA__", blob)
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    print("wrote %s (%d bytes, %d fixes, %d ranked)" % (os.path.relpath(out, ROOT) if out.startswith(ROOT) else out,
                                                     len(page.encode("utf-8")), len(data["fixes"]), len(data["ranking"])))


if __name__ == "__main__":
    sys.exit(main())
