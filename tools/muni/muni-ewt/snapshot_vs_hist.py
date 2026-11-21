"""Rebuild one service date's Muni stop arrivals from our 511 realtime snapshots and score them against a reference record.

Bryan, 2026-11-10: "if we save every three minutes is that enough to capture the same data we
get from the historical feed?" The realtime archive (tools/muni/rt-archive/, on the cloud VM) saves Muni's GTFS-rt
trip updates every 2 minutes and vehicle positions every 3. 511's historic stop observations (fetch_hist.py, extract_sf.py)
give an observed time at every stop. This script rebuilds the second from the first and measures the gap.

Subcommands (run on the VM with ~/.venvs/sf-works-geo/bin/python -I):

  rebuild --date YYYY-MM-DD --gtfs <511 operator_id=SF GTFS zip> --tu <parquet>... --vp <parquet>... --out <arrivals.parquet>
          [--vp-every N] [--vp-from HH:MM --vp-to HH:MM]
      One row per scheduled stop visit (trip, stop_sequence) of every trip the timetable runs that date, with:
        tu_arr   from trip updates: a stop leaves a trip's update once the vehicle has passed it, so its time is the last
                 prediction made for it, clamped between that snapshot's trip timestamp minus 120 s and the next snapshot's
                 trip timestamp (the stop was dropped in between). A last prediction more than 240 s ahead of its
                 snapshot rebuilds nothing (the stop may have been dropped without the bus reaching it).
        vp_arr, vp_dep  from vehicle positions: each position is placed on the trip's shape (nearest point of the shape
                 between the vehicle's previous and current stop, in shape_dist_traveled units; a position more than
                 150 m off the shape is dropped), distance is made non-decreasing along the trip, and the time the
                 vehicle reached 10 m before the stop (arrival) and 10 m past it (departure) is interpolated linearly
                 between the two positions either side. A pair of positions more than 900 s apart rebuilds nothing.
        vp_gap   seconds between those two positions.
        vp_fill  'mid' or 'end' where a visit the positions don't bracket is filled from the scheduled running time
                 between rebuilt neighbours (fill_vp; --no-fill leaves them empty, for a reference rebuild).
        arr, src trip updates where present ('tu'), else positions ('vp', or 'vp-fill' for a filled visit).
      --vp-every N keeps every Nth snapshot of positions (N=2 turns 90-second snapshots into 3-minute ones), so the
      interval can be tested against a finer one. --vp-from/--vp-to keep positions in that local clock window only.
      The trip's first stop is left out, as ewt_month.py drops it.

  extract --arrivals <arrivals.parquet> --gtfs <zip> --date YYYY-MM-DD --col arr|tu_arr|vp_arr --out <dir> [--sched <511 extract dir>]
      Writes an extract directory in extract_sf.py's layout (stop_observations, trips, stop_times, calendar_dates, gzipped
      CSV) with the chosen column as the observed time, so ewt_month.py computes excess wait from our rebuild exactly as
      it does from 511's record. The timetable comes from the GTFS zip (trip ids written 'SF:<id>'), or with --sched
      from a 511 historic extract: every visit 511's timetable runs that date, matched to ours by Muni trip number,
      stop and nearest scheduled time, so both sides of a comparison use 511's own timetable rows.

  compare --test <arrivals.parquet> --col <column> --ref <arrivals.parquet> --refcol <column> | --ref511 <511 extract dir>
          --date YYYY-MM-DD [--from HH:MM --to HH:MM] --out <json>
      Joins each reference stop visit to ours on trip and stop and reports: visits in the reference, share we did not
      rebuild, median and 90th-percentile absolute error (seconds), median signed error, broken down by source (tu, vp),
      by the vp position gap, and by line. A 511 visit joins on the Muni trip number (the part of 511's 'SF:<n>:<date>' or
      'SF:<n>_M11:<date>' id before any '_') and stop_id, nearest scheduled time; the reference is 511's observed arrival
      time, else its departure, after ewt_month.py's first-stop and duplicate rules.

  ewt --ref-extract <dir> --test-extract <dir> --date YYYY-MM-DD --work <dir> --out <csv> [--common]
      Runs ewt_month.py on both extracts for the one date and ewt_daily.py on the results (speed fields blank: the seg and
      trip inputs are empty), and writes each line's excess wait both ways, citywide pooled by scheduled departures as
      ewt_aggregate.py pools lines (eb weights), and the difference. --common first cuts both extracts to the stop
      visits both hold, which isolates timing error from lost visits. On a one-day run ewt_month.py's outage rule
      (rule 5) can't fire, since it compares each 10-minute bin with the median of the month's dates.

Interim reference (until 511 posts November's observations): 511 posts a month's historic stop observations at the start
of the next month (historic=2026-11-so returned 404 on 2026-11-11; so did 2026-11-10-so). Until then the reference is
positions at 90 seconds: the old collector (collect_511.py) saved positions every 90 s until 2026-11-10 06:12 UTC, so
Monday 9 November 07:00 to 22:00 local holds both the 90-second record and, by keeping every second snapshot, a 3-minute one.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import datetime as dt
import gzip
import json
import os
import subprocess
import sys
import zipfile
from zoneinfo import ZoneInfo

import duckdb
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TZ = ZoneInfo("America/Los_Angeles")
OFF_ROUTE_M = 150.0      # a position further than this from its trip's shape is dropped
STOP_PAD_M = 10.0        # arrival = reaching STOP_PAD_M before the stop, departure = STOP_PAD_M past it
MAX_SPEED_MPS = 25.0     # a position implying a faster move from the last kept one is dropped
MAX_GAP_S = 900          # positions further apart than this rebuild nothing between them
WINDOW_PAD_M = 100.0     # the shape stretch searched runs this far either side of the previous and current stop
TU_LO_S, TU_TAIL_S = 120, 240
FILL_MID_S, FILL_END_S = 900, 360   # see fill_vp


def day0(date):
    """Epoch second of the GTFS service day's zero: noon local minus 12 h (GTFS reference time)."""
    d = dt.date.fromisoformat(date)
    return int(dt.datetime(d.year, d.month, d.day, 12, tzinfo=TZ).timestamp()) - 43200


