"""Average speed along each Muni line the pages list, by tenth of the line and by consecutive stop pair, for each window of the Muni pages (30, 90, 365, 1825 days and max).

Asked for on the Muni line page (Bryan, 2026-11-10): "Can you show speed along the line here and
also show speed above in the map?"
Input: stop_pair_time.py's <ewt>/pairs/<YYYY-MM>.parquet (one row per route, stop pair s0 -> s1, day type, period
and its final and inwin flags: n, obs_s, sch_s, dist), the months each window holds from site/data/muni.json (windows[w].monthList), the lines
it lists (lines: the frequent lines and, since 2026-11-11, the less frequent ones the Lines page lists; cable cars
left out, as in its byPosition charts), SFMTA's GTFS
(.cache/muni-gtfs/muni_gtfs-current.zip) for each line and direction's most common stop pattern, and
site/data/muni-map.json (lines[line].order[dir], the stop_code order the map draws) for the stop-pair keys, and
data/muni-ewt/daily/<YYYY-MM>.csv (ewt_daily.py: each line's miles and observed hours by date) for the check below.
Time: a pair's time is the observed time at s1 minus the observed time at s0 of the same trip on the same day, both
stops observed and consecutive in the trip's timetable. Each trip's final pair, into its last stop, is left out: 511's
time at a trip's last stop is not an arrival (final pairs ran a mean 164 s over schedule in 2026-10 against 2 s for the
rest, at 1.6 to 6 mph, Fable review 2026-11-10). 511 carries one time per stop visit (observed arrival = observed departure, dwell_time_secs 0), so
each pair's time is stop time to stop time: the running time between the two stops plus the time stopped at one of
them. Summed along the line every stop's dwell is counted once, so the speeds are average speed including stops,
the same thing as each line's figure in site/data/muni-lines.json. Distance: the pair's miles from 511's GTFS
shape_dist_traveled (dist_table.py's stop_pairs.parquet, median over months). A pair's
speed is its miles over its mean observed time; a tenth's (and a line's, for the check) is the sum of its pairs' miles
over the sum of their mean times, so each pair counts once, as a trip runs it, however many buses were measured on it
(weighting by buses measured let the well-covered slow pairs outweigh the rest). Each stop pair also says
whether it lies inside the timepoint window, between the first and last interior timepoints of most of the trips
measured on it (inWindow), the stretch the line pages' speed covers.
Scope: as stop_pair_time.py keeps it, all day types, buses scheduled at s0 from 05:00 to 22:59, feed-outage hours and
line-day outages out, a pair dropped when it reads over 60 mph or over three times its scheduled time plus 10 minutes.
Same hours and day types as the line figures in muni-lines.json (trip_time.py's timepoint stretches, 05:00-22:59).
Tenths: a stop's position is its rank in the line and direction's most common GTFS pattern over (stops - 1), the
same position as muni.json byPosition (site_data.py); a pair goes in the tenth of its first stop. A pair on both
directions' patterns (the 15, 28, 36 and 43 have a few: shared loops and terminals) goes in both. Pairs on neither
pattern (a short-turn or a detour) are left out of both outputs, and counted.
Stop pairs: keyed "<from stop_code>-<to stop_code>" for each consecutive pair of muni-map.json order[dir]; a pair with
no measured buses in the window is left out.
Checks (exit 1, nothing written): every window's months have a pairs file; every speed finite and at most 50 mph,
at least 1 mph for a tenth and 0.5 for a pair (a pair into a loop where buses lay over reads about 1 mph: the 12's
13935-16882); every frequent line and direction (byPosition) gets at least 8 of 10 tenths in the 365-day window; at least 80% of
the measured bus-miles on a frequent line in the 365-day window fall on its main pattern; each line's speed over all its pairs
inside the timepoint window, weighted by buses as trip_time.py weights them, within 3% of its line speed for the
period (miles over observed hours in daily/<m>.csv, the figure muni_detail.py writes to muni-lines.json) for the 30,
90 and 365-day windows and 5% for 1825 days and max; a less frequent line gets 5% and 8% (OPEN_TOL), since its
timepoint window moves more between short-turn and full trips.
cover: each line's share of measured bus-miles inside the timepoint window and its speed over all pairs, per window;
the Lines page blanks a line's speed when the share is under half (the 8AX, 25, 39, 56, 57 over 365 days), since
the line figure then covers a small, unrepresentative part of the route. On 2026-11-10 every line was within 2.8% over 365 days
(the 9, 5% off before pairs were matched by timetable rank, within 1.6%). Over the long windows the 29 reads 5% to 6%
slower than its line figure in each month to mid-2023 and about 2% after, and the L 3% to 4% slower in each month from
2024-09 to 2026-08 and within 0.3% after; we haven't found why (timepoint flags or which stops 511 records are the
likeliest). The comparison is printed, with the line's speed over all its pairs beside it:
the line page measures only between each trip's first and last interior timepoint (trip_time.py), so the ends of the
line, where buses are slowest, are outside it, and the all-pairs figure reads slower on lines with long slow ends.
Output: JSON {about, windows: {w: {months, lines: {line: {dir: {tenths: [{tenth, mph, miles}],
pairs: {key: {mph, inWindow}}}}}}}},
sorted and rounded, no run stamp (identical bytes when nothing changed).
Incremental: a step of pipeline/transportation-update.py (muni-speed-along), after muni-site-data and muni-map and
before muni-detail, which carries the result into muni-lines.json. Its pairs come from post_all.sh, which rebuilds
only the months whose input changed. The step reads every input through Python (pairs files opened as well, for the
orchestrator's read trace), so it reruns only when a pairs file, muni.json, muni-map.json, the GTFS or daily/ moved.
Off the VM (no <ewt>/pairs) it says so and exits 0, keeping the last good file.
Usage: python3 tools/muni/muni-ewt/speed_along_line.py [<ewt dir, default ~/muni-511/ewt> [<out.json, default data/muni-ewt/speed_along_line.json>]]
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import sys, os, io, csv, json, math, zipfile
import duckdb

ROOT = paths.ROOT
args = [a for a in sys.argv[1:] if not a.startswith("--")]
ewt = os.path.expanduser(args[0] if args else "~/muni-511/ewt")
out = args[1] if len(args) > 1 else os.path.join(ROOT, "data", "muni-ewt", "speed_along_line.json")
if not os.path.isdir(os.path.join(ewt, "pairs")):
    import time
    age = f", last written {(time.time() - os.path.getmtime(out)) / 86400:.0f} days ago" if os.path.exists(out) else ", and there is no copy"
    print(f"speed along the line: no {ewt}/pairs (not on the VM); last good {out} kept{age}", file=sys.stderr)
    sys.exit(0)
REN = {"C": "CA", "L-OWL": "LOWL", "N-OWL": "NOWL", "LBUS": "L"}
muni = json.load(open(os.path.join(ROOT, "site", "data", "muni.json")))
mmap = json.load(open(os.path.join(ROOT, "site", "data", "muni-map.json")))
CABLE = {"PH", "PM", "CA"}  # turntables set their gaps, as in site_data.py's byPosition
DAILY = os.path.join(ROOT, "data", "muni-ewt", "daily")
_lm = {}
def line_mph(line, ms):
    """The line's speed over months ms: miles over observed hours from daily/<m>.csv, as muni_detail.py's period figure."""
    mi = hr = 0.0
    for m in ms:
        if m not in _lm:
            _lm[m] = {}
            f = os.path.join(DAILY, f"{m}.csv")
            for r in csv.DictReader(open(f)) if os.path.exists(f) else []:
                if r["miles"] and r["obs_hr"] and float(r["obs_hr"]) > 0:
                    a = _lm[m].setdefault(r["route"], [0.0, 0.0])
                    a[0] += float(r["miles"]); a[1] += float(r["obs_hr"])
        a = _lm[m].get(line)
        if a:
            mi += a[0]; hr += a[1]
    return round(mi / hr, 2) if hr else None
FEED = os.path.join(ROOT, ".cache", "muni-gtfs", "muni_gtfs-current.zip")
errors = []

def gtfs(name):
    return csv.DictReader(io.TextIOWrapper(zipfile.ZipFile(FEED).open(name), encoding="utf-8-sig", newline=""))
code = {r["stop_id"]: r["stop_code"] for r in gtfs("stops.txt")}
trips = {r["trip_id"]: (REN.get(r["route_id"], r["route_id"]), r["direction_id"]) for r in gtfs("trips.txt")}
seqs = {}
for r in gtfs("stop_times.txt"):
    if r["trip_id"] in trips:
        seqs.setdefault(r["trip_id"], []).append((int(r["stop_sequence"]), r["stop_id"]))
count = {}
for t, sq in seqs.items():
    pt = tuple(x[1] for x in sorted(sq))
    c = count.setdefault(trips[t], {})
    c[pt] = c.get(pt, 0) + 1
del seqs
# (line, dir) -> {(code s0, code s1): position of s0}, from the most common pattern (ties broken by the pattern itself)
pairpos = {}
for key, c in count.items():
    pat = max(c.items(), key=lambda kv: (kv[1], kv[0]))[0]
    cs = [code.get(s, s) for s in pat]
    pairpos[key] = {(cs[i], cs[i + 1]): i / (len(cs) - 1) for i in range(len(cs) - 1)}
# an ordered stop pair belongs to one direction; find it
owner = {}
for (line, d), pp in pairpos.items():
    for p in pp:
        owner.setdefault((line, p), []).append(d)

TOL = {"30": 0.03, "90": 0.03, "365": 0.03, "1825": 0.05, "max": 0.05}  # see the docstring
OPEN_TOL = {"30": 0.05, "90": 0.05, "365": 0.05, "1825": 0.08, "max": 0.08}  # a less frequent line's
con = duckdb.connect()
con.execute("SET threads=1")  # one thread and sorted rows: the same sums in the same order on every run
result = {}
compare = []
for w, x in sorted(muni["windows"].items()):
    ms = x["monthList"]
    files = [os.path.join(ewt, "pairs", f"{m}.parquet") for m in ms]
    missing = [f for f in files if not os.path.exists(f)]
    if missing:
        errors.append(f"{w}: no pairs file for {missing}"); continue
    for f in files:  # DuckDB reads these itself; open them too, so the orchestrator's read trace sees them
        open(f, "rb").close()
    freq = set((x.get("byPosition") or {}).get("lines", {}))
    lines = sorted(l for l in muni["lines"] if l not in CABLE)
    src = f"read_parquet([{','.join(repr(f) for f in files)}]) WHERE route IN ({','.join(repr(l) for l in lines)}) AND NOT final"
    rows = con.execute(f"""SELECT route, s0, s1, sum(n) n, sum(obs_s) obs_s, sum(n * dist) nmi, sum(n) FILTER (WHERE inwin) nin
      FROM {src} GROUP BY 1, 2, 3 ORDER BY 1, 2, 3""").fetchall()
    # the in-window check: bus-weighted miles over hours on every pair inside the timepoint window, as trip_time.py
    inwin = {r[0]: r[1:] for r in con.execute(f"""SELECT route, sum(n * dist), sum(obs_s) FILTER (WHERE dist IS NOT NULL),
      sum(obs_s) FILTER (WHERE dist IS NULL) FROM {src} AND inwin GROUP BY 1 ORDER BY 1""").fetchall()}
    acc = {}       # (line, dir) -> pair -> [n, obs_s, n*miles]
    off = {}       # line -> [bus-miles on the main pattern, bus-miles off it]
    for route, s0, s1, n, obs, nmi, nin in rows:
        if nmi is None:
            continue
        ds = owner.get((route, (s0, s1)), [])
        o = off.setdefault(route, [0.0, 0.0])
        if not ds:
            o[1] += nmi; continue
        o[0] += nmi
        for d in ds:  # a pair both directions' patterns run (a shared terminal loop, a one-way couplet) goes in each
            acc.setdefault((route, d), {})[(s0, s1)] = (n, obs, nmi, (nin or 0) / n)
    allmi = {}
    for route, s0, s1, n, obs, nmi, nin in rows:
        if nmi is not None:
            allmi[route] = allmi.get(route, 0.0) + nmi
    wl, cover = {}, {}
    for (line, d), pairs in sorted(acc.items()):
        tb = {}
        for p, (n, obs, nmi, _) in pairs.items():
            t = min(int(pairpos[(line, d)][p] * 10), 9)
            a = tb.setdefault(t, [0.0, 0.0])
            a[0] += obs / n; a[1] += nmi / n  # one bus's mean seconds and the pair's miles: each pair once, as a trip runs it
        ten = [{"tenth": t, "mph": round(a[1] / (a[0] / 3600), 2), "miles": round(a[1], 3)} for t, a in sorted(tb.items())]
        order = mmap["lines"].get(line, {}).get("order", {}).get(d, [])
        pk = {}
        for s0, s1 in zip(order, order[1:]):
            if (s0, s1) in pairs:
                n, obs, nmi, sin = pairs[(s0, s1)]
                pk[f"{s0}-{s1}"] = {"mph": round(nmi / (obs / 3600), 2), "inWindow": sin >= 0.5}
        for v, lo in [(t["mph"], 1) for t in ten] + [(v["mph"], 0.5) for v in pk.values()]:
            if not (math.isfinite(v) and lo <= v <= 50):
                errors.append(f"{w} {line} {d}: speed {v} out of range")
        if w == "365" and line in freq and len(ten) < 8:
            errors.append(f"365 {line} {d}: only {len(ten)} tenths")
        wl.setdefault(line, {})[d] = {"tenths": ten, "pairs": dict(sorted(pk.items()))}
    for line in lines:
        o = off.get(line, [0, 0])
        if w == "365" and line in freq and o[0] < 0.8 * (o[0] + o[1]):
            errors.append(f"365 {line}: only {o[0] / max(o[0] + o[1], 1):.0%} of bus-miles on the main pattern")
        tot = list({p: v for (l, d), pr in acc.items() if l == line for p, v in pr.items()}.values())  # each pair once
        if not tot:
            continue
        ours = sum(v[2] / v[0] for v in tot) / (sum(v[1] / v[0] for v in tot) / 3600)
        theirs = line_mph(line, ms)
        iw = inwin.get(line)
        win = iw[0] / (iw[1] / 3600) if iw and iw[1] else None
        nodist = iw[2] / (iw[1] + iw[2]) if iw and iw[2] else 0.0
        # the share of the line's measured bus-miles inside the timepoint window, the stretch its line speed covers
        cover[line] = {"share": round(iw[0] / allmi[line], 3) if iw and iw[0] and allmi.get(line) else 0.0, "allMph": round(ours, 2)}
        compare.append((w, line, round(ours, 2), round(win, 2) if win else None, theirs,
                        round(win / theirs - 1, 3) if theirs and win else None, round(nodist, 4), round(o[0] / max(o[0] + o[1], 1), 3)))
        if theirs and win and abs(win / theirs - 1) > (TOL if line in freq else OPEN_TOL)[w]:
            errors.append(f"{w} {line}: {win:.2f} mph inside the timepoint window against {theirs}, its line speed")
    result[w] = {"months": [ms[0], ms[-1]], "lines": wl, "cover": cover}

print("window line all_pairs_mph in_window_mph line_mph in_window_diff in_window_hours_no_distance main_pattern_share")
for r in compare:
    print(*r)
if errors:
    print("checks failed:", *errors, sep="\n  ", file=sys.stderr); sys.exit(1)
doc = {"about": {"speed": "miles over hours, all day types, buses scheduled 05:00-22:59 at a pair's first stop",
                 "time": "observed time at the next stop minus observed time at this stop, consecutive in the trip's timetable: 511 has one time per stop, so each pair holds the running time plus one stop's dwell",
                 "distance": "511 GTFS shape_dist_traveled between the two stops, median over months",
                 "tenth": "tenth of the line and direction's most common GTFS pattern, by the pair's first stop, as muni.json byPosition; mph is the tenth's miles over the sum of its pairs' mean times, miles its length",
                 "pairs": "keyed <from stop_code>-<to stop_code>, consecutive in muni-map.json order[dir]; inWindow: between the first and last interior timepoints, the stretch the line speed covers",
                 "final": "each trip's last pair, into its last stop, is left out: 511's time there is not an arrival"},
       "windows": result}
text = json.dumps(doc, sort_keys=True, separators=(",", ":"))
if not os.path.exists(out) or open(out).read() != text:
    open(out, "w").write(text)
    print("wrote", out, len(text), "bytes")
else:
    print("unchanged", out)
