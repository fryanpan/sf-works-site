#!/usr/bin/env python3
"""Crash cards for every injury crash on the Street Safety map, 2005 to the newest report, at every severity, written as small files by year and map cell under site/data/street-safety/cards/ so the map fetches only the file holding a tapped crash.

    python3 tools/street-safety/street-safety-cards.py            # build from the held reads
    python3 tools/street-safety/street-safety-cards.py --update   # ask DataSF what changed, re-read it, check it, then build
    python3 tools/street-safety/street-safety-cards.py --all      # rebuild every file, even one whose inputs hash the same

Bryan, 2026-11-20 ("Go for it"): crash cards for every injury crash at every severity and every
year the map covers, not only the severe injuries and deaths of 2022 to 2024.

INPUTS. Three DataSF tables, each read one calendar year per query through lib/sfdata.py into its own cache folder,
data/socrata-cache/street-safety-cards/ (gitignored), from 2005, the tables' first year, to this year:
  crashes  ubvf-ztfx  hin_crash_cards.CRASH_FIELDS
  parties  8gtc-pjc6  hin_crash_cards.PARTY_FIELDS
  victims  nwes-mmgh  hin_crash_cards.VICTIM_FIELDS plus the geocoded point (tb_longitude, tb_latitude)
plus the active street centrelines (3psu-pn9h, the query hin_crash_cards.load_network makes, refreshed by the socrata
step), the High Injury Network editions in data/extract/access/hin-<year>.json, and site/data/street-safety/map.json,
whose people with a police case number (the severe injuries and deaths of 2022 to 2024 and the fatality log's deaths)
keep the point the map draws them at, so their cards are the same bytes tools/street-safety/hin-people-map.py makes.

INCREMENTAL FETCH (--update). For each table the script asks DataSF for rowsUpdatedAt, to the second. When it has not
moved since the last check (data/pipeline-state/sources.json, "cards:<id>"), nothing is read. When it has, this year's
and last year's queries are re-read (the crash tables are revised for months after a crash), and so is every year from
2022, the years of the map's carded people (MAP_FROM), so a card moves on the same run as the map's own reads of
those cases (tools/street-safety/street-safety-crashes.py). An older year's query is re-read only when it was last re-read over
90 days ago: that is the bound for revisions to old years. A re-read goes to a
staging folder first; only when the checks below pass does it replace the held copy. A re-read that fails (no answer,
or fewer rows than the floor) keeps the held copy, records the table as failed and goes on, so the build runs on the
last good reads. A re-read with the same rows keeps the held copy and its date, so nothing downstream moves.

CHECKS, run after every fetch and before any file is written; a failure exits 1 and leaves the cards and the held reads
as they were. Per table and year: rows at least the floor (complete years) and at least 90% of the count the index
recorded last time; case id present on every row; each row's date inside its year. Keys unique (an identical repeat is
allowed, as case 260408381 is repeated in the crash and parties tables, research/sources/datasf-traffic-crashes.md).
Joins: every victim's case is in the crash table (at most 0.5% missing), every carded crash has a party, every victim
names a party of its crash (hin_crash_cards.build asserts the last two), and at least 97% of crashes with someone hurt
have a point. After the build: every card has a header, a party list, a drawing and its year, one injury list per
party with someone hurt in at least one, every
planned crash has a card on disk, and at least 99.9% of the dots in data/extract/street-safety/light-injuries.json
whose case has a card find it in the file the map names from their date and point. A failure in the build or these
checks exits 1 after files were written; pipeline/transportation-update.py then puts the previous files back from its
snapshot. Order: this step reads map.json, which street-safety-map writes later, so a person new to map.json is placed
in their own file on the next run (street-safety-map is rerun by hand for now).

BUILD. One card per crash that hurt someone at any of the four levels (Fatal Injury, Severe Injury, Other Visible
Injury, Complaint of Pain), made by hin_crash_cards.build, with its date (`dt`) and its people's points (`at`, degrees
x 1e5, the map's own rounding) added so the map can find the card of a person who carries no case number. The point a
card is drawn around is the map.json person's point for a case the map carries with one, else the first victim's
geocoded point (by victim id) to six decimals. A crash with no point in the city's box gets no card and is counted.

FILES. cards/<year>/<i>-<j>.json holds the cards of one calendar year whose people fall in one 0.01 degree cell,
i = floor(lon x 100) + 12260 and j = floor(lat x 100) - 3770, from the points the map holds (each person's point to
five decimals, and a map.json person's own point), so a card whose people straddle a cell edge is in both files. Each
file is {"cards": {case: card}}. cards/index.json lists every file with its card count, the cards and generic-cross
drawings per year, the rows read per table and year, and the date the data was read (the newest read date), and is not
read by the page.

IDEMPOTENT AND INCREMENTAL BUILD. Each file's inputs (its crashes' rows, points and HIN editions, the centrelines its
drawings can reach, and this script's and hin_crash_cards.py's own text) hash to one value, kept per file in
data/pipeline-state/street-safety-cards.json. A file whose hash is unchanged and whose bytes are as written is not
rebuilt; a deleted or edited file is. Output is compact JSON with sorted keys, so a run with no new data writes nothing.

Checks: as above. Writes nothing outside site/data/street-safety/cards/ and the two state files.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import sys
import time
import multiprocessing
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(paths.ROOT)
sys.path.insert(0, str(HERE))
import sfdata  # noqa: E402
import hin_crash_cards as hcc  # noqa: E402
from lib import pipeline_state  # noqa: E402
from lib.stable import write_text  # noqa: E402

hpm = paths.load("hin-people-map.py")

OUT = ROOT / "site/data/street-safety/cards"
MAP_JSON = ROOT / "site/data/street-safety/map.json"
LIGHT = ROOT / "data/extract/street-safety/light-injuries.json"   # the dots' own read, for the lookup check
CACHE = ROOT / "data/socrata-cache/street-safety-cards"
STAGE = ROOT / "data/socrata-cache/street-safety-cards.stage"
STATE_DIR = Path(os.environ.get("PIPELINE_STATE_DIR") or ROOT / "data/pipeline-state")
MANIFEST = STATE_DIR / "street-safety-cards.json"
FIRST_YEAR = 2005
X0, Y0 = 12260, 3770          # cell offsets: i = floor(lon * 100) + X0, j = floor(lat * 100) - Y0
BOX = (-122.53, -122.35, 37.70, 37.84)   # the city's box, as tools/street-safety/street-safety-light.py keeps it
INJURED = ("Fatal Injury", "Severe Injury", "Other Visible Injury", "Complaint of Pain")
VICTIM_FIELDS = hcc.VICTIM_FIELDS + ",tb_longitude,tb_latitude"
TABLES = (("crashes", "ubvf-ztfx", hcc.CRASH_FIELDS), ("parties", "8gtc-pjc6", hcc.PARTY_FIELDS),
          ("victims", "nwes-mmgh", VICTIM_FIELDS))
# Rows per complete year: 2005 to 2025 run 2,454 to 3,486 crashes, 5,189 to 7,361 parties and 2,993 to 4,458 victims
# (DataSF, grouped by year, queried 2026-11-20). Last year's floor is lower, since the tables fill in for months.
FLOOR = {"crashes": 2000, "parties": 4500, "victims": 2500}
FLOOR_LAST_YEAR = {"crashes": 1000, "parties": 2000, "victims": 1200}
MAX_DROP = 0.10
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
MAX_UNJOINED = 0.005
MIN_PLACED = 0.97
REREAD_RECENT = 2      # this year and last year are re-read on every change
OLD_MAX_AGE = 90       # an older year's read is re-read on a change once it is this many days old
# The years the map's carded people come from (hin_crash_cards.SINCE, 2022 on): re-read on every change, as
# tools/street-safety/street-safety-crashes.py re-reads the map's own reads of them, so a new or reclassified case reaches the
# map and its card on the same run.
MAP_FROM = 2022


def where_year(y):
    return "collision_datetime between '%d-01-01T00:00:00' and '%d-12-31T23:59:59'" % (y, y)


def years(today):
    return list(range(FIRST_YEAR, today.year + 1))


def floor_for(name, y, today):
    if y >= today.year:
        return 0
    return FLOOR_LAST_YEAR[name] if y == today.year - 1 else FLOOR[name]


def read_tables(update, today, checked):
    """{name: {year: sfdata.Result}} and the per-table outcome {name: (status, version, detail)}. checked: {"<id>/<year>":
    date} of each query's last re-read, updated in place (a re-read with the same rows keeps the copy's own date, so
    the 90-day bound is counted from the last check, not from that date)."""
    out, outcome = {}, {}
    state = pipeline_state.load()
    for name, fxf, select in TABLES:
        status, version, detail, changed = "unchanged", None, "", False
        if update:
            try:
                meta = sfdata.metadata(fxf)
                version = str(meta.get("rows_updated_ts"))
                last = state.get("cards:" + fxf, {})
                changed = not (last.get("version") == version and last.get("status") != "failed")
            except Exception as e:  # noqa: BLE001 - no answer: keep the held reads
                status, detail = "failed", "rowsUpdatedAt not read (%s); held reads kept" % e
        out[name] = {}
        failed = []
        for y in years(today):
            kw = dict(select=select, where=where_year(y), floor=floor_for(name, y, today))
            held = sfdata.fetch(fxf, cache_dir=CACHE, max_age_days=10 ** 6, **kw) if _held(fxf, kw) else None
            last = dt.date.fromisoformat(checked.get("%s/%d" % (fxf, y)) or (held.fetched_on.isoformat() if held else "2000-01-01"))
            reread = held is None or (changed and (y > today.year - REREAD_RECENT or y >= MAP_FROM
                                                   or (today - last).days > OLD_MAX_AGE))
            if not reread:
                out[name][y] = held
                continue
            try:
                STAGE.mkdir(parents=True, exist_ok=True)
                src = _path(CACHE, fxf, kw)
                if src.exists():   # so a re-read with the same rows keeps the held copy's date
                    shutil.copy2(src, _path(STAGE, fxf, kw))
                out[name][y] = fetch_retry(fxf, kw)
                checked["%s/%d" % (fxf, y)] = today.isoformat()
            except Exception as e:  # noqa: BLE001
                if held is None:
                    raise
                failed.append("%d (%s)" % (y, str(e)[:80]))
                out[name][y] = held
        if failed:
            status, detail = "failed", "re-read failed, held copy kept: " + "; ".join(failed[:5])
        elif update and status != "failed":
            status = "changed" if changed else "unchanged"
        outcome[name] = (status, version, detail, fxf)
    return out, outcome


def fetch_retry(fxf, kw, tries=3):
    """A staged re-read, tried again after a dropped connection or a 5xx (DataSF drops one now and then)."""
    for t in range(tries):
        try:
            return sfdata.fetch(fxf, cache_dir=STAGE, refresh=True, **kw)
        except (sfdata.TooFew, sfdata.Truncated):
            raise
        except Exception:  # noqa: BLE001
            if t == tries - 1:
                raise
            time.sleep(10 * (t + 1))


def _params(kw):
    return {"$select": kw["select"], "$where": kw["where"], "$order": ":id"}   # as sfdata.fetch builds them


def _path(d, fxf, kw):
    return Path(d) / ("%s.json" % sfdata._key(fxf, _params(kw)))


def _held(fxf, kw):
    return _path(CACHE, fxf, kw).exists()


def commit_staged():
    """Move every staged read over the held copy (after the checks pass)."""
    if not STAGE.exists():
        return
    CACHE.mkdir(parents=True, exist_ok=True)
    for f in sorted(STAGE.glob("*.json")):
        os.replace(f, CACHE / f.name)
    shutil.rmtree(STAGE, ignore_errors=True)


def drop_staged():
    shutil.rmtree(STAGE, ignore_errors=True)


class Stop(Exception):
    pass


def check_reads(R, today, prev_counts):
    """The fetch checks. Returns the rows read per table and year; raises Stop naming each failure."""
    bad, counts = [], {}
    for name, fxf, _ in TABLES:
        counts[name] = {}
        for y, res in sorted(R[name].items()):
            n = len(res.rows)
            counts[name][str(y)] = n
            fl = floor_for(name, y, today)
            if n < fl:
                bad.append("%s %d: %d rows, floor %d" % (name, y, n, fl))
            prev = (prev_counts.get(name) or {}).get(str(y))
            if prev and n < (1 - MAX_DROP) * prev:
                bad.append("%s %d: %d rows, down from %d last time (more than %d%%)" % (name, y, n, prev, MAX_DROP * 100))
            nocase = sum(1 for r in res.rows if not r.get("case_id_pkey"))
            if nocase:
                bad.append("%s %d: %d rows with no case id" % (name, y, nocase))
            if name == "crashes":   # the one table of the three whose query carries the date
                out = sum(1 for r in res.rows if not str(r.get("collision_datetime") or "").startswith(str(y)))
                if out:
                    bad.append("%s %d: %d rows dated outside the year" % (name, y, out))
    if bad:
        raise Stop("; ".join(bad))
    return counts


def load_people():
    """map.json's people with a case number: {case: (lon, lat)} in the map's order (first person wins, as
    hin-people-map.crash_cards does), and [(case, date, (lon, lat))] for every one, for the cells they fall in."""
    D = json.loads(MAP_JSON.read_text())
    where, all_ = {}, []
    for o in D["people"]:
        if o.get("cs"):
            where.setdefault(o["cs"], tuple(o["c"]))
            all_.append((o["cs"], o["d"], tuple(o["c"])))
    return where, all_


def cell(lon, lat):
    return "%d-%d" % (math.floor(lon * 100) + X0, math.floor(lat * 100) - Y0)


def in_box(lon, lat):
    return BOX[0] < lon < BOX[1] and BOX[2] < lat < BOX[3]


def plan(R, map_where, map_people):
    """Every carded crash: ({case: point drawn around}, {case: [(x, y)] people's points x 1e5}, {case: date},
    {shard: [cases]}, stats). Raises Stop on a failed join."""
    crash, parties, victims = hcc.index_rows([r for y in sorted(R["crashes"]) for r in R["crashes"][y].rows],
                                             [r for y in sorted(R["parties"]) for r in R["parties"][y].rows],
                                             [r for y in sorted(R["victims"]) for r in R["victims"][y].rows], set())
    hurt = {c: sorted(vs, key=lambda v: v.get("victim_id") or "") for c, vs in victims.items()
            if any(v.get("victim_degree_of_injury") in INJURED for v in vs)}
    unjoined = sorted(c for c in hurt if c not in crash)
    if len(unjoined) > MAX_UNJOINED * len(hurt):
        raise Stop("%d of %d crashes with someone hurt are not in the crash table: %s" % (len(unjoined), len(hurt), unjoined[:5]))
    point, at, date, shards, unplaced = {}, {}, {}, collections.defaultdict(set), 0
    for c, vs in sorted(hurt.items()):
        if c not in crash:
            continue
        d = crash[c]["collision_datetime"][:10]
        pts = []
        for v in vs:
            try:
                lon, lat = float(v["tb_longitude"]), float(v["tb_latitude"])
            except (KeyError, TypeError, ValueError):
                continue
            if in_box(lon, lat):
                pts.append((lon, lat))
        if c in map_where:
            point[c] = map_where[c]
        elif pts:
            point[c] = (round(pts[0][0], 6), round(pts[0][1], 6))
        else:
            unplaced += 1
            continue
        # The map's own rounding (street-safety-light.py: round(lon, 5), then x 1e5), so a tie rounds the same way.
        at[c] = sorted({(round(round(lon, 5) * 1e5), round(round(lat, 5) * 1e5)) for lon, lat in pts})
        date[c] = d
        for lon, lat in pts:
            shards["%s/%s" % (d[:4], cell(round(lon, 5), round(lat, 5)))].add(c)
        if not pts:
            shards["%s/%s" % (d[:4], cell(*point[c]))].add(c)
    for c, d, p in map_people:   # the map's own people, at the point and date the map holds for them
        if c in point:
            shards["%s/%s" % (d[:4], cell(*p))].add(c)
    placed = len(point)
    if placed < MIN_PLACED * (placed + unplaced):
        raise Stop("only %d of %d carded crashes have a point" % (placed, placed + unplaced))
    stats = {"crashes_hurt": len(hurt), "not_in_crash_table": len(unjoined), "no_point": unplaced, "carded": placed}
    return (crash, parties, victims), point, at, date, {k: sorted(v) for k, v in shards.items()}, stats


# ---- the build, in worker processes that share the reads by fork ----
G = {}


def hin_fn(lon, lat):
    P = hpm.xy(lon, lat)
    return [y for y, g in G["nets"] if g.nearest(P, hpm.NEAR_FT)]


def line_hashes(lines):
    return [hashlib.sha1(json.dumps(l, sort_keys=True).encode()).hexdigest()[:16] for l in lines]


def reach(lon, lat):
    """The centreline indices hin_crash_cards.geometry visits for a point, in its order."""
    grid = G["net"][1]
    cx, cy = int(lon // hcc.CELL), int(lat // hcc.CELL)
    out = []
    for gx in (cx - 1, cx, cx + 1):
        for gy in (cy - 1, cy, cy + 1):
            out.extend(grid.get((gx, gy), ()))
    return out


def shard_hash(key):
    crash, parties, victims = G["rows"]
    h = hashlib.sha1(G["code"].encode())
    for c in G["shards"][key]:
        lon, lat = G["point"][c]
        h.update(json.dumps([c, [lon, lat], G["at"][c], G["date"][c], crash[c], parties.get(c, []), victims.get(c, []),
                             hin_fn(lon, lat), [G["lh"][i] for i in reach(lon, lat)]], sort_keys=True).encode())
    return h.hexdigest()


def build_shard(key):
    cases = {c: G["point"][c] for c in G["shards"][key]}
    cards, _ = hcc.build(cases, hin_fn, rows=(G["rows"], G["tags"]), net=G["net"])
    for c, cd in cards.items():
        cd["dt"] = G["date"][c]
        cd["at"] = [list(p) for p in G["at"][c]]
    return key, json.dumps({"cards": cards}, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def hash_many(keys):
    return [(k, shard_hash(k)) for k in keys]


def file_sha(p):
    try:
        return hashlib.sha1(p.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true", help="ask DataSF what changed and re-read it before building")
    ap.add_argument("--all", action="store_true", help="rebuild every file")
    ap.add_argument("--workers", type=int, default=min(16, os.cpu_count() or 1))
    a = ap.parse_args()
    today = dt.date.today()
    index_path = OUT / "index.json"
    old_index = json.loads(index_path.read_text()) if index_path.exists() else {}
    prev_counts = old_index.get("reads", {})
    drop_staged()   # reads a stopped run left staged were never checked
    try:
        man = json.loads(MANIFEST.read_text())
    except (FileNotFoundError, ValueError):
        man = {}
    checked = dict(man.get("checked", {}))

    R, outcome = read_tables(a.update, today, checked)
    try:
        counts = check_reads(R, today, prev_counts)
        map_where, map_people = load_people()
        rows, point, at, date, shards, pstats = plan(R, map_where, map_people)
    except Stop as e:
        drop_staged()
        for name, (status, version, detail, fxf) in outcome.items():
            pipeline_state.record("cards:" + fxf, "failed", version=None, detail="checks failed: " + str(e)[:300])
        print("STOPPED: street-safety-cards checks failed: %s" % e, file=sys.stderr)
        sys.exit(1)

    net = hcc.load_network()
    nets = []
    for f in sorted((ROOT / "data/extract/access").glob("hin-[0-9][0-9][0-9][0-9].json")):
        recs = json.loads(f.read_text())["records"]
        nets.append((f.stem[4:], hpm.Grid([([hpm.xy(*q) for q in r["pts"]], True) for r in recs if len(r.get("pts") or []) > 1])))
    code = (pathlib.Path(paths.script("street-safety-cards.py"))).read_text() + (pathlib.Path(paths.script("hin_crash_cards.py"))).read_text()
    tags = {"crashes": "[DataSF ubvf-ztfx — queried %s]" % max(r.fetched_on for r in R["crashes"].values()),
            "parties": "[DataSF 8gtc-pjc6 — queried %s]" % max(r.fetched_on for r in R["parties"].values()),
            "victims": "[DataSF nwes-mmgh — queried %s]" % max(r.fetched_on for r in R["victims"].values())}
    G.update(rows=rows, point=point, at=at, date=date, shards=shards, net=net, nets=nets, code=code, tags=tags,
             lh=line_hashes(net[0]))

    keys = sorted(shards)
    old = man.get("files", {})
    chunks = [keys[i::a.workers] for i in range(a.workers)]
    with multiprocessing.get_context("fork").Pool(a.workers) as pool:
        hashes = dict(kv for part in pool.map(hash_many, chunks) for kv in part)
    todo = [k for k in keys if a.all or old.get(k, {}).get("in") != hashes[k]
            or file_sha(OUT / (k + ".json")) != old.get(k, {}).get("out")]
    print("street-safety-cards: %d files, %d to build" % (len(keys), len(todo)), file=sys.stderr)
    written = 0
    newman = {k: old[k] for k in keys if k in old}
    if todo:
        try:   # hin_crash_cards.build asserts every crash has a party and every victim names one of its crash's
            with multiprocessing.get_context("fork").Pool(a.workers) as pool:
                for k, text in pool.imap_unordered(build_shard, todo, chunksize=8):
                    p = OUT / (k + ".json")
                    written += write_text(str(p), text)
                    newman[k] = {"in": hashes[k], "out": file_sha(p)}
        except Exception as e:  # noqa: BLE001 - the orchestrator puts the previous files back from its snapshot
            drop_staged()
            MANIFEST.write_text(json.dumps({"files": newman, "checked": man.get("checked", {})}, sort_keys=True))
            print("STOPPED: street-safety-cards build failed: %s" % e, file=sys.stderr)
            sys.exit(1)
    # Files no crash falls in any more.
    removed = 0
    for p in sorted(OUT.glob("*/*.json")):
        k = "%s/%s" % (p.parent.name, p.stem)
        if k not in shards:
            p.unlink()
            removed += 1

    # The index and the post-build checks, from the files on disk.
    files, per_year, bad = {}, collections.defaultdict(lambda: collections.Counter()), []
    seen = set()
    for k in keys:
        C = json.loads((OUT / (k + ".json")).read_text())["cards"]
        files[k] = len(C)
        y = k[:4]
        for c, cd in C.items():
            if not (cd.get("hd") and cd.get("pr") and cd.get("g") and cd.get("dt", "")[:4] == y):
                bad.append("%s in %s lacks a header, party list, drawing or its year" % (c, k))
            # Each party's people and injuries, one list per party line, and someone hurt on every card.
            if len(cd.get("pi") or []) != len(cd["pr"]) or not any(e[0] in "ksvp" for row in cd["pi"] for e in row):
                bad.append("%s in %s: the injuries don't line up with its parties, or nobody is hurt" % (c, k))
            if c in seen:
                continue
            seen.add(c)
            per_year[y]["cards"] += 1
            per_year[y]["generic"] += "geo" not in cd["g"]
            per_year[y]["parties"] += len(cd["g"]["p"])
            per_year[y]["parties_no_dir"] += sum(1 for q in cd["g"]["p"] if not q.get("d"))
    if any(EMAIL.search((OUT / (k + ".json")).read_text()) for k in todo):
        bad.append("an e-mail address reached a card file")   # staff addresses are the city's to publish
    # Every dot the map draws finds its card in the file map.js names from its date and point: the light extract's people,
    # joined by case number (tools/street-safety/street-safety-light.py), wherever that case has a card.
    if LIGHT.exists():
        L = json.loads(LIGHT.read_text())
        f = {n: i for i, n in enumerate(L["fields"])}
        tried = found = 0
        cache = {}
        for r in L["people"]:
            c = r[f["case"]]
            if c not in point or r[f["lon"]] is None:   # a person with no point is counted, not drawn: no dot to look up
                continue
            k = "%s/%s" % (r[f["date"]][:4], cell(r[f["lon"]], r[f["lat"]]))
            if k not in cache:
                cache[k] = json.loads((OUT / (k + ".json")).read_text())["cards"] if k in shards else {}
            tried += 1
            cd = cache[k].get(c)
            found += bool(cd and cd["dt"] == r[f["date"]] and [round(r[f["lon"]] * 1e5), round(r[f["lat"]] * 1e5)] in cd["at"])
        if found < 0.999 * tried:
            bad.append("%d of %d dots with a carded case don't find their card by file, date and point" % (tried - found, tried))
        pstats["dots_checked"], pstats["dots_found"] = tried, found
    if len(seen) != len(point):
        bad.append("%d cards on disk, %d crashes planned" % (len(seen), len(point)))
    if bad:
        print("STOPPED: street-safety-cards output checks failed: %s" % "; ".join(bad[:5]), file=sys.stderr)
        sys.exit(1)

    read = max(r.fetched_on for t in R.values() for r in t.values()).isoformat()
    index = {"cell": 0.01, "x0": X0, "y0": Y0, "file": "<year>/<i>-<j>.json", "read": read, "sources": tags,
             "cards": len(seen), "files": files, "by_year": {y: dict(sorted(v.items())) for y, v in sorted(per_year.items())},
             "reads": counts, "crashes": pstats}
    write_text(str(index_path), json.dumps(index, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({"files": newman, "checked": checked}, sort_keys=True))
    commit_staged()
    if a.update:
        for name, (status, version, detail, fxf) in outcome.items():
            pipeline_state.record("cards:" + fxf, status, version=version, detail=detail or None)
    print("street-safety-cards: %d cards in %d files; %d written, %d removed; read %s" % (len(seen), len(keys), written, removed, read),
          file=sys.stderr)
    for y, v in sorted(per_year.items()):
        print("  %s  %5d cards  %4d generic cross (%.1f%%)  parties with no direction %.1f%%" % (
            y, v["cards"], v["generic"], 100.0 * v["generic"] / v["cards"], 100.0 * v["parties_no_dir"] / max(1, v["parties"])), file=sys.stderr)
    if any(s[0] == "failed" for s in outcome.values()):
        print("REFRESH FAILED: " + "; ".join("%s %s" % (n, s[2]) for n, s in outcome.items() if s[0] == "failed"), file=sys.stderr)


if __name__ == "__main__":
    main()