def T511(c):
    """Seconds after the service day's zero from 511's time field, written HH:MM:SS or as whole seconds (ewt_month.py's T)."""
    return (f"(CASE WHEN contains({c}, ':') THEN TRY_CAST(split_part({c},':',1) AS INT)*3600+TRY_CAST(split_part({c},':',2) AS INT)*60"
            f"+TRY_CAST(split_part({c},':',3) AS INT) ELSE TRY_CAST({c} AS INT) END)")


def gtfs_dir(zp):
    out = zp[:-4]
    if not os.path.exists(os.path.join(out, "DONE")):
        os.makedirs(out, exist_ok=True)
        zipfile.ZipFile(zp).extractall(out)
        open(os.path.join(out, "DONE"), "w").write("ok\n")
    return out


def load_sched(con, gd, date):
    """Trips the timetable runs on date, and their stop visits with times (seconds after the service day's zero)."""
    ymd = date.replace("-", "")
    wd = dt.date.fromisoformat(date).strftime("%A").lower()
    rd = lambda f: f"read_csv('{gd}/{f}', header=true, all_varchar=true)"
    con.execute(f"""CREATE OR REPLACE TABLE svc AS
      SELECT service_id FROM {rd('calendar.txt')} WHERE {wd}='1' AND start_date <= '{ymd}' AND end_date >= '{ymd}'
        AND service_id NOT IN (SELECT service_id FROM {rd('calendar_dates.txt')} WHERE date='{ymd}' AND exception_type='2')
      UNION SELECT service_id FROM {rd('calendar_dates.txt')} WHERE date='{ymd}' AND exception_type='1'""")
    con.execute(f"""CREATE OR REPLACE TABLE gtrips AS SELECT trip_id, route_id, CAST(direction_id AS INT) dir, shape_id, service_id
      FROM {rd('trips.txt')} WHERE service_id IN (SELECT service_id FROM svc)""")
    T = lambda c: f"(CAST(split_part({c},':',1) AS INT)*3600 + CAST(split_part({c},':',2) AS INT)*60 + CAST(split_part({c},':',3) AS INT))"
    con.execute(f"""CREATE OR REPLACE TABLE gst AS SELECT s.trip_id, CAST(s.stop_sequence AS INT) seq, s.stop_id,
        {T("coalesce(nullif(s.arrival_time,''), s.departure_time)")} sched_arr, {T("coalesce(nullif(s.departure_time,''), s.arrival_time)")} sched_dep,
        CAST(s.shape_dist_traveled AS DOUBLE) sd, t.route_id, t.dir, t.shape_id
      FROM {rd('stop_times.txt')} s JOIN gtrips t USING (trip_id)""")
    # The realtime feeds stamp a trip that starts after midnight with the calendar date it runs on, not its service
    # date (Fable review 2026-11-11, item 5), so each trip carries the start_date its realtime rows will have.
    nxt = (dt.date.fromisoformat(date) + dt.timedelta(days=1)).strftime("%Y%m%d")
    con.execute(f"""CREATE OR REPLACE TABLE gsd AS SELECT trip_id, CASE WHEN min(sched_dep) >= 86400 THEN '{nxt}' ELSE '{ymd}' END rt_date
      FROM gst GROUP BY 1""")
    con.execute(f"""CREATE OR REPLACE TABLE gshape AS SELECT shape_id, CAST(shape_pt_sequence AS INT) i,
        CAST(shape_pt_lat AS DOUBLE) lat, CAST(shape_pt_lon AS DOUBLE) lon, CAST(shape_dist_traveled AS DOUBLE) sd
      FROM {rd('shapes.txt')} WHERE shape_id IN (SELECT DISTINCT shape_id FROM gtrips)""")
    con.execute(f"CREATE OR REPLACE TABLE gstops AS SELECT stop_id, CAST(stop_lat AS DOUBLE) lat, CAST(stop_lon AS DOUBLE) lon FROM {rd('stops.txt')}")


