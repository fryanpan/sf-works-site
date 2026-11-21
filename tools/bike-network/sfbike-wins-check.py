#!/usr/bin/env python3
"""Check the bike page's map against the SF Bike Coalition's posts about wins, so projects the map is missing surface.

    tools/bike-network/sfbike-wins-check.py

A one-off exploratory check, not a scheduled fetch: nothing on the site reads
its output, so the incremental-update rule in pipeline/README.md does not apply. If a
page ever reads it, it needs --update, quality checks and a pipeline step.

Input: data/sfbike-wins/wins.json, a hand-kept list of Coalition posts about
wins (title, URL, the streets it names, the SFMTA project pages it is about).
sfbike.org answers scripted requests with a Cloudflare 403, so the list came
from web searches restricted to the site; wins.json says which.

For each win it asks two questions of what the bike page draws:

  1. Is the SFMTA project on the page? site/data/bike-history/projects.json
     (built blocks credited to a project), planned.json (drawn in a future
     year, or named but not drawn under `uncounted`), reported.json (2026
     work read off project pages), or listed as unbuilt and left off.
  2. Did its blocks change on the map? The project's blocks from
     out/project-record/project-blocks.json, looked up in
     site/data/bike-history/segments.json: how many are a separated lane,
     path or Slow Street (codes 1, 4, S) in the latest year, and the first
     year each became one. When a win names no project, the named streets
     are looked up in segments.json by name instead.

A win is then one of:
  on-map-built    the page credits the project with a block on a street the
                  post names, or the project is not otherwise on the page and
                  at least half its blocks on those streets are separated,
                  path or Slow Street in the latest year;
  on-map-planned  drawn in a future year;
  named-not-drawn on the page (uncounted, unbuilt, or credited only for
                  blocks on other streets) but not drawn where the post says;
  on-map-lane     no project on the page, but the post calls it built and
                  the named streets carry a painted lane or route;
  missing         none of the above.

Writes out/sfbike-check/check.json and out/sfbike-check/check.md. The .md is
bound to a board doc; after a rerun, call reparse_from_disk on it (the script
prints the docId).
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections
import json
import os
import sys

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
from lib import settings, stable  # noqa: E402

BIKE = os.path.join(ROOT, "site", "data", "bike-history")
WINS = os.path.join(ROOT, "data", "sfbike-wins", "wins.json")
SFMTA = os.path.join(ROOT, "out", "sfmta-projects", "projects.json")
BLOCKS = os.path.join(ROOT, "out", "project-record", "project-blocks.json")
OUT_DIR = os.path.join(ROOT, "out", "sfbike-check")
SEPARATED = set("14S")
DOC_ID = settings.get("SFBIKE_CHECK_DOC")  # the board doc that shows check.md, if any (lib/settings.py)
STATUS_ORDER = ["credited", "reported", "planned", "uncounted", "unbuilt"]


def street_key(name):
    """A street name with ordinal zero-padding removed: segments.json carries
    both '07TH ST' and '7TH ST'."""
    words = [w.lstrip("0") if w[:1] == "0" and w[1:2].isdigit() else w for w in name.upper().split()]
    # The centerline file spells Bayshore both ways.
    return " ".join(words).replace("BAY SHORE", "BAYSHORE")


def load(path):
    with open(path) as f:
        return json.load(f)


def main():
    wins = load(WINS)
    seg = load(os.path.join(BIKE, "segments.json"))
    years = seg["years"]
    planned = load(os.path.join(BIKE, "planned.json"))
    credited = load(os.path.join(BIKE, "projects.json"))
    reported = load(os.path.join(BIKE, "reported.json"))
    sfmta = {p["node"]: p for p in load(SFMTA)["projects"]}
    pblocks = load(BLOCKS)["projects"]

    by_cnn = collections.defaultdict(list)
    by_street = collections.defaultdict(list)
    by_key = {s["key"]: s for s in seg["segments"]}
    for s in seg["segments"]:
        if s.get("cnn"):
            by_cnn[s["cnn"]].append(s)
        if s.get("name"):
            by_street[street_key(s["name"])].append(s)
    planned_streets = collections.defaultdict(set)
    for p in planned["projects"]:
        for b in p["blocks"]:
            planned_streets[street_key(b["street"])].add(p["name"])

    # Every place a node appears on the page. A node can appear more than once:
    # planned.json lists node 381 twice, as its Folsom and its Howard halves.
    on_page = collections.defaultdict(list)
    for p in credited["projects"]:
        on_page[p["node"]].append({"status": "credited", "year": None, "name": p["name"],
                                   "keys": list(p.get("blocks", []))})
    for p in reported["projects"]:
        on_page[p["node"]].append({"status": "reported", "year": p.get("year"), "name": p["name"],
                                   "keys": [b["cnn"] for b in p.get("blocks", [])]})
    for p in planned["projects"]:
        on_page[p["node"]].append({"status": "planned", "year": p.get("year"), "name": p["name"],
                                   "keys": [b["cnn"] for b in p.get("blocks", [])]})
    for p in planned["uncounted"]:
        on_page[p["node"]].append({"status": "uncounted", "year": p.get("year"),
                                   "name": p["name"] + " — " + p["why"], "keys": []})
    for p in credited["excluded_unbuilt"]:
        on_page[p["node"]].append({"status": "unbuilt", "year": None, "name": p["name"], "keys": []})

    def block_state(segs, total=None):
        """Blocks separated in the latest year, and the first year each became so.

        `total` is the number of blocks the project covers; a covered block
        with no row in segments.json never carried a bikeway, so it counts in
        the denominator and never as separated."""
        n = len(segs) if total is None else max(total, len(segs))
        sep = [s for s in segs if s["y"][-1] in SEPARATED]
        firsts = collections.Counter()
        for s in sep:
            for i, c in enumerate(s["y"]):
                if c in SEPARATED:
                    firsts[years[i]] += 1
                    break
        return {"blocks": n, "separated_latest": len(sep),
                "bikeway_latest": sum(1 for s in segs if s["y"][-1] != "0"),
                "first_year": dict(sorted(firsts.items()))}

    rows = []
    for w in wins["wins"]:
        named_streets = {street_key(n) for n in w["streets"]}
        proj = []
        for node in w["nodes"]:
            p = sfmta.get(node)
            entries = on_page.get(node, [])
            cnns = set(pblocks.get(node, {}).get("cnns", []))
            # The blocks a project covers: its published geometry, plus any
            # block the page credits it with (a stand-in Slow Street has no
            # geometry; Sanchez Slow Street's geometry sits on its cross streets).
            page_keys = {k for e in entries if e["status"] in ("credited", "reported") for k in e["keys"]}
            keys = sorted(cnns | page_keys)
            segs = []
            seen = set()
            for k in keys:
                for s in by_cnn.get(k, []) + ([by_key[k]] if k in by_key else []):
                    if s["key"] not in seen:
                        seen.add(s["key"])
                        segs.append(s)
            # A project's geometry also touches cross streets and freeways, so
            # whether it is drawn is judged on the blocks of the streets the
            # post names, when the geometry reaches any of them.
            named = [s for s in segs if s.get("name") and street_key(s["name"]) in named_streets]
            credited_named = [k for k in page_keys
                              if k in by_key and by_key[k].get("name")
                              and street_key(by_key[k]["name"]) in named_streets] + [
                k for k in page_keys if k in by_cnn and any(
                    street_key(s.get("name") or "") in named_streets for s in by_cnn[k])]
            statuses = sorted({e["status"] for e in entries}, key=STATUS_ORDER.index)
            proj.append({
                "node": node,
                "name": p["name"] if p else (entries[0]["name"] if entries else None),
                "phase": p.get("phase") if p else None,
                "page": ("https://www.sfmta.com/node/%s" % node) if p else None,
                "on_page": statuses[0] if statuses else None,
                "on_page_all": [{"status": e["status"], "year": e["year"], "name": e["name"]} for e in entries],
                "credited_on_named_streets": bool(credited_named),
                "geometry_blocks": len(keys),
                **block_state(segs, len(keys)),
                "on_named_streets": block_state(named),
            })
        streets = []
        for name in w["streets"]:
            segs = by_street.get(street_key(name), [])
            streets.append({"street": name, "found": bool(segs),
                            "planned_by": sorted(planned_streets.get(street_key(name), [])),
                            **block_state(segs)})

        def drawn(pr):
            b = pr["on_named_streets"] if pr["on_named_streets"]["blocks"] else pr
            return bool(b["blocks"]) and b["separated_latest"] * 2 >= b["blocks"]

        def credited_here(pr):
            # Credited on the page for a block on a street the post names; a
            # credit elsewhere is another place, not this win.
            return pr["on_page"] in ("credited", "reported") and (
                pr["credited_on_named_streets"] or not named_streets)

        def built(pr):
            if credited_here(pr):
                return True
            return pr["on_page"] not in ("planned", "credited", "reported") and drawn(pr)

        flags = []
        any_credited = any(credited_here(pr) for pr in proj)
        for pr in proj:
            if pr["on_page"] == "planned" or any_credited or not drawn(pr):
                continue
            # The page credits only blocks that became separated after the
            # map's first year, so blocks already separated then are no one's
            # (the Great Highway path, drawn from 2015).
            b = pr["on_named_streets"] if pr["on_named_streets"]["blocks"] else pr
            if not any(y > years[0] for y in b["first_year"]):
                continue
            if pr["on_page"] == "unbuilt":
                flags.append("%s: the page leaves it off as unbuilt (SFMTA phase %s), but the bikeway layer shows its blocks on the streets the post names as separated, path or Slow Street" % (pr["name"], pr["phase"]))
            elif pr["on_page"] in ("credited", "reported"):
                flags.append("%s: the page credits it only with blocks on other streets, while its blocks on the streets the post names are drawn as separated, path or Slow Street" % pr["name"])
            else:
                flags.append("%s: its blocks on the streets the post names are drawn as separated, path or Slow Street, but the page does not credit the project" % pr["name"])

        if any(built(pr) for pr in proj):
            verdict = "on-map-built"
        elif any(pr["on_page"] == "planned" for pr in proj):
            verdict = "on-map-planned"
        elif any(pr["on_page"] in ("uncounted", "unbuilt", "credited", "reported") for pr in proj):
            verdict = "named-not-drawn"
        elif w["kind"] == "built" and streets and all(
                s["found"] and s["bikeway_latest"] * 2 >= s["blocks"] for s in streets):
            # Only a win the post calls built can be matched by a lane already
            # on the street; an approval there is an upgrade still to come.
            verdict = "on-map-lane"
        else:
            verdict = "missing"
        rows.append({**{k: w[k] for k in ("id", "title", "url", "kind", "claim")},
                     "note": w.get("note"),
                     "verdict": verdict, "flags": flags, "projects": proj, "streets": streets})

    counts = collections.Counter(r["verdict"] for r in rows)
    out = {"generated": wins["read"], "wins_read": wins["read"], "how": wins["how"],
           "latest_year": years[-1], "counts": dict(sorted(counts.items())), "rows": rows}
    os.makedirs(OUT_DIR, exist_ok=True)
    stable.write_json(os.path.join(OUT_DIR, "check.json"), out)
    stable.write_text(os.path.join(OUT_DIR, "check.md"), render(out))
    print(json.dumps(out["counts"]))
    if DOC_ID:
        print("out/sfbike-check/check.md is shown on board doc %s: re-read it so the board shows this run" % DOC_ID)


VERDICT = {
    "on-map-built": "On the map as built",
    "on-map-planned": "On the map as planned",
    "named-not-drawn": "On the page, but not drawn on the streets the post names",
    "on-map-lane": "On the map as a painted lane or route",
    "missing": "Not on the map",
}
ON_PAGE = {
    "credited": "credited with built blocks, on %s",
    "reported": "2026 work read off its page",
    "planned": "drawn in %s",
    "uncounted": "listed, not drawn",
    "unbuilt": "left off as unbuilt",
    None: "not on the page",
}


def render(out):
    tag = "[web search — verify]"
    lines = [
        "# The bike map against the SF Bike Coalition's wins",
        "",
        "Each row is a post on sfbike.org about a win, found by web search on %s %s, "
        "checked against what the bike page draws: whether the SFMTA project is on the page, "
        "and how many of its blocks are a separated lane, path or Slow Street in %s "
        "(from [segments.json](../../site/data/bike-history/segments.json) and "
        "[project-blocks.json](../project-record/project-blocks.json)). "
        "Built by [tools/bike-network/sfbike-wins-check.py](../../tools/bike-network/sfbike-wins-check.py) from "
        "[data/sfbike-wins/wins.json](../../data/sfbike-wins/wins.json)."
        % (out["wins_read"], tag, out["latest_year"]),
        "",
        "| Verdict | Wins |", "| --- | --- |",
    ]
    for k in VERDICT:
        lines.append("| %s | %d |" % (VERDICT[k], out["counts"].get(k, 0)))
    for k in ("missing", "named-not-drawn", "on-map-lane", "on-map-planned", "on-map-built"):
        rows = [r for r in out["rows"] if r["verdict"] == k]
        if not rows:
            continue
        lines += ["", "## %s" % VERDICT[k], ""]
        for r in rows:
            lines.append("### [%s](%s)" % (r["title"], r["url"]))
            lines.append("")
            lines.append("The post: %s. %s" % (r["claim"], tag))
            lines.append("")
            if r.get("note"):
                lines.append("- Note: %s" % r["note"])
            for f in r["flags"]:
                lines.append("- **Check:** %s." % f)
            for p in r["projects"]:
                hows = []
                for e in p["on_page_all"] or [{"status": None, "year": None}]:
                    h = ON_PAGE[e["status"]]
                    if e["status"] == "credited":
                        h = h % ("the streets the post names" if p["credited_on_named_streets"] else "other streets only")
                    elif "%s" in h:
                        h = h % e["year"]
                    if h not in hows:
                        hows.append(h)
                how = "; ".join(hows)
                first = ", ".join("%s: %d" % (y, n) for y, n in p["first_year"].items()) or "none"
                label = "[%s](%s)" % (p["name"], p["page"]) if p["page"] else "%s (no SFMTA page)" % p["name"]
                ns = p["on_named_streets"]
                named = (" On the streets the post names: %d of %d." % (ns["separated_latest"], ns["blocks"])) if ns["blocks"] else ""
                lines.append("- %s, SFMTA phase %s: %s. %d of the %d blocks its geometry touches are separated, path or Slow Street in %s; first year per block %s.%s"
                             % (label, p["phase"] or "not given", how,
                                p["separated_latest"], p["blocks"], out["latest_year"], first, named))
            if not r["projects"]:
                lines.append("- No SFMTA project page in the mirror matches this win.")
            for s in r["streets"]:
                if not s["found"]:
                    lines.append("- %s: no block of that name on the map." % s["street"])
                    continue
                pl = (" Planned on this street: %s." % "; ".join(s["planned_by"])) if s["planned_by"] else ""
                lines.append("- %s, whole street: %d of %d blocks separated, path or Slow Street in %s; %d carry any bikeway.%s"
                             % (s["street"], s["separated_latest"], s["blocks"], out["latest_year"], s["bikeway_latest"], pl))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    main()
