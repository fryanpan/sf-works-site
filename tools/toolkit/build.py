"""Build site/data/toolkit/tools.json and the toolkit PlotChart MDX files (760 wide and a 390 phone variant)
from tools_src.py. Run: python3 tools/toolkit/build.py (the MDX goes to .cache/toolkit/)"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import json, os, sys, textwrap
sys.path.insert(0, os.path.dirname(__file__))
from tools_src import TOOLS

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT

FIELDS = {
  "id": "Stable kebab-case id. Never changes once published.",
  "name": "Display name.",
  "short_name": "Optional shorter label used in the chart's row heading.",
  "group": "'spot' = spot fixes at corners, crossings and blocks; 'network' = network tools SF mostly lacks; 'programs' = enforcement and programs; 'muni' = Muni service.",
  "one_line": "Plain-language description for a reader who has never heard the term.",
  "cost": "{text, short, value_low, value_high (USD, null when not found or not a dollar cost), unit, source_url, source_title (with provenance tag): the unit cost; per_sq_mi: {quantity_text (what is placed where in a typical square mile, see _square_mile), unit_cost, total_low, total_high (USD), per_year (true for a recurring cost), working (quantity × unit cost = total, generated from the numbers and checked against the totals), band ('$' | '$$' | '$$$' from _bands, computed by build.py from the totals; 'revenue' when the tool raises money; 'unknown' when no cost was found), assumptions, sources [{title, url}]}}.",
  "effect": "{area: {pct (signed percent change in all injury crashes across a typical square mile when the tool is built everywhere per_sq_mi puts it; null when no study), local_pct (the study's effect where the tool goes), share (percent of SF injury crashes 2022-2025 at those places, see _shares_note), share_key, treat (share of those places treated), terms (each term's local, share, label, treat, treat_words, value; the effect is their sum), cell (table text when there is no single figure), note (the study, in plain sentences), working (the arithmetic, generated from the numbers), text (note + working)}, text, short (chart cell), pct (signed percent change, negative = fewer; null when no study measured it), outcome ('deaths+serious' | 'all injuries' | 'crashes' | 'pedestrian casualties, all severities'), design ('controlled' | 'before-after' | 'cross-sectional' | 'meta-analysis' | 'not stated'; outcome and design null when pct is null and no study exists), where, source_url, source_title}.",
  "opposition": "{grade 'Low' | 'Medium' | 'High' from SF's own record, or 'Untested' when SF has no record, reason (one line), examples [{text, url}]}. Grades marked [inference — mine] in the reason have no direct SF record.",
  "programs": "{safe_school_connections, safe_routes, street_safety_initiative}: each null (absent) or {status 'in' | 'considered' | 'limits', source_url, note, quote (required for 'limits': the limiting words, verbatim from the source)}. 'in' = adopted, built or ordered; 'considered' = a pilot, a draft plan, an in-progress action or an urging resolution; 'limits' = the plan opposes or severely limits the tool. No Street Safety Initiative document attaches dollars, so none is marked funded.",
  "sfmta_use": "{text, url} or null: the SFMTA program that delivers the tool today.",
  "legal": "Present when state law caps or blocks the tool: {text (with the statute's words quoted), sources [{title, url}]}. cost.per_sq_mi.net, when present, is the cost net of revenue in words.",
  "coverage": "{pct (0-100, share of the places per_sq_mi counts, citywide, that have the tool today; null when no count exists), label (cell text: '65%', '<1%', '~35%' for our estimate, 'no count'), text (the count behind it), url}. See _coverage_rule.",
  "programs_defs": "safe_school_connections = SFMTA Safe School Connections Draft Approach, Sept 2026 (toolkit and the school programs it coordinates). safe_routes = SF Safe Routes to School, 2024-25 annual report incl. section X on SFMTA work. street_safety_initiative = Mayor's ED 25-06 status page, Board Res. 437-25 (Street Safety Act), SFMTA Street Safety Commitments deck of 2026-01-20.",
  "sf_example": "{name, year, lat, lon (WGS84; for a segment, its midpoint), geometry_hint ('point' | 'street segment: ... from (lat,lon) to (lat,lon)' | 'area: ...'), source_url}. Intersection coordinates are DataSF street centerline endpoints (3psu-pn9h), queried 2026-10-23. null when SF has no example.",
  "nearest_example": "Present only when sf_example is null: {city, name, url}.",
  "by_user": "{walking, biking, transit, driving, kids_school_trip}: each {pros, cons, evidence_url (null when none), evidence_note}. 'None measured.' means no source opened says anything; '[inference — mine]' marks our own reading.",
}
PROG_KEYS = ["safe_school_connections", "safe_routes", "street_safety_initiative"]
COVERAGE_RULE = ("Built today: the share of the places a tool fits, citywide, that have it now, counting the same places the "
                 "cost column counts (for example 65% of intersections daylit); each info box names the count it is out of. "
                 "Counts come from DataSF and SFMTA inventories where they exist; ~ marks our estimate, and 'no count' means none is published.")

def write_json():
    tools = []
    for t in TOOLS:
        t = dict(t)
        t.setdefault("nearest_example", None)
        tools.append(t)
    from tools_src import BANDS, SQUARE_MILE, LISTS, SKIPPED, SHARES_NOTE
    for t in tools:
        q = t["cost"]["per_sq_mi"]
        if q["band"] not in ("revenue", "unknown"):
            # The band is computed from the figure, never typed by hand; a recurring cost counts ten years.
            v = (q["total_low"] + (q.get("total_high") or q["total_low"])) / 2 * (10 if q.get("per_year") else 1)
            q["band"] = next(k for k, c in BANDS["cutoffs"].items() if c["max"] is None or v < c["max"])
    out = {"_fields": FIELDS, "_read": "2026-10-22 to 2026-10-23", "_bands": BANDS, "_square_mile": SQUARE_MILE,
           "_coverage_rule": COVERAGE_RULE, "_shares_note": SHARES_NOTE, "_lists": LISTS, "_skipped": SKIPPED, "tools": tools}
    # The site reads site/data/toolkit/tools.json; TOOLKIT_OUT points the build at a worktree's copy.
    path = os.environ.get("TOOLKIT_OUT") or f"{ROOT}/site/data/toolkit/tools.json"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, sort_keys=False)
        f.write("\n")

OPP_FILL = {"Low": "#dbe4f5", "Medium": "#9db3e3", "High": "#4269d0", "Untested": "#f4f6f8"}
OPP_TEXT = {"Low": "#15181c", "Medium": "#15181c", "High": "#ffffff", "Untested": "#59626f"}
INK, GRAY, RULE = "#15181c", "#59626f", "#e3e6ea"
DESIGN = {"controlled": "controlled study", "before-after": "before-after", "before-after with citywide comparison": "before-after vs. citywide", "cross-section": "cross-sectional", "model": "our model", "case-control": "case-control", "cross-sectional": "cross-sectional", "meta-analysis": "meta-analysis", "not stated": "design not stated", None: ""}

def wrap(s, n):
    return "\n".join(textwrap.wrap(s, n)) if s else ""

def chart(layout):
    L = layout
    rows, cells, sub, opp, dots, holes, grp, rules, dashes, cov = [], [], [], [], [], [], [], [], [], []
    y = L["top"]
    for g, label in [("spot", "Spot fixes"), ("network", "Network tools SF mostly lacks"), ("programs", "Enforcement and programs"), ("muni", "Muni service")]:
        grp.append({"x": L["x_tool"], "y": y + 14, "t": label})
        y += L["grp_h"]
        for t in [t for t in TOOLS if t["group"] == g]:
            yc = y + L["row_h"] / 2
            rules.append({"y": y + L["row_h"]})
            name = wrap(t.get("short_name", t["name"]), L["w_tool"])
            e = t["effect"]
            def block(x, main, subt, ttl1, ttl2, into):
                n = main.count("\n") + 1
                top = yc - (n + 1) * 6.5
                into.append({"x": x, "y": top + n * 6.5, "t": main, "ttl": ttl1})
                if subt:
                    sub.append({"x": x, "y": top + n * 13 + 6.5, "t": subt, "ttl": ttl2})
            if L.get("cost_under_name"):
                block(L["x_tool"], name, (t["cost"]["per_sq_mi"]["band"]).replace("-", "\u2013"), t["one_line"], t["cost"]["text"], rows)
            else:
                rows.append({"x": L["x_tool"], "y": yc, "t": name, "ttl": t["one_line"]})
                cells.append({"x": L["x_cost"], "y": yc, "t": wrap((t["cost"]["per_sq_mi"]["band"]).replace("-", "\u2013"), L["w_cost"]), "ttl": t["cost"]["text"]})
            a = e.get("area") or {}
            short = (f"{a['pct']:+.{2 if abs(a['pct']) < 1 else 1}f}% injuries" if a.get("pct") is not None else (a.get("cell") or e["short"]))
            short = ("\u2212" + short[1:] if short.startswith("-") else short).replace("to -", "to \u2212").replace("Up to -", "Up to \u2212")
            if e["pct"] is None and not e["where"]:
                st = "no injury study"
            elif e["pct"] is None:
                st = e["where"] + ", " + DESIGN[e["design"]] + " only" if t["id"] == "circulation-plan" else e["where"] + ", no comparison"
            else:
                st = (e["where"] + ", " if e["where"] else "") + DESIGN[e["design"]]
            if t["id"] == "parking-removal": st = ""
            if t["id"] == "school-streets": st = "mode effect only"
            if a.get("pct") is not None or a.get("sub"):
                st = a.get("sub") or "study: " + e["short"]
            st = st.replace("-", "\u2212") if st else st
            block(L["x_eff"], wrap(short.replace("-", "\u2212"), L["w_eff"]), st, a.get("text") or e["text"], e["source_title"], cells)
            c = t["coverage"]
            cov.append({"x": L["x_cov"], "y": yc, "t": c["label"], "ttl": c["text"]})
            o = t["opposition"]
            opp.append({"x1": L["x_opp"][0], "x2": L["x_opp"][1], "y1": y + 4, "y2": y + L["row_h"] - 4,
                        "f": OPP_FILL[o["grade"]], "c": OPP_TEXT[o["grade"]], "xc": sum(L["x_opp"]) / 2, "yc": yc, "t": o["grade"], "ttl": o["reason"]})
            for i, k in enumerate(PROG_KEYS):
                p = t["programs"][k]
                if p:
                    d = {"x": L["x_mark"][i], "y": yc, "t": "\u2014", "ttl": f"{k}: {p['status']} — {p['note']}"}
                    (dots if p["status"] == "in" else dashes if p["status"] == "limits" else holes).append(d)
            y += L["row_h"]
    H = y + L["bottom"]
    heads = [{"x": L["x_tool"], "y": L["head_y"], "t": "Tool" if not L.get("cost_under_name") else "Tool and cost"}]
    if not L.get("cost_under_name"):
        heads.append({"x": L["x_cost"], "y": L["head_y"], "t": "Cost"})
    heads += [{"x": L["x_eff"], "y": L["head_y"], "t": "Effect a square mile"}]
    oh = [{"x": sum(L["x_opp"]) / 2, "y": L["head_y"], "t": L["opp_head"]}]
    mheads = [{"x": L["x_mark"][i], "y": L["mhead_y"], "t": L["mark_heads"][i]} for i in range(3)]
    oh.append({"x": L["x_cov"], "y": L["head_y"], "t": L["cov_head"]})
    legend = [{"x": L["x_tool"], "y": H - L["bottom"] + 18, "t": L["legend"]}]
    data = {"rules": rules, "grp": grp, "rows": rows, "cells": cells, "sub": sub, "opp": opp,
            "dots": dots, "holes": holes, "dashes": dashes, "cov": cov, "heads": heads, "oh": oh, "mheads": mheads, "legend": legend,
            "hr": [{"y": L["top"] - 2}]}
    fs = L["fs"]
    marks = [
      {"mark": "ruleY", "data": "rules", "options": {"y": "y", "stroke": RULE}},
      {"mark": "ruleY", "data": "hr", "options": {"y": "y", "stroke": "#9aa3ad"}},
      {"mark": "text", "data": "heads", "options": {"x": "x", "y": "y", "text": "t", "textAnchor": "start", "fontSize": fs, "fontWeight": 700, "fill": INK}},
      {"mark": "text", "data": "oh", "options": {"x": "x", "y": "y", "text": "t", "fontSize": fs, "fontWeight": 700, "fill": INK}},
      {"mark": "text", "data": "mheads", "options": {"x": "x", "y": "y", "text": "t", "fontSize": fs - 1.5, "fontWeight": 700, "fill": INK, "lineHeight": 1.1, **({"rotate": -90, "textAnchor": "start"} if L.get("rotate") else {"frameAnchor": None})}},
      {"mark": "text", "data": "grp", "options": {"x": "x", "y": "y", "text": "t", "textAnchor": "start", "fontSize": fs, "fontWeight": 700, "fill": "#4269d0"}},
      {"mark": "text", "data": "rows", "options": {"x": "x", "y": "y", "text": "t", "textAnchor": "start", "fontSize": fs, "fontWeight": 600, "fill": INK, "lineHeight": 1.15, "title": "ttl"}},
      {"mark": "text", "data": "cells", "options": {"x": "x", "y": "y", "text": "t", "textAnchor": "start", "fontSize": fs, "fill": INK, "lineHeight": 1.15, "title": "ttl"}},
      {"mark": "text", "data": "sub", "options": {"x": "x", "y": "y", "text": "t", "textAnchor": "start", "fontSize": fs - 1.5, "fill": GRAY}},
      {"mark": "rect", "data": "opp", "options": {"x1": "x1", "x2": "x2", "y1": "y1", "y2": "y2", "fill": "f", "rx": 3, "title": "ttl"}},
      {"mark": "text", "data": "opp", "options": {"x": "xc", "y": "yc", "text": "t", "fill": "c", "fontSize": fs - 0.5, "fontWeight": 600, "title": "ttl"}},
      {"mark": "dot", "data": "dots", "options": {"x": "x", "y": "y", "r": L["r"], "fill": "#4269d0", "title": "ttl"}},
      {"mark": "dot", "data": "holes", "options": {"x": "x", "y": "y", "r": L["r"] - 0.5, "fill": "#ffffff", "stroke": "#4269d0", "strokeWidth": 1.6, "title": "ttl"}},
      {"mark": "text", "data": "dashes", "options": {"x": "x", "y": "y", "text": "t", "fill": "#59626f", "fontSize": fs + 4, "fontWeight": 700, "title": "ttl"}},
      {"mark": "text", "data": "cov", "options": {"x": "x", "y": "y", "text": "t", "fontSize": fs, "fill": INK, "title": "ttl"}},
      {"mark": "text", "data": "legend", "options": {"x": "x", "y": "y", "text": "t", "textAnchor": "start", "fontSize": fs - 1.5, "fill": GRAY, "lineHeight": 1.2}},
    ]
    # Plot's text mark needs fill as a channel name for per-row colours ("c", "f") — they are fields.
    for m in marks:
        m["options"] = {k: v for k, v in m["options"].items() if v is not None}
    options = {"style": {"fontFamily": "inherit", "color": GRAY}, "width": L["W"], "height": H,
               "marginLeft": 0, "marginRight": 0, "marginTop": 0, "marginBottom": 0,
               "x": {"domain": [0, L["W"]], "axis": None},
               "y": {"domain": [0, H], "reverse": True, "axis": None},
               "color": {"type": "identity"}}
    return data, marks, options

MAIN = dict(W=760, fs=11.5, top=50, head_y=38, mhead_y=24, grp_h=24, row_h=36, bottom=34, r=5.5,
            x_tool=4, w_tool=24, x_cost=170, w_cost=24, x_eff=330, w_eff=30, x_opp=(500, 566), where=True,
            x_cov=600, cov_head="Built", x_mark=(650, 694, 738), opp_head="Opposition in SF",
            mark_heads=["School\nplan", "Safe\nRoutes", "Safety\nInitiative"],
            legend="● in the plan   ○ a pilot, a draft or urged   — the plan opposes or severely limits it   Built: share of the city's places that have it\nCost and effect: the tool built everywhere it fits in a typical SF square mile. Hover a cell for the working and its source.")
PHONE = dict(W=390, fs=10.5, top=74, head_y=66, mhead_y=68, grp_h=22, row_h=40, bottom=44, r=4.5, rotate=True,
             x_tool=2, w_tool=19, cost_under_name=True, x_eff=124, w_eff=21, x_opp=(232, 276),
             x_cov=300, cov_head="Built", x_mark=(334, 354, 374), opp_head="Opposition",
             mark_heads=["School plan", "Safe Routes", "Safety Init."],
             legend="Gray under each tool: its cost a square mile.  ● in the plan  ○ pilot, draft or urged\n— opposed or severely limited   Built: share of places that have it")

TITLE = "What each street safety tool costs, what it does, and how hard it is to win in San Francisco"

def mdx(data, marks, options, title):
    j = lambda o: json.dumps(o, ensure_ascii=False, separators=(", ", ": "))
    return f'<PlotChart\n  title="{title}"\n  data={{{j(data)}}}\n  marks={{{j(marks)}}}\n  options={{{j(options)}}}\n/>\n'

if __name__ == "__main__":
    write_json()
    for name, L in [("toolkit", MAIN), ("toolkit-390", PHONE)]:
        d, m, o = chart(L)
        os.makedirs(f"{ROOT}/.cache/toolkit", exist_ok=True)
        open(f"{ROOT}/.cache/toolkit/{name}.mdx", "w").write(mdx(d, m, o, TITLE))
    print("ok", len(TOOLS), "tools")