def xy(lat, lon):
    return np.column_stack([np.asarray(lon) * 111320.0 * np.cos(np.radians(37.76)), np.asarray(lat) * 110540.0])


def rebuild_tu(con, tu_files, date, z0):
    ymd = date.replace("-", "")
    src = ", ".join(f"'{f}'" for f in tu_files)
    con.execute(f"""CREATE OR REPLACE TABLE tu AS SELECT trip_id, stop_sequence seq, stop_id,
        coalesce(arrival_time, departure_time) a, coalesce(trip_timestamp, epoch(snapshot_time)::BIGINT) ts,
        epoch(snapshot_time)::BIGINT snap
      FROM read_parquet([{src}]) r SEMI JOIN gsd ON gsd.trip_id = r.trip_id AND gsd.rt_date = r.start_date
      WHERE stop_sequence IS NOT NULL""")
    # every snapshot of each trip (for "the next snapshot after the stop was last listed")
    con.execute("CREATE OR REPLACE TABLE tusnap AS SELECT trip_id, snap, max(ts) ts FROM tu GROUP BY 1, 2")
    con.execute(f"""CREATE OR REPLACE TABLE tuarr AS
      WITH last AS (SELECT trip_id, seq, max(snap) snap, arg_max(a, snap) a, arg_max(ts, snap) ts FROM tu GROUP BY 1, 2),
      nxt AS (SELECT l.*, s.ts ts_next FROM last l ASOF LEFT JOIN tusnap s ON l.trip_id = s.trip_id AND s.snap > l.snap)
      SELECT trip_id, seq, a - ts tu_lead,
        CASE WHEN a IS NULL THEN NULL
             WHEN ts_next IS NULL THEN CASE WHEN a - ts <= {TU_TAIL_S} THEN greatest(a, ts - {TU_LO_S}) END
             WHEN a - ts > {TU_TAIL_S} THEN NULL
             ELSE least(greatest(a, ts - {TU_LO_S}), ts_next) END - {z0} tu_arr,
        ts_next - ts tu_gap
      FROM nxt""")


def fill_vp(con, t_from=None, t_to=None):
    """Fill stop visits the positions bracket badly, from the scheduled running time between rebuilt neighbours.

    'mid': between two rebuilt stops of the trip no more than FILL_MID_S apart, in proportion to scheduled time.
    'end': before the trip's first rebuilt stop or after its last, the nearest rebuilt time shifted by the scheduled
    running time, only where that is at most FILL_END_S (the stops a bus passes in about two 3-minute snapshots: a trip
    starts or ends between snapshots, so its first and last few stops have a position on one side only)."""
    con.execute(f"""CREATE OR REPLACE TABLE vparr AS
      WITH b AS (SELECT g.trip_id, g.seq, g.sched_arr s, v.vp_arr, v.vp_dep, v.vp_gap FROM gst g LEFT JOIN vparr v USING (trip_id, seq)
                 WHERE g.trip_id IN (SELECT trip_id FROM vparr WHERE vp_arr IS NOT NULL)
                   AND g.seq > (SELECT min(seq) FROM gst x WHERE x.trip_id = g.trip_id)),
      n AS (SELECT *, last_value(vp_arr IGNORE NULLS) OVER wp pa, last_value(CASE WHEN vp_arr IS NOT NULL THEN s END IGNORE NULLS) OVER wp ps,
                      first_value(vp_arr IGNORE NULLS) OVER wn na, first_value(CASE WHEN vp_arr IS NOT NULL THEN s END IGNORE NULLS) OVER wn ns
            FROM b WINDOW wp AS (PARTITION BY trip_id ORDER BY seq ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),
                          wn AS (PARTITION BY trip_id ORDER BY seq ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING)),
      f AS (SELECT *, CASE WHEN vp_arr IS NOT NULL THEN NULL
              WHEN pa IS NOT NULL AND na IS NOT NULL AND na - pa <= {FILL_MID_S} AND na >= pa THEN 'mid'
              WHEN pa IS NULL AND na IS NOT NULL AND ns - s BETWEEN 0 AND {FILL_END_S} THEN 'end'
              WHEN na IS NULL AND pa IS NOT NULL AND s - ps BETWEEN 0 AND {FILL_END_S} THEN 'end' END vp_fill FROM n)
      SELECT trip_id, seq,
        CASE WHEN vp_fill IS NULL THEN vp_arr WHEN vp_fill = 'mid' THEN pa + (na - pa) * coalesce((s - ps) / nullif(ns - ps, 0), 0)
             WHEN pa IS NULL THEN na - (ns - s) ELSE pa + (s - ps) END vp_arr,
        CASE WHEN vp_fill IS NULL THEN vp_dep WHEN vp_fill = 'mid' THEN pa + (na - pa) * coalesce((s - ps) / nullif(ns - ps, 0), 0)
             WHEN pa IS NULL THEN na - (ns - s) ELSE pa + (s - ps) END vp_dep,
        vp_gap, vp_fill
      FROM f WHERE vp_arr IS NOT NULL OR vp_fill IS NOT NULL""")
    if t_from is not None or t_to is not None:  # a fill never reaches outside the positions' window
        con.execute(f"""DELETE FROM vparr WHERE vp_fill IS NOT NULL AND (vp_arr < {t_from if t_from is not None else -10**9}
          OR vp_arr >= {t_to if t_to is not None else 10**9})""")


