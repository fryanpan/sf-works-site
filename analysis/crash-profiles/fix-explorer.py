#!/usr/bin/env python3
"""Build the crash fix explorer, one self-contained HTML page of SF crash groups, the fixes mapped to them, their cost per person hurt avoided and stacked packages.

Reads out/crash-augment/profiles/fix-map.json, fix-groups.json, fix-reach.json
and results.json (written by fix-map.py, fix-groups.py, fix-reach.py and
crash-profiles.py) and writes
out/crash-augment/profiles/fix-explorer.html with the data inlined as JSON and
plain SVG and HTML for the charts, so it opens with no network.

    python3 analysis/crash-profiles/fix-explorer.py [--profiles DIR] [--out FILE]

--profiles names the folder holding the four inputs (default this repo's
out/crash-augment/profiles), so the page can be rebuilt on revised numbers.

The three stacks come from fix-map.json's stacks (area_wide_only,
corner_and_corridor_only, area_wide_and_corner_corridor), which carry the mid
only. The low and high band is recounted here in the same order with the same
sequential rule (remaining = product of 1 - share x r within each of the 45
mode x family groups), from each fix's stack_terms in fix-map.json. The recount must reproduce
fix-map.json's mid at every step to 0.05 people and 0.005 KSI people, or the
script stops: a band that does not match the line it surrounds would be wrong.

The Crash Groups view offers every grouping in fix-groups.json. A grouping with
more than GROUP_ROWS + 1 groups shows its GROUP_ROWS biggest named groups (no
catch-all value) and one row over the rest, so the rows add to everyone hurt.
A row's fixes are the people each fix avoids in that row's crashes, as
fix-groups.py spreads them crash by crash, so a fix's rows in any grouping add
to its total. The years and the yearly average come from results.json.

Standard library only. A second run on the same inputs writes the same bytes.
"""

import argparse
import json
import math
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_PROFILES = os.path.join(ROOT, "out", "crash-augment", "profiles")
YEARS = None  # the number of collision years in results.json, set in build()
CATCH = {"not stated", "unknown", "other", "Other", "Not Stated", "not stated or other", "age not stated",
         "time not stated", "role not stated", "0 (layer gap)"}
GROUP_ROWS = 12  # named groups shown per grouping before the "All other" row
MIN_SHOWN = (0.05, 0.005)  # a fix is listed on a row when it avoids this many people hurt or KSI people a year there

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
MODES = {"vehicles only": "Vehicles only", "pedestrian involved": "Someone walking hit", "bicycle involved": "Crash with someone biking"}
# A violation is the crash's primary collision factor, which police assign to the party at fault. VERBS says it with
# the actor in front ("Driver speeding"); NOUNS without one, for a family no one party type dominates.
VERBS = {
    "unsafe speed": "speeding", "following too closely": "following too closely",
    "dooring": "opening a door into traffic", "unsafe starting or backing": "starting or backing unsafely",
    "failure to yield to pedestrian": "failing to yield to someone walking",
    "vehicle right of way": "failing to yield right of way", "red light": "running a red light",
    "stop sign or other sign": "running a stop sign or other sign", "pedestrian violation": "crossing against the rules",
    "DUI": "under the influence", "unsafe turn or lane use": "turning or changing lanes unsafely",
    "bike or scooter rules": "breaking a bike or scooter rule", "phone use": "using a phone",
}
NOUNS = {
    "DUI": "Driving under the influence", "not stated": "Cause not stated", "other": "Other violation",
    "failure to yield to pedestrian": "Failure to yield to someone walking",
    "pedestrian violation": "Violation by the person walking", "unsafe turn or lane use": "Unsafe turn or lane change",
    "bike or scooter rules": "Bike or scooter rule broken",
}
ACTORS = {"Driver": "Driver", "Pedestrian": "Person walking", "Bicyclist": "Bicyclist",
          "Parked Vehicle": "Parked car's occupant", "Other": "Scooter rider or other"}
ACTOR_LOW = {"Driver": "driver", "Pedestrian": "person walking", "Bicyclist": "bicyclist",
             "Parked Vehicle": "parked car's occupant", "Other": "scooter rider or other"}
DOMINANT = 0.8  # one at-fault party type holding more than this share of a family's people hurt names the actor
DRIVER_ALL = 0.97  # at or above this driver share the row carries no at-fault line
ROLES = {"pedestrian": "Person walking", "bicyclist": "Person biking", "driver": "Driver", "passenger": "Passenger",
         "scooter or other": "Scooter rider or other", "role not stated": "Role not stated"}
