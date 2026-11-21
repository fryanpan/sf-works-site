#!/usr/bin/env python3
"""SFMTA's own project record, from the live service rather than the DataSF copy.

    tools/projects/sfmta-projects.py                 # writes out/sfmta-projects/
    tools/projects/sfmta-projects.py --no-pages      # skip fetching sfmta.com project pages
    tools/projects/sfmta-projects.py --out DIR
    tools/projects/sfmta-projects.py --update        # re-read only what moved (the pipeline's flag)

Refresh (--update). Each of the three layers is asked for its row count and its
newest LAST_EDITED_DATE and CREATED_DATE (one statistics query per layer; the
service publishes no editingInfo), and each DataSF mirror for its
rowsUpdatedAt. Only a layer or mirror whose marker moved is re-read; the rest
come from the held copy under .cache/sfmta-projects/ (gitignored). The check
is recorded as `arcgis:sfmta-projects` in data/pipeline-state/sources.json. A
marker check that fails keeps the held copy and records the check failed; a
re-read shorter than the layer's own count raises, so a short read never
replaces the held rows. Project pages are re-read only when sfmta.com's
sitemap says they changed (tools/projects/sfmta-project-pages.py).

Bryan, 2026-09-20: "That project polygons dataset is woefully out of date. Is
there a more complete source for MTA projects? And then please do go read the
project pages."

He is right about the dataset and there is a more complete source. Both are the
same underlying thing — SFMTA's Interactive Project Map, whose own description
says it "gathers spatial data for agency projects that have project pages on
SFMTA.com and CIP projects" — but they are not the same age:

  DataSF `6ibt-jpn7` / `j4dm-6zyr`   mirrors, last loaded 2025-09-02 / 2025-09-20,
                                     and the rows inside carry `data_as_of`
                                     2025-06-12. Publishing frequency is declared
                                     Weekly. It has not moved in twelve months.
  services.sfmta.com Multimodal/     the live service the mirror is taken from.
  projects                           Rows carry LAST_EDITED_DATE into the current
                                     week.

Measured 2026-09-20: 224 distinct projects live against 116 project nodes across
both DataSF mirrors, and 95 of the 122 bike-tagged live projects have no row in
the mirror at all. So the mirror is not merely late, it is missing most of the
bike programme — Arguello, Bayview Community Pathway, every Slow Street, the
Quick-Builds.

The project page is the other half. The layer gives a name, a phase and a
geometry; what the project actually proposes to build is prose on
sfmta.com/node/<PROJECTNODE>, which is server-rendered Drupal and plain to read.
SFMTA runs no JSON:API, so this reads the HTML.

What this does NOT give you: the layer's PROJECTPHASE is SFMTA's own word for
where a project stands and is not dated, so "Completed" carries no completion
date. Do not read it as delivery evidence on its own — join it to the bikeway
layer's INSTALL_YR, or to the board record, before saying something was built.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import importlib.util
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import pipeline_state, stable  # noqa: E402
import sfdata  # noqa: E402

ROOT = paths.ROOT
UA = "sf-works-research/1.0 (https://github.com/fryanpan/sf-works-site)"

BASE = "https://services.sfmta.com/arcgis/rest/services/Multimodal/projects/FeatureServer"
# 0 points, 1 lines, 2 polygons. A project can appear in more than one, and the
# same project appears once per geometry part, so PROJECTNODE is the key and not
# the row.
LAYERS = (0, 1, 2)

PAGE = "https://www.sfmta.com/node/{}"

# The mirrors, so the staleness this script exists to report is checkable rather
# than asserted.
MIRRORS = ("6ibt-jpn7", "j4dm-6zyr")


PAGES = paths.load("sfmta-project-pages.py")


def get(url, tries=3):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as fh:
                return fh.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError) as exc:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))
            last = exc
    raise last


def layer(n, geometry=True):
    """Every row of one layer, paged. ArcGIS caps a response at its own limit."""
    out, offset = [], 0
    while True:
        q = urllib.parse.urlencode({
            "where": "1=1", "outFields": "*", "f": "json",
            "returnGeometry": "true" if geometry else "false",
            "outSR": "4326", "resultOffset": offset, "resultRecordCount": 1000,
        })
        d = json.loads(get(f"{BASE}/{n}/query?{q}"))
        feats = d.get("features") or []
        out += feats
        if not d.get("exceededTransferLimit") or not feats:
            return out
        offset += len(feats)


# Held copies of the layers and mirrors with the marker they were read at.
CACHE = os.path.join(ROOT, ".cache", "sfmta-projects")
MARKERS = {}   # what each layer or mirror answered this run, for sources.json
FAILED = []    # marker checks that did not answer; the held copy was used


def layer_marker(n):
    """Row count, newest edit and newest creation of one layer: one small statistics query."""
    stats = [{"statisticType": "count", "onStatisticField": "OBJECTID", "outStatisticFieldName": "n"},
             {"statisticType": "max", "onStatisticField": "LAST_EDITED_DATE", "outStatisticFieldName": "e"},
             {"statisticType": "max", "onStatisticField": "CREATED_DATE", "outStatisticFieldName": "c"}]
    q = urllib.parse.urlencode({"where": "1=1", "outStatistics": json.dumps(stats), "f": "json"})
    d = json.loads(get(f"{BASE}/{n}/query?{q}"))
    a = {k.lower(): v for k, v in d["features"][0]["attributes"].items()}
    if a.get("n") is None:
        raise RuntimeError("no row count in the statistics answer: %s" % json.dumps(d)[:200])
    return a["n"], "%s rows, edited %s, created %s" % (a["n"], a.get("e"), a.get("c"))


def held(name, marker_fn, read):
    """`read()`'s answer, or the held copy when the source's marker has not moved.

    marker_fn returns (expected row count or None, marker). Without --update
    (marker_fn None) the source is read in full, as before."""
    path = os.path.join(CACHE, name + ".json")
    if marker_fn is None:
        return read()
    copy = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None
    try:
        count, marker = marker_fn()
    except Exception as exc:  # noqa: BLE001
        if copy is None:
            raise
        FAILED.append("%s: %s" % (name, exc))
        print(f"  {name}: change check failed ({type(exc).__name__}); held copy kept", file=sys.stderr)
        return copy["rows"]
    MARKERS[name] = marker
    if copy is not None and copy.get("marker") == marker:
        print(f"  {name}: unchanged ({marker})")
        return copy["rows"]
    rows = read()
    if count is not None and len(rows) < count:
        raise RuntimeError(f"{name}: read {len(rows)} rows against the layer's count of {count}: a short read")
    os.makedirs(CACHE, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"marker": marker, "rows": rows}, fh)
    print(f"  {name}: re-read ({marker})")
    return rows


def mirror_nodes(update=False):
    """Project nodes the DataSF copies know about, for the staleness comparison."""
    seen, asof = set(), {}
    for res in MIRRORS:
        url = (f"https://data.sf.gov/resource/{res}.json"
               f"?$limit=50000&$select=projectnode,data_as_of,data_loaded_at")
        try:
            rows = held("mirror-" + res,
                        (lambda res=res: (None, str(sfdata.metadata(res)["rows_updated_ts"]))) if update else None,
                        lambda url=url: json.loads(get(url)))
        except Exception as exc:
            # A failed read of a mirror used to leave every project marked as
            # missing from it. The last run's answer is the best we know.
            prev = os.path.join(ROOT, "out", "sfmta-projects", "projects.json")
            if not os.path.exists(prev):
                raise
            print(f"  !! DataSF mirror {res} unreadable ({type(exc).__name__}); keeping the last run's answer",
                  file=sys.stderr)
            d = json.load(open(prev, encoding="utf-8"))
            return ({p["node"] for p in d["projects"] if p.get("inDataSfMirror") and p.get("node")},
                    d.get("mirrorAsOf") or {})
        if len(rows) >= 50000:
            raise RuntimeError(f"{res} returned {len(rows)} rows, the query's limit: a short read")
        for r in rows:
            if r.get("projectnode"):
                seen.add(str(r["projectnode"]))
            for k in ("data_as_of", "data_loaded_at"):
                if r.get(k):
                    asof[f"{res}.{k}"] = max(asof.get(f"{res}.{k}", ""), r[k][:10])
    return seen, asof


# Individual city staff email addresses are scrubbed, so that only the city
# publishes those. Bryan's standing rule, 2026-09-19: "We should consider
# scrubbing email addresses so that only the city publishes those." A scraped
# project page is a different artifact from SFMTA's own contact page, whatever
# its text says. The person's NAME stays — a public employee in their official
# role is public record — and so does the link to the page that carries the
# address.
#
# The test is the local part. An institutional inbox is one topical word
# (SlowStreets@, TellMuni@, Valencia@, TLStreets@, embarcadero@) and is the
# published way to reach a team, so it stays. An address whose local part
# separates name tokens with a dot or an underscore is a person, and goes —
# two of them or three, since a middle initial (Alex.M.Murillo@) is still a
# person and a two-token-only test let that one through.
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PERSONAL_LOCAL = re.compile(r"^[A-Za-z][A-Za-z'-]*(?:[._][A-Za-z][A-Za-z'-]*)+$")


def scrub_emails(text):
    """Drop individual staff addresses, keep institutional inboxes."""
    def one(m):
        local = m.group(0).split("@", 1)[0]
        if PERSONAL_LOCAL.match(local):
            return "[staff email removed — see the project page]"
        return m.group(0)
    return EMAIL.sub(one, text)


TAG = re.compile(r"(?s)<[^>]+>")
DROP = re.compile(r"(?s)<(script|style|nav|header|footer|form)\b.*?</\1>")


def page_text(node):
    """The readable prose of one sfmta.com project page, or None.

    Drupal renders the whole chrome into every page, so this keeps only what
    sits inside the main region and then flattens it. It is prose for a person
    to read, not a parse: nothing downstream should depend on its structure.
    """
    try:
        # Through tools/projects/sfmta-project-pages.py's page cache, so a page is
        # downloaded once and, under --update, again only when the sitemap
        # says it changed.
        raw = PAGES.get(PAGE.format(node))
    except Exception:
        return None
    m = re.search(r'(?s)<main\b.*?</main>', raw) or re.search(
        r'(?s)<div[^>]*\brole="main".*?</div>\s*</div>', raw)
    seg = m.group(0) if m else raw
    seg = DROP.sub(" ", seg)
    txt = html.unescape(TAG.sub(" ", seg))
    txt = re.sub(r"\s+", " ", txt).strip()
    return scrub_emails(txt) or None


# The layer's PROJECTTYPE is a comma-joined tag list. "Bike" is the one that
# decides whether a project is in scope for this repo's streets work.
def is_bike(a):
    return "Bike" in (a.get("PROJECTTYPE") or "")


def ymd(v):
    if not v:
        return None
    return dt.datetime.utcfromtimestamp(v / 1000).strftime("%Y-%m-%d")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "sfmta-projects"))
    ap.add_argument("--no-pages", action="store_true")
    ap.add_argument("--pages-for", choices=("bike", "all"), default="bike",
                    help="which projects to fetch sfmta.com prose for")
    ap.add_argument("--update", action="store_true",
                    help="re-read a cached project page only when the sitemap says it changed")
    args = ap.parse_args()
    if args.update and not args.no_pages:
        PAGES.LASTMOD = PAGES.sitemap_lastmods()
    os.makedirs(args.out, exist_ok=True)
    today = dt.date.today().isoformat()

    feats, geo = [], []
    for n in LAYERS:
        rows = held("layer-%d" % n, (lambda n=n: layer_marker(n)) if args.update else None, lambda n=n: layer(n))
        for f in rows:
            a = dict(f["attributes"])
            a["_layer"] = n
            feats.append(a)
            if f.get("geometry"):
                geo.append((a, f["geometry"], n))
        print(f"  layer {n}: {len(rows)} rows")

    # One record per project. Where a project has several parts, keep the most
    # recently edited attributes and collect every part's geometry.
    proj = {}
    for a in feats:
        k = str(a.get("PROJECTNODE") or a.get("PROJECTNAME"))
        cur = proj.get(k)
        if cur is None or (a.get("LAST_EDITED_DATE") or 0) > (cur.get("LAST_EDITED_DATE") or 0):
            proj[k] = a
    for a in proj.values():
        a["_parts"] = sum(1 for f in feats
                          if str(f.get("PROJECTNODE") or f.get("PROJECTNAME")) == str(
                              a.get("PROJECTNODE") or a.get("PROJECTNAME")))

    bike = {k: a for k, a in proj.items() if is_bike(a)}
    mirror, asof = mirror_nodes(args.update)
    if args.update:
        if FAILED:
            pipeline_state.record("arcgis:sfmta-projects", "failed", detail="; ".join(FAILED))
        else:
            pipeline_state.record("arcgis:sfmta-projects", "checked",
                                  version="; ".join("%s %s" % kv for kv in sorted(MARKERS.items())))
    missing = sorted(k for k in bike if k not in mirror)

    pages = {}
    if not args.no_pages:
        want = bike if args.pages_for == "bike" else proj
        for i, (k, a) in enumerate(sorted(want.items()), 1):
            node = a.get("PROJECTNODE")
            if not node:
                continue
            txt = page_text(node)
            if txt:
                pages[str(node)] = txt
            if i % 20 == 0:
                print(f"  pages: {i}/{len(want)}")
        print(f"  pages: {len(pages)} of {len(want)} fetched")

    records = []
    for k, a in sorted(proj.items(), key=lambda kv: (kv[1].get("PROJECTNAME") or "")):
        node = str(a.get("PROJECTNODE") or "")
        records.append({
            "node": node or None,
            "name": a.get("PROJECTNAME"),
            "cipTitle": a.get("CIP_TITLE"),
            "phase": a.get("PROJECTPHASE"),
            "types": [t.strip() for t in (a.get("PROJECTTYPE") or "").split(",") if t.strip()],
            "bike": is_bike(a),
            "leadAgency": a.get("LEADAGENCY"),
            "partners": a.get("PARTNERAGENCIES"),
            "supervisors": a.get("SUPERVISORNAME"),
            "districts": a.get("SUPERVISORDISTRICT"),
            "neighborhoods": a.get("NEIGHBORHOOD"),
            "page": PAGE.format(node) if node else None,
            "teaser": a.get("TEASER"),
            "lastEdited": ymd(a.get("LAST_EDITED_DATE")),
            "created": ymd(a.get("CREATED_DATE")),
            "geometryParts": a.get("_parts"),
            "inDataSfMirror": node in mirror,
            "pageText": pages.get(node),
        })

    stable.write_json(os.path.join(args.out, "projects.json"),
                      {"generated": today, "source": BASE,
                       "mirrorAsOf": asof, "projects": records}, end="", ensure_ascii=True, indent=1)

    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "properties": {"node": a.get("PROJECTNODE"), "name": a.get("PROJECTNAME"),
                        "phase": a.get("PROJECTPHASE"), "bike": is_bike(a),
                        "lastEdited": ymd(a.get("LAST_EDITED_DATE"))},
         "geometry": esri_to_geojson(g, n)}
        for a, g, n in geo if esri_to_geojson(g, n)]}
    stable.write_json(os.path.join(args.out, "projects.geojson"), fc, end="", ensure_ascii=True)

    edited = sorted(r["lastEdited"] for r in records if r["lastEdited"])
    L = [
        "# SFMTA's project record, read from the live service",
        "",
        f"Generated {today} by `tools/projects/sfmta-projects.py`. **Do not edit this file "
        "by hand — the next run overwrites it.**",
        "",
        f"- **{len(records)} distinct projects**, {len(bike)} of them tagged Bike, "
        f"from [{BASE}]({BASE}).",
        f"- Rows carry an edit date from {edited[0]} to {edited[-1]}.",
        f"- **{len(missing)} of the {len(bike)} bike projects have no row in the "
        "DataSF mirrors** ([6ibt-jpn7](https://data.sf.gov/d/6ibt-jpn7), "
        "[j4dm-6zyr](https://data.sf.gov/d/j4dm-6zyr)), which between them know "
        f"{len(mirror)} project nodes.",
        "",
        "The mirrors declare a weekly publishing frequency and have not moved since "
        f"{min(v for k, v in asof.items() if k.endswith('data_loaded_at')) if asof else 'their last load'}"
        "; the rows inside them are stamped older still. Use the live service.",
        "",
        "## Bike projects the DataSF mirror does not have",
        "",
        "| Project | Phase | Last edited | Page |",
        "| --- | --- | --- | --- |",
    ]
    for k in sorted(missing, key=lambda k: bike[k].get("PROJECTNAME") or ""):
        a = bike[k]
        node = a.get("PROJECTNODE")
        L.append(f"| {a.get('PROJECTNAME')} | {a.get('PROJECTPHASE') or '—'} "
                 f"| {ymd(a.get('LAST_EDITED_DATE')) or '—'} "
                 f"| [sfmta.com/node/{node}]({PAGE.format(node)}) |")
    L += ["", "## Every bike project the live service carries", "",
          "| Project | Phase | Last edited | In mirror | Page |",
          "| --- | --- | --- | --- | --- |"]
    for k, a in sorted(bike.items(), key=lambda kv: kv[1].get("PROJECTNAME") or ""):
        node = a.get("PROJECTNODE")
        L.append(f"| {a.get('PROJECTNAME')} | {a.get('PROJECTPHASE') or '—'} "
                 f"| {ymd(a.get('LAST_EDITED_DATE')) or '—'} "
                 f"| {'yes' if str(node) in mirror else 'no'} "
                 f"| [sfmta.com/node/{node}]({PAGE.format(node)}) |")
    L += [
        "",
        "## What this does not say",
        "",
        "- **`Phase` is undated.** It is SFMTA's own word for where a project "
        "stands, with no completion date behind it, so a project reading "
        "\"Completed\" is not evidence that anything was built in a given year. "
        "Join it to the bikeway layer or the board record before saying so.",
        "- **A project's geometry is its study area, not its build.** A corridor "
        "polygon covers blocks the project may or may not touch.",
        "- **The page prose is prose.** It is fetched so a person can read what a "
        "project proposes; nothing here parses it, and SFMTA rewrites those pages "
        "without changing the layer.",
        "",
    ]
    stable.write_text(os.path.join(args.out, "projects.md"), "\n".join(L) + "\n")

    print(f"{len(records)} projects ({len(bike)} bike, {len(missing)} missing from "
          f"the DataSF mirror) → {args.out}/")


def esri_to_geojson(g, layer_id):
    if layer_id == 0:
        if g.get("x") is None:
            return None
        return {"type": "Point", "coordinates": [g["x"], g["y"]]}
    if layer_id == 1:
        paths = g.get("paths") or []
        if not paths:
            return None
        return ({"type": "LineString", "coordinates": paths[0]} if len(paths) == 1
                else {"type": "MultiLineString", "coordinates": paths})
    rings = g.get("rings") or []
    if not rings:
        return None
    return {"type": "Polygon", "coordinates": rings}


if __name__ == "__main__":
    main()