def rebuild_vp(con, vp_files, date, z0, every, t_from, t_to, fill=True):
    ymd = date.replace("-", "")
    src = ", ".join(f"'{f}'" for f in vp_files)
    con.execute(f"""CREATE OR REPLACE TABLE vpsnap AS SELECT snap, row_number() OVER (ORDER BY snap) - 1 k FROM
      (SELECT DISTINCT epoch(snapshot_time)::BIGINT snap FROM read_parquet([{src}]))""")
    win = ""
    if t_from:
        win += f" AND coalesce(vehicle_timestamp, epoch(snapshot_time)::BIGINT) - {z0} >= {t_from}"
    if t_to:
        win += f" AND coalesce(vehicle_timestamp, epoch(snapshot_time)::BIGINT) - {z0} < {t_to}"
    con.execute(f"""CREATE OR REPLACE TABLE vp AS SELECT trip_id, any_value(latitude) lat, any_value(longitude) lon,
        any_value(current_stop_sequence) cseq, any_value(stop_id) csid, any_value(current_status) st, t
      FROM (SELECT v.*, coalesce(vehicle_timestamp, epoch(snapshot_time)::BIGINT) - {z0} t FROM read_parquet([{src}]) v
            JOIN vpsnap s ON s.snap = epoch(v.snapshot_time)::BIGINT
            WHERE s.k % {every} = 0 AND trip_id IN (SELECT trip_id FROM gtrips)
              AND coalesce(start_date, (SELECT rt_date FROM gsd WHERE gsd.trip_id = v.trip_id)) = (SELECT rt_date FROM gsd WHERE gsd.trip_id = v.trip_id)
              AND latitude IS NOT NULL {win})
      GROUP BY trip_id, t""")
    # shapes and stop distances, per shape
    shp = {}
    for sid, lat, lon, sd in con.execute("SELECT shape_id, list(lat ORDER BY i), list(lon ORDER BY i), list(sd ORDER BY i) FROM gshape GROUP BY 1").fetchall():
        p = xy(lat, lon); d = np.asarray(sd, dtype=float)
        seg_len = np.hypot(*np.diff(p, axis=0).T)
        dd = np.diff(d)
        m_per_u = seg_len.sum() / max(d[-1] - d[0], 1e-9)
        shp[sid] = (p, d, m_per_u)
    stops = {}
    for tid, sid, seqs, sds, sids in con.execute("SELECT trip_id, any_value(shape_id), list(seq ORDER BY seq), list(sd ORDER BY seq), list(stop_id ORDER BY seq) FROM gst GROUP BY 1").fetchall():
        stops[tid] = (sid, np.asarray(seqs), np.asarray(sds, dtype=float), sids)
    rows = []
    obs = con.execute("SELECT trip_id, list(t ORDER BY t), list(lat ORDER BY t), list(lon ORDER BY t), list(cseq ORDER BY t), list(csid ORDER BY t) FROM vp GROUP BY 1").fetchall()
    n_off = n_pos = 0
    for tid, ts, lats, lons, cseqs, csids in obs:
        sid, seqs, sds, sids = stops[tid]
        if sid not in shp or np.isnan(sds).any():
            continue
        p, d, mpu = shp[sid]
        a, b = p[:-1], p[1:]
        ab = b - a
        L2 = np.maximum((ab ** 2).sum(1), 1e-9)
        q = xy(lats, lons)
        t = np.asarray(ts, dtype=float)
        dist = np.full(len(t), np.nan)
        pad = WINDOW_PAD_M / mpu
        def place(j, k):
            """Nearest point of the shape between stop k-1 and stop k (index into the trip's stops), or None for the
            whole shape: (metres off the shape, distance along it)."""
            if k is None:
                sel = np.ones(len(a), bool)
            else:
                sel = (d[1:] >= (sds[k - 1] if k > 0 else sds[0]) - pad) & (d[:-1] <= sds[k] + pad)
            if not sel.any():
                return None
            aa, abb, ll = a[sel], ab[sel], L2[sel]
            u = np.clip(((q[j] - aa) * abb).sum(1) / ll, 0, 1)
            e = np.hypot(*(aa + abb * u[:, None] - q[j]).T)
            i = int(np.argmin(e))
            d0, d1 = d[:-1][sel][i], d[1:][sel][i]
            return e[i], d0 + u[i] * (d1 - d0)
        sid_ix = {x: i for i, x in enumerate(sids)}
        for j in range(len(t)):
            # The window is keyed on the position's own stop_id where the trip has it: the static GTFS numbers 740
            # short-pattern trips from 2 while the realtime feed numbers them from 1, so the sequence alone puts the
            # window a stop behind on those (Fable review 2026-11-11, item 2). The sequence is the fallback, and where
            # both exist the window nearer the shape wins.
            ks = []
            if csids[j] is not None and csids[j] in sid_ix:
                ks.append(sid_ix[csids[j]])
            if cseqs[j] is not None and cseqs[j] in seqs:
                ks.append(int(np.searchsorted(seqs, cseqs[j])))
            cands = [r for r in (place(j, k) for k in (ks or [None])) if r is not None]
            if not cands:
                continue
            e, dj = min(cands)
            n_pos += 1
            if e > OFF_ROUTE_M:
                n_off += 1
                continue
            dist[j] = dj
        ok = ~np.isnan(dist)
        t, dist = t[ok], dist[ok]
        if len(t) < 2:
            continue
        # a position implying more than MAX_SPEED_MPS from the last kept one is a misplacement (Fable review, item 13)
        keep = np.ones(len(t), bool); lk = 0
        for j in range(1, len(t)):
            if (dist[j] - dist[lk]) * mpu > MAX_SPEED_MPS * max(t[j] - t[lk], 1):
                keep[j] = False
            else:
                lk = j
        t, dist = t[keep], dist[keep]
        if len(t) < 2:
            continue
        dist = np.maximum.accumulate(dist)  # a vehicle doesn't go backwards along its trip; jitter is flattened
        padu = STOP_PAD_M / mpu
        for s_seq, s_sd in zip(seqs[1:], sds[1:]):  # first stop left out (ewt_month.py rule 1)
            out = []
            for v in (s_sd - padu, s_sd + padu):
                j = int(np.searchsorted(dist, v, side="left"))  # first position at or past v
                if j == 0 or j >= len(dist):
                    out.append((None, None)); continue
                g = t[j] - t[j - 1]
                if g > MAX_GAP_S or dist[j] == dist[j - 1]:
                    out.append((None, g)); continue
                out.append((t[j - 1] + (v - dist[j - 1]) / (dist[j] - dist[j - 1]) * g, g))
            rows.append((tid, int(s_seq), out[0][0], out[1][0], out[0][1]))
    con.execute("CREATE OR REPLACE TABLE vparr (trip_id VARCHAR, seq INT, vp_arr DOUBLE, vp_dep DOUBLE, vp_gap DOUBLE)")
    if rows:
        con.executemany("INSERT INTO vparr VALUES (?, ?, ?, ?, ?)", rows)
    con.execute("ALTER TABLE vparr ADD COLUMN vp_fill VARCHAR")
    if fill:
        fill_vp(con, t_from, t_to)
    return {"positions_placed": n_pos, "positions_off_route": n_off, "trips_with_positions": len(obs)}