AGES = {"child under 18": "under 18", "adult 18 to 64": "18 to 64", "65 and over": "65 and over", "age not stated": "age not stated"}
TURNS = {"going straight": "going straight", "left or U-turn": "turning left or U-turning", "right turn": "turning right",
         "other movement": "other movement", "not stated or other": "movement not stated"}
STRESS = {"high (LTS 3-4)": "High bike traffic stress", "low (LTS 1-2)": "Low bike traffic stress",
          "unknown": "Bike traffic stress not known"}
ONE_FIELD = {
    "speed_limit": {"25 or under": "Posted 25 mph or under", "30": "Posted 30 mph", "35 or more": "Posted 35 mph or more",
                    "unknown": "Speed limit not known"},
    "lanes": {"1": "1 lane", "2": "2 lanes", "3 or more": "3 or more lanes", "0 (layer gap)": "Not in SFMTA's lanes layer",
              "unknown": "Lanes not known"},
    "light": {"daylight": "Daylight", "dusk or dawn": "Dusk or dawn", "dark": "Dark", "not stated": "Light not stated"},
    "epc": {"in EPC": "In an Equity Priority Community", "outside EPC": "Outside Equity Priority Communities",
            "unknown": "Not known"},
    "weight": {"under 3,500 lb": "Heaviest vehicle under 3,500 lb", "3,500 to 5,000 lb": "Heaviest vehicle 3,500 to 5,000 lb",
               "over 5,000 lb": "Heaviest vehicle over 5,000 lb", "no weight": "No vehicle weight on record"},
}
# The Crash Groups select, in this order: fix-groups.json grouping id and its label.
GROUPINGS = [
    ("family", "Violation and who was hit"), ("hybrid", "Crash type"), ("hybrid_turn", "Crash type and turn"),
    ("place", "Place"), ("what_where", "Violation and bike traffic stress"), ("who", "Who was hurt, by age"),
    ("who_what", "Who was hurt, by violation"), ("time", "Time of day"), ("light", "Light"),
    ("speed_limit", "Speed limit"), ("lanes", "Number of lanes"), ("weight", "Heaviest vehicle's weight"),
    ("epc", "Equity Priority Community"),
]
NOTES = {
    "family": ["The violation is the crash's primary collision factor, which police assign to the party at fault."],
    "place": ["Road class is DataSF 3psu-pn9h's classcode (2 major, 3 arterial, 4 collector, 5 residential); at an intersection, the most major street meeting there.",
              "High bike traffic stress is SFMTA's Bike Comfort Index LTS 3 or 4 on any block the crash touches. LTS rises with posted speed, lanes and traffic volume, and falls with separated bike lanes."],
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


def cap(t):
    return t[:1].upper() + t[1:]


class Labels(object):
    """Row labels. A family's actor comes from results.json's by_at_fault_party_type: the party type holding most of
    its people hurt names the actor when it holds more than DOMINANT; otherwise the violation is named alone, with the
    driver's share."""

    def __init__(self, res):
        self.fault = {}
        for f in res["size_families"]["families"]:
            a = f.get("by_at_fault_party_type", {}).get("people_injured") or {}
            t = sum(a.values())
            self.fault["%s | %s" % (f["mode"], f["violation"])] = {k: v / t for k, v in a.items()} if t else {}

    def violation(self, mode, viol, actor=True):
        """(label, at-fault line or None) for a mode x violation family."""
        shares = self.fault.get("%s | %s" % (mode, viol), {})
        noun = NOUNS.get(viol, cap(viol))
        if viol not in VERBS or not shares or not actor:
            return noun, None
        top, top_share = max(shares.items(), key=lambda kv: (kv[1], kv[0]))
        drv = shares.get("Driver", 0.0)
        others = sorted(((v, k) for k, v in shares.items() if k != "Driver" and v >= 0.02), reverse=True)
        if top_share > DOMINANT and top in ACTORS:
            label = "%s %s" % (ACTORS[top], VERBS[viol])
            if drv >= DRIVER_ALL:
                return label, None
            parts = ["%s at fault in %d%%" % (ACTORS[top], round(100 * top_share))]
            parts += ["%s %d%%" % (ACTOR_LOW[k], round(100 * v)) for k, v in sorted(
                ((k, v) for k, v in shares.items() if k != top and v >= 0.02), key=lambda kv: -kv[1])]
            return label, ", ".join(parts)
        label = "%s (driver at fault in %d%%)" % (noun, round(100 * drv))
        line = ", ".join("%s at fault in %d%%" % (ACTORS.get(k, k), round(100 * v)) if i == 0 else "%s %d%%" % (ACTOR_LOW.get(k, k), round(100 * v))
                         for i, (v, k) in enumerate(others))
        return label, line or None

    def mode_sub(self, mode, viol=None):
        if mode == "bicycle involved" and viol is not None:
            shares = self.fault.get("%s | %s" % (mode, viol), {})
            if shares.get("Driver", 0.0) > DOMINANT:
                return "Someone biking hit"
        return MODES.get(mode, cap(mode))

    def family(self, name):
        """(label, sub, at-fault line) for a family name, or the chart's remainder."""
        if name == "all other families":
            return "All other crashes", "", None
        mode, _, viol = name.partition(" | ")
        label, line = self.violation(mode, viol)
        return label, self.mode_sub(mode, viol), line

    def row(self, gid, key):
        """(label, sub, at-fault line) for a fix-groups.json group key."""
        if gid == "family":
            return self.family(" | ".join(key))
        if gid == "who":
            return "%s, %s" % (ROLES.get(key[0], cap(key[0])), AGES.get(key[1], key[1])), "", None
        if gid == "who_what":
            return self.violation(None, key[1], actor=False)[0], "%s hurt" % ROLES.get(key[0], cap(key[0])), None
        if gid == "place":
            stress, cls, where = key
            if cls in ("unknown", "other", ""):
                label = "%s, street class not known" % cap(where)
            else:
                art = "an" if cls[:1] in "aeiou" else "a"
                label = "%s on %s %s street" % ("Intersection" if where == "intersection" else "Midblock", art, cls)
            return label, STRESS.get(stress, stress), None
        if gid == "time":
            mode, band, day = key
            label = cap(band)
            if not band.startswith(("weekday", "weekend")):
                label += ", " + day
            return label, MODES.get(mode, cap(mode)), None
        if gid in ("hybrid", "hybrid_turn"):
            mode = key[0]
            if mode == "vehicles only":
                return cap(key[1].lower()), MODES[mode], None
            label, sub, line = self.family("%s | %s" % (mode, key[1]))
            if gid == "hybrid_turn":
                # the movement is the at-fault party's, or the first driver's when a person walking was at fault
                shares = self.fault.get("%s | %s" % (mode, key[1]), {})
                who = "driver " if shares.get("Pedestrian", 0.0) > DOMINANT else ""
                label += ", " + who + TURNS.get(key[2], key[2])
            return label, sub, line
        if gid == "what_where":
            label, sub, line = self.family("%s | %s" % (key[0], key[1]))
            return label, sub + " · " + STRESS.get(key[2], key[2]), line
        if gid in ONE_FIELD:
            return ONE_FIELD[gid].get(key[0], cap(key[0])), "", None
        return " / ".join(key), "", None


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


def sig3(x):
    """x to three significant figures, enough for the two the page prints."""
    if not x:
        return 0
    return round(x, max(0, 2 - int(math.floor(math.log10(abs(x))))))


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
def stack_terms(fix):
    """{family: [(share hurt, share KSI, effect)]}, fix-map.json's stack_terms ("all other families" already spread)."""
    return {g: [(t["share_hurt"], t["share_ksi"], t["effect"]) for t in ts] for g, ts in (fix.get("stack_terms") or {}).items()}


def recount(order, fixes, fam, q):
    rem = {g: [1.0, 1.0] for g in fam}
    out, ch, ck = [], 0.0, 0.0
    for fid in order:
        dh = dk = 0.0
        for g, ts in stack_terms(fixes[fid]).items():
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
    global YEARS
    fm = load(os.path.join(profiles, "fix-map.json"))
    fg = load(os.path.join(profiles, "fix-groups.json"))
    fr = load(os.path.join(profiles, "fix-reach.json"))
    res = load(os.path.join(profiles, "results.json"))
    years = res["years"]
    if fm["inputs"]["years"] != years or fg["years"] != years or fr["years"] != years:
        raise SystemExit("fix-explorer: inputs are for different years; rerun fix-reach.py, fix-map.py, fix-groups.py")
    YEARS = years[1] - years[0] + 1
    labels = Labels(res)
    fixes = {f["id"]: f for f in fm["fixes"]}
    fam = {g["group"]: g for g in fm["groups"]}
    remainder = sorted(g for g, v in fam.items() if not v["in_chart"])
    year_h = fm["inputs"]["people_hurt_total"] / YEARS
    year_k = fm["inputs"]["ksi_total"] / YEARS

    stacks = {}
    for key, src, label in STACKS:
        st = fm["stacks"][src]
        order = [s["id"] for s in st["steps"]]
        mid = recount(order, fixes, fam, "mid")
        for s, (h, k) in zip(st["steps"], mid):
            if abs(h - s["cumulative_hurt_avoided"]) > 0.05 or abs(k - s["cumulative_ksi_avoided"]) > 0.005:
                raise SystemExit("fix-explorer: recount of %s step %d (%s) gives %.2f hurt, fix-map.json %.2f; band not drawn"
                                 % (src, s["step"], s["id"], h, s["cumulative_hurt_avoided"]))
        lo = recount(order, fixes, fam, "low")
        hi = recount(order, fixes, fam, "high")
        steps = []
        for s, l, h in zip(st["steps"], lo, hi):
            steps.append({
                "id": s["id"], "cost": s["cumulative_annual_cost"], "add": s["annual_cost"],
                "h": [r3(l[0] / year_h), s["share_of_people_hurt_avoided"], r3(h[0] / year_h)],
                "k": [r3(l[1] / year_k), s["share_of_ksi_avoided"], r3(h[1] / year_k)],
                "dh": round(s["marginal_hurt_avoided"], 1), "dk": round(s["marginal_ksi_avoided"], 2),
            })
        stacks[key] = {"label": label, "steps": steps, "not_added": st["not_added"]}

    # groups: every grouping in fix-groups.json, each row with the fixes that reach its crashes
    def where_of(names):
        tot_h = sum(fr["groups"][n]["people_hurt"] for n in names)
        out = []
        for place, label in WHERE:
            ph = sum(fr["groups"][n]["places"][place]["people_hurt"] for n in names)
            out.append([label, r3(ph / tot_h) if tot_h else None])
        return out

    mapped = {}  # fix-map.json group name -> {fix id: rows}, for the fixes mapped there that can't be counted
    for f in fm["fixes"]:
        for r in f["groups"]:
            g = r["group"]
            m = re.match(r"pedestrian \| (.*?) \(cross-cut", g)
            g = "who | pedestrian | " + m.group(1) if m else g
            mapped.setdefault(g, {}).setdefault(f["id"], []).append(r)

    refs = {}

    def ref(fid, row_i):
        """The id of the mechanism, effect and source shown for a fix on a row, from its fix-map.json row."""
        key = "%s:%s" % (fid, -1 if row_i is None else row_i)
        if key not in refs:
            fix = fixes[fid]
            r = fix["groups"][row_i] if row_i is not None else {}
            refs[key] = {"mech": feet(r.get("mechanism") or fix.get("how_it_works")),
                         "eff": effect_text(r.get("effect_fraction")),
                         "src": feet((r.get("effect") or {}).get("source")),
                         "url": source_link(fix, (r.get("effect") or {}).get("source"))}
        return key

    def fix_list(members, people, mapped_keys):
        """The counted fixes over fix-groups.json groups `members`, then the mapped fixes that can't be counted."""
        acc = {}
        for g in members:
            for fid, v in g["fixes"].items():
                a = acc.setdefault(fid, {"h": [0.0] * 3, "k": [0.0] * 3, "reached": 0.0, "best": (-1.0, None)})
                for j in range(3):
                    a["h"][j] += v["hurt"][j]
                    a["k"][j] += v["ksi"][j]
                a["reached"] += v["reached_hurt"]
                if v["hurt"][1] > a["best"][0]:
                    a["best"] = (v["hurt"][1], v["row"])
        out = []
        for fid, a in sorted(acc.items()):
            if abs(a["h"][1]) < MIN_SHOWN[0] and abs(a["k"][1]) < MIN_SHOWN[1]:
                continue
            ref(fid, a["best"][1])
            out.append({"id": fid, "h": [sig3(x) for x in a["h"]] if any(a["h"]) else None, "k": [sig3(x) for x in a["k"]],
                        "s": r3(a["reached"] / people) if people else None, "r": -1 if a["best"][1] is None else a["best"][1]})
        shown = {x["id"] for x in out}
        for mk in mapped_keys:
            for fid, rows in sorted(mapped.get(mk, {}).items()):
                if fid in shown or fid in acc:
                    continue
                shown.add(fid)
                r0 = next((r for r in rows if r.get("reason")), rows[0])
                why = plain_reason(r0.get("reason")) or plain_reason((fixes[fid].get("not_computable_reasons") or [None])[0]) \
                    or "Not counted"
                out.append({"id": fid, "why": why, "mech": feet(r0.get("mechanism") or fixes[fid].get("how_it_works"))})
        out.sort(key=lambda x: ("why" in x, -((x.get("h") or [0, 0])[1]), -((x.get("k") or [0, 0])[1]), x["id"]))
        return out

    def stack_end(members):
        out = {}
        for key, src, _ in STACKS:
            out[key] = [round(sum(sum(g["stacks"][src]["hurt"]) for g in members), 1),
                        round(sum(sum(g["stacks"][src]["ksi"]) for g in members), 2)]
        return out

    def make_row(gid, key, members, label, sub, line, where, mapped_keys):
        h = sum(g["people_hurt"] for g in members)
        k = sum(g["ksi"] for g in members)
        return {"key": key, "label": label, "sub": sub, "at": line, "h": round(h / YEARS), "k": round(k / YEARS, 1),
                "where": where, "fixes": fix_list(members, h, mapped_keys), "st": stack_end(members)}

    fg_by = {g["id"]: g for g in fg["groupings"]}
    if sorted(gid for gid, _ in GROUPINGS) != sorted(fg_by):
        raise SystemExit("fix-explorer: GROUPINGS does not name every grouping in fix-groups.json")
    groupings = {}
    fam_groups = {" | ".join(g["key"]): g for g in fg_by["family"]["groups"]}
    rows = []
    for c in res["size_families"]["chart"]:
        name = "all other families" if c["mode"] == "all other families" else "%s | %s" % (c["mode"], c["violation"])
        members = remainder if name == "all other families" else [name]
        label, sub, line = labels.family(name)
        row = make_row("family", name, [fam_groups[m] for m in members], label, sub, line, where_of(members), [name])
        if name != "all other families" and row["h"] != round(c["people_injured"] / YEARS):
            raise SystemExit("fix-explorer: family %s differs between results.json and fix-groups.json" % name)
        rows.append(row)
    groupings["family"] = rows
    prefixes = {"place": "place | ", "who": "who | "}
    for gid, _ in GROUPINGS:
        if gid == "family":
            continue
        gs = fg_by[gid]["groups"]
        if len(gs) <= GROUP_ROWS + 1:
            shown, rest = gs, []
        else:
            named = [g for g in gs if not any(v in CATCH for v in g["key"])]
            shown = named[:GROUP_ROWS]
            rest = [g for g in gs if g not in shown]
        rows = []
        for g in shown:
            label, sub, line = labels.row(gid, g["key"])
            key = " | ".join(g["key"])
            rows.append(make_row(gid, gid + " | " + key, [g], label, sub, line, None,
                                 [prefixes[gid] + key] if gid in prefixes else []))
        if rest:
            rows.append(make_row(gid, gid + " | rest", rest, "All other %s" % ("people hurt" if fg_by[gid]["unit"] == "person" else "crashes"),
                                 "%d smaller groups%s" % (len(rest), ", and those not stated" if any(any(v in CATCH for v in g["key"]) for g in rest) else ""),
                                 None, None, []))
        groupings[gid] = rows

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
            "top": [["%s (%s)" % (labels.family(g)[0], labels.family(g)[1].lower()), round(v, 1)] for g, v in top[:3] if v > 0],
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
    return {"stack_order": [k for k, _, _ in STACKS], "stacks": stacks, "groupings": groupings,
            "grouping_order": [[gid, label] for gid, label in GROUPINGS], "notes": NOTES, "refs": refs,
            "fixes": fx, "ranking": ranking, "unranked": unranked, "levers": LEVERS, "about": about}


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
select { font:inherit; width:100%; padding:5px 8px; border:1px solid var(--line); border-radius:6px; background:#fff; color:var(--ink); margin:2px 0 8px; }
label.label { display:block; }
#groupNote p { color:var(--muted); font-size:12px; margin:0 0 6px; }
.gb .name small.at { color:#6b4e00; }
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
      <label class="label" for="groupSel">Group crashes by</label>
      <select id="groupSel"></select>
      <div id="groupNote"></div>
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
      <p class="note" id="groupFoot"></p>
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
  document.getElementById('groupNote').innerHTML = (D.notes[S.grouping] || []).map(t => `<p>${esc(t)}</p>`).join('');
  document.getElementById('groupFoot').textContent = `SF crashes ${D.about.years[0]} to ${D.about.years[1]}, a yearly average. Tap a group to see the fixes that reach it.`;
  if (!rows.some(r => r.key === S.group)) S.group = rows[0].key;
  const mh = Math.max(...rows.map(r => r.h)), mk = Math.max(...rows.map(r => r.k));
  const t = document.getElementById('groupTable');
  t.innerHTML = `<tr><th></th><th>People hurt</th><th>Killed or seriously hurt</th></tr>` + rows.map(r => `<tr class="row ${r.key === S.group ? 'sel' : ''}" data-k="${esc(r.key)}"><td class="name">${esc(r.label)}${r.sub ? `<small>${esc(r.sub)}</small>` : ''}${r.at ? `<small class="at">${esc(r.at)}</small>` : ''}</td>
    <td><div class="bar"><i style="width:${(r.h / mh * 70).toFixed(1)}%"></i><b>${num(r.h)}</b></div></td>
    <td><div class="bar k"><i style="width:${(r.k / mk * 60).toFixed(1)}%"></i><b>${num(r.k)}</b></div></td></tr>`).join('');
  t.onclick = e => { const tr = e.target.closest('tr.row'); if (!tr) return; S.group = tr.dataset.k; drawGroups(); if (window.innerWidth <= 760) document.getElementById('right').scrollIntoView({ behavior: 'smooth' }); };
  const g = rows.find(r => r.key === S.group);
  let h = `<h2>${esc(g.label)}${g.sub ? ` <span style="font-weight:400;color:#59626f">· ${esc(g.sub)}</span>` : ''}</h2>`;
  if (g.at) h += `<p class="note" style="margin:0 0 6px">${esc(g.at)}</p>`;
  const se = g.st[S.stack], sv = S.measure === 'h' ? se[0] : se[1], base = S.measure === 'h' ? g.h : g.k;
  const stackWho = { area: 'every area-wide fix', corner: 'every corner and corridor fix', both: 'every area-wide, corner and corridor fix' }[S.stack];
  h += `<p class="note" style="margin:4px 0 0">Stacked, ${stackWho}: ${num(sv)} fewer ${S.measure === 'h' ? 'people hurt' : 'killed or seriously hurt'} a year here${base ? ', ' + pct(sv / base) + ' of this group' : ''}.</p>`;
  if (g.where) h += `<h3>Where These Crashes Happen</h3><p class="note" style="margin:0 0 4px">Places overlap, so the shares add to more than 100%.</p><div class="where">` + g.where.map(([l, v]) => `<span>${esc(l)}</span><div class="bar"><i style="width:${Math.round((v || 0) * 50)}px"></i><b>${pct(v)}</b></div>`).join('') + `</div>`;
  const on = g.fixes.filter(x => !x.why), off = g.fixes.filter(x => x.why);
  h += `<h3>Fixes That Reach It, Most People First</h3>`;
  if (!g.fixes.length) h += `<p class="note">No fix in the research is mapped to this group yet.</p>`;
  h += on.map(x => fixRow(x)).join('') + off.map(x => fixRow(x)).join('');
  document.getElementById('groupDetail').innerHTML = h;
}
function fixRow(x) {
  const f = F[x.id];
  if (!x.why) x = Object.assign({}, D.refs[x.id + ':' + x.r], x, { ah: x.h ? { low: x.h[0], mid: x.h[1], high: x.h[2] } : null,
    ak: { low: x.k[0], mid: x.k[1], high: x.k[2] }, share: x.s });
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
const gsel = document.getElementById('groupSel');
gsel.innerHTML = D.grouping_order.map(([v, t]) => `<option value="${esc(v)}">${esc(t)}</option>`).join('');
gsel.value = S.grouping;
gsel.onchange = () => { S.grouping = gsel.value; S.group = null; render(); };
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