def cmd_rebuild(a):
    con = duckdb.connect()
    con.execute("SET threads=6; SET memory_limit='20GB'")
    gd = gtfs_dir(a.gtfs)
    load_sched(con, gd, a.date)
    z0 = day0(a.date)
    hm = lambda s: int(s.split(":")[0]) * 3600 + int(s.split(":")[1]) * 60 if s else None
    diag = {"date": a.date, "trips_scheduled": con.execute("SELECT count(*) FROM gtrips").fetchone()[0]}
    if a.tu:
        rebuild_tu(con, a.tu, a.date, z0)
    else:
        con.execute("CREATE OR REPLACE TABLE tuarr (trip_id VARCHAR, seq INT, tu_lead BIGINT, tu_arr DOUBLE, tu_gap BIGINT)")
    diag.update(rebuild_vp(con, a.vp, a.date, z0, a.vp_every, hm(a.vp_from), hm(a.vp_to), not a.no_fill) if a.vp else {})
    if not a.vp:
        con.execute("CREATE OR REPLACE TABLE vparr (trip_id VARCHAR, seq INT, vp_arr DOUBLE, vp_dep DOUBLE, vp_gap DOUBLE, vp_fill VARCHAR)")
    con.execute(f"""COPY (SELECT g.trip_id, '{a.date}' sdate, g.route_id, g.dir, g.seq, g.stop_id, g.sched_arr, g.sched_dep,
        t.tu_arr, t.tu_lead, t.tu_gap, v.vp_arr, v.vp_dep, v.vp_gap, v.vp_fill,
        coalesce(t.tu_arr, v.vp_arr) arr, CASE WHEN t.tu_arr IS NOT NULL THEN 'tu' WHEN v.vp_arr IS NOT NULL THEN CASE WHEN v.vp_fill IS NULL THEN 'vp' ELSE 'vp-fill' END END src
      FROM gst g LEFT JOIN tuarr t USING (trip_id, seq) LEFT JOIN vparr v USING (trip_id, seq)
      WHERE g.seq > (SELECT min(seq) FROM gst x WHERE x.trip_id = g.trip_id)
      ORDER BY g.trip_id, g.seq) TO '{a.out}' (FORMAT parquet)""")
    r = con.execute(f"""SELECT count(*), count(tu_arr), count(vp_arr), count(arr),
        count(*) FILTER (WHERE tu_arr IS NOT NULL AND vp_arr IS NOT NULL),
        median(abs(tu_arr - vp_arr)), quantile_cont(abs(tu_arr - vp_arr), 0.9) FROM '{a.out}'""").fetchone()
    diag.update(dict(zip(["visits_scheduled", "tu_rebuilt", "vp_rebuilt", "either_rebuilt", "both", "tu_vs_vp_median_abs_s",
                          "tu_vs_vp_p90_abs_s"], r)))
    json.dump(diag, open(a.out.replace(".parquet", ".json"), "w"), indent=1, default=float)
    print(json.dumps(diag, default=float))


def cmd_extract(a):
    con = duckdb.connect()
    os.makedirs(a.out, exist_ok=True)
    ymd = a.date.replace("-", "")
    hms = lambda c: f"printf('%02d:%02d:%02d', CAST({c} AS BIGINT)//3600, (CAST({c} AS BIGINT)%3600)//60, CAST({c} AS BIGINT)%60)"
    if a.sched:
        # 511's own timetable rows for the date; our arrivals keyed onto 511's trip ids by Muni trip number and stop
        for f in ["trips.csv.gz", "stop_times.csv.gz", "calendar_dates.csv.gz"]:
            src = os.path.join(a.sched, f)
            if f == "stop_times.csv.gz" or f == "trips.csv.gz":
                os.system(f"cp '{src}' '{a.out}/{f}'")
            else:
                con.execute(f"""COPY (SELECT * FROM read_csv('{src}', header=true, all_varchar=true) WHERE date = '{ymd}')
                  TO '{a.out}/{f}' (HEADER, COMPRESSION gzip)""")
        # Every visit 511's timetable runs that date, not only the ones 511 observed, so a visit we hold and 511
        # doesn't still counts (Fable review 2026-11-11, item 9). Times parsed in both of 511's forms (item 3).
        rd = lambda f: f"read_csv('{a.sched}/{f}', header=true, all_varchar=true)"
        con.execute(f"""CREATE TABLE ref AS SELECT st.trip_id, split_part(split_part(st.trip_id, ':', 2), '_', 1) tn, st.stop_id,
            st.stop_sequence, t.route_id, t.direction_id, {T511("coalesce(nullif(st.departure_time,''), st.arrival_time)")} s
          FROM {rd('stop_times.csv.gz')} st JOIN {rd('trips.csv.gz')} t USING (trip_id)
          WHERE t.service_id IN (SELECT service_id FROM {rd('calendar_dates.csv.gz')} WHERE date = '{ymd}' AND exception_type = '1')""")
        con.execute(f"""COPY (SELECT r.trip_id, NULL trip_start_time, NULL schedule_relationship, '{ymd}' service_date, NULL vehicle_id,
            r.stop_sequence, CAST(round(x.{a.col}) AS BIGINT) observed_arrival_time, CAST(round(x.{a.col}) AS BIGINT) observed_departure_time,
            '0' uncertainty, NULL dwell_time_secs, NULL scheduled_dwell_time_secs, r.route_id, 'SF' agency_id, r.direction_id,
            NULL from_stop_id, r.stop_id to_stop_id, r.s scheduled_arrival_time, r.s scheduled_departure_time
          FROM ref r JOIN (SELECT *, split_part(trip_id, '_', 1) tn FROM '{a.arrivals}') x ON x.tn = r.tn AND x.stop_id = r.stop_id
            AND abs(x.sched_dep - r.s) <= 1800
          WHERE x.{a.col} IS NOT NULL
          QUALIFY row_number() OVER (PARTITION BY r.trip_id, r.stop_sequence ORDER BY abs(x.sched_dep - r.s)) = 1)
          TO '{a.out}/stop_observations.csv.gz' (HEADER, COMPRESSION gzip)""")
        return
    gd = gtfs_dir(a.gtfs)
    load_sched(con, gd, a.date)
    con.execute(f"""COPY (SELECT 'SF:' || route_id route_id, service_id, 'SF:' || trip_id trip_id, dir direction_id FROM gtrips)
      TO '{a.out}/trips.csv.gz' (HEADER, COMPRESSION gzip)""")
    con.execute(f"""COPY (SELECT DISTINCT service_id, '{ymd}' date, '1' exception_type FROM gtrips)
      TO '{a.out}/calendar_dates.csv.gz' (HEADER, COMPRESSION gzip)""")
    con.execute(f"""COPY (SELECT 'SF:' || trip_id trip_id, {hms('sched_arr')} arrival_time, {hms('sched_dep')} departure_time, stop_id, seq stop_sequence
      FROM gst) TO '{a.out}/stop_times.csv.gz' (HEADER, COMPRESSION gzip)""")
    con.execute(f"""COPY (SELECT 'SF:' || trip_id trip_id, NULL trip_start_time, NULL schedule_relationship, '{ymd}' service_date,
        NULL vehicle_id, seq stop_sequence, CAST(round({a.col}) AS BIGINT) observed_arrival_time, CAST(round({a.col}) AS BIGINT) observed_departure_time,
        '0' uncertainty, NULL dwell_time_secs, NULL scheduled_dwell_time_secs, 'SF:' || route_id route_id, 'SF' agency_id,
        CAST(dir AS VARCHAR) direction_id, NULL from_stop_id, stop_id to_stop_id, sched_arr scheduled_arrival_time, sched_dep scheduled_departure_time
      FROM '{a.arrivals}' WHERE {a.col} IS NOT NULL) TO '{a.out}/stop_observations.csv.gz' (HEADER, COMPRESSION gzip)""")
    print("wrote", a.out, con.execute(f"SELECT count(*) FROM read_csv('{a.out}/stop_observations.csv.gz')").fetchone()[0], "observations")


def cmd_compare(a):
    con = duckdb.connect()
    con.execute("SET threads=4")
    hm = lambda s: int(s.split(":")[0]) * 3600 + int(s.split(":")[1]) * 60
    lo, hi = (hm(a.t_from) if a.t_from else -10 ** 9), (hm(a.t_to) if a.t_to else 10 ** 9)
    con.execute(f"CREATE TABLE test AS SELECT *, split_part(trip_id, '_', 1) tn FROM '{a.test}'")
    if a.ref511:
        ymd = a.date.replace("-", "")
        T = lambda c: (f"(CASE WHEN contains({c}, ':') THEN TRY_CAST(split_part({c},':',1) AS INT)*3600+TRY_CAST(split_part({c},':',2) AS INT)*60"
                       f"+TRY_CAST(split_part({c},':',3) AS INT) ELSE TRY_CAST({c} AS INT) END)")
        # 511's record, with ewt_month.py's first-stop rule (feed sequence 1) and duplicate rule (nearest its scheduled time)
        con.execute(f"""CREATE TABLE ref AS SELECT split_part(split_part(trip_id, ':', 2), '_', 1) tn, to_stop_id stop_id,
            replace(route_id, 'SF:', '') route_id, {T("coalesce(nullif(observed_arrival_time,''), observed_departure_time)")} r,
            {T("coalesce(nullif(scheduled_departure_time,''), scheduled_arrival_time)")} s
          FROM read_csv('{a.ref511}/stop_observations.csv.gz', header=true, all_varchar=true)
          WHERE service_date = '{ymd}' AND CAST(stop_sequence AS INT) > 1
          QUALIFY row_number() OVER (PARTITION BY trip_id, to_stop_id ORDER BY abs(r - coalesce(s, r)), r) = 1""")
        con.execute("UPDATE ref SET r = r + 86400 WHERE s IS NOT NULL AND r < s - 43200")
        con.execute(f"""CREATE TABLE j AS SELECT ref.route_id, ref.r, x.{a.col} t, x.src, x.vp_gap
          FROM ref LEFT JOIN test x ON x.tn = ref.tn AND x.stop_id = ref.stop_id AND abs(x.sched_dep - ref.s) <= 1800
          WHERE ref.r >= {lo} AND ref.r < {hi}
          QUALIFY row_number() OVER (PARTITION BY ref.tn, ref.stop_id, ref.s ORDER BY abs(x.sched_dep - ref.s) NULLS LAST) = 1""")
    else:
        con.execute(f"""CREATE TABLE j AS SELECT x.route_id, f.{a.refcol} r, x.{a.col} t,
            CASE WHEN '{a.col}' = 'arr' THEN x.src WHEN '{a.col}' LIKE 'tu%' THEN 'tu' WHEN x.vp_fill IS NULL THEN 'vp' ELSE 'vp-fill' END src, x.vp_gap
          FROM read_parquet('{a.ref}') f JOIN test x USING (trip_id, seq)
          WHERE f.{a.refcol} IS NOT NULL AND f.{a.refcol} >= {lo} AND f.{a.refcol} < {hi}""")
    q = lambda w="TRUE", g=None: con.execute(f"""SELECT {g + ',' if g else ''} count(*) n, round(1 - count(t)/count(*), 4) not_rebuilt,
        round(median(abs(t - r)), 1) med_abs_s, round(quantile_cont(abs(t - r), 0.9), 1) p90_abs_s, round(median(t - r), 1) med_signed_s
      FROM j WHERE {w} {'GROUP BY 1 ORDER BY 1' if g else ''}""").fetchall()
    res = {"all": q()[0], "by_src": q("t IS NOT NULL", "src"),
           "by_vp_gap": q("t IS NOT NULL AND src = 'vp'", "CASE WHEN vp_gap <= 120 THEN '<=2 min' WHEN vp_gap <= 240 THEN '2-4 min' WHEN vp_gap <= 480 THEN '4-8 min' ELSE '>8 min' END"),
           "by_line": q("TRUE", "route_id"),
           "columns": ["n", "not_rebuilt", "med_abs_s", "p90_abs_s", "med_signed_s"]}
    json.dump(res, open(a.out, "w"), indent=1, default=float)
    print(json.dumps({k: res[k] for k in ("all", "by_src", "by_vp_gap")}, default=float))


def cmd_ewt(a):
    os.makedirs(a.work, exist_ok=True)
    py = sys.executable
    outs = {}
    exs = {"ref": a.ref_extract, "test": a.test_extract}
    if a.common:
        # Both sides cut to the stop visits both hold, so the difference is timing alone, not lost visits (Fable
        # review 2026-11-11, items 1 and 10).
        con = duckdb.connect()
        so = lambda d: f"read_csv('{d}/stop_observations.csv.gz', header=true, all_varchar=true)"
        for name, ex in list(exs.items()):
            other = exs["test" if name == "ref" else "ref"]
            cd = os.path.join(a.work, name + "-common-extract"); os.makedirs(cd, exist_ok=True)
            for f in ("trips.csv.gz", "stop_times.csv.gz", "calendar_dates.csv.gz"):
                os.system(f"cp '{ex}/{f}' '{cd}/{f}'")
            con.execute(f"""COPY (SELECT * FROM {so(ex)} x SEMI JOIN {so(other)} y ON x.trip_id = y.trip_id AND x.stop_sequence = y.stop_sequence)
              TO '{cd}/stop_observations.csv.gz' (HEADER, COMPRESSION gzip)""")
            exs[name] = cd
    for name, ex in exs.items():
        od = os.path.join(a.work, name)
        os.makedirs(os.path.join(od, "seg"), exist_ok=True); os.makedirs(os.path.join(od, "trip"), exist_ok=True)
        subprocess.run([py, "-I", paths.script("ewt_month.py"), ex, od, a.date], check=True)
        con = duckdb.connect()
        seg = os.path.join(od, "seg", f"{a.date}.parquet")
        con.execute(f"""COPY (SELECT ''::VARCHAR route, ''::VARCHAR sdate, 0 hr, 0.0 dist, 0.0 obs_s, 0.0 sch_s LIMIT 0) TO '{seg}' (FORMAT parquet)""")
        con.execute(f"""COPY (SELECT ''::VARCHAR route, ''::VARCHAR sdate, 0 hr, 0.0 dist, 0.0 obs_s LIMIT 0) TO '{os.path.join(od, 'trip', a.date + '.parquet')}' (FORMAT parquet)""")
        csv = os.path.join(od, "daily.csv")
        subprocess.run([py, "-I", paths.script("ewt_daily.py"), os.path.join(od, "hourly", f"{a.date}.parquet"), seg, csv], check=True)
        outs[name] = csv
    con = duckdb.connect()
    con.execute(f"""COPY (WITH r AS (SELECT * FROM read_csv('{outs['ref']}') WHERE eb IS NOT NULL),
        t AS (SELECT * FROM read_csv('{outs['test']}') WHERE eb IS NOT NULL),
        j AS (SELECT r.route, r.eb, r.ewt ewt_ref, t.ewt ewt_test, r.ob ob_ref, t.ob ob_test FROM r FULL JOIN t USING (route)),
        b AS (SELECT * FROM j WHERE ewt_ref IS NOT NULL AND ewt_test IS NOT NULL),
        u AS (SELECT 1 k, route, eb, ob_ref, ob_test, ewt_ref, ewt_test, round(ewt_test - ewt_ref, 3) diff FROM j
          UNION ALL SELECT 0, 'ALL (eb-weighted)', sum(eb), sum(ob_ref), sum(ob_test), round(sum(ewt_ref*eb)/sum(eb), 3),
            round(sum(ewt_test*eb)/sum(eb), 3), round(sum((ewt_test - ewt_ref)*eb)/sum(eb), 3) FROM b)
      SELECT * EXCLUDE (k) FROM u ORDER BY k, eb DESC NULLS LAST, route) TO '{a.out}' (HEADER)""")
    print(open(a.out).read()[:3000])


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("rebuild"); r.add_argument("--date", required=True); r.add_argument("--gtfs", required=True)
    r.add_argument("--tu", nargs="*", default=[]); r.add_argument("--vp", nargs="*", default=[]); r.add_argument("--out", required=True)
    r.add_argument("--vp-every", type=int, default=1); r.add_argument("--no-fill", action="store_true"); r.add_argument("--vp-from"); r.add_argument("--vp-to")
    e = sp.add_parser("extract"); e.add_argument("--arrivals", required=True); e.add_argument("--gtfs"); e.add_argument("--date", required=True)
    e.add_argument("--col", default="arr"); e.add_argument("--out", required=True); e.add_argument("--sched")
    c = sp.add_parser("compare"); c.add_argument("--test", required=True); c.add_argument("--col", default="arr")
    c.add_argument("--ref"); c.add_argument("--refcol", default="vp_arr"); c.add_argument("--ref511"); c.add_argument("--date", required=True)
    c.add_argument("--from", dest="t_from"); c.add_argument("--to", dest="t_to"); c.add_argument("--out", required=True)
    w = sp.add_parser("ewt"); w.add_argument("--ref-extract", required=True); w.add_argument("--test-extract", required=True)
    w.add_argument("--date", required=True); w.add_argument("--work", required=True); w.add_argument("--out", required=True)
    w.add_argument("--common", action="store_true")
    a = ap.parse_args()
    {"rebuild": cmd_rebuild, "extract": cmd_extract, "compare": cmd_compare, "ewt": cmd_ewt}[a.cmd](a)


if __name__ == "__main__":
    main()
