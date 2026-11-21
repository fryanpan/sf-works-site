"""Compact one UTC day of archived 511 snapshots into one Parquet file per feed, decoded, in the same bucket.

Reads every snapshot the bucket holds for the day (the spool copy when there is one, else the bucket's), decodes it,
and writes gs://$RT_ARCHIVE_BUCKET/sf/parquet/{feed}/YYYY/MM/YYYY-MM-DD.parquet, one row group per hour,
rows sorted by snapshot time, trip and stop sequence.

    trip_updates: one row per stop_time_update (a trip with none gets one row with the stop fields empty):
      snapshot_time, feed_timestamp, entity_id, trip_id, start_date, route_id, direction_id,
      trip_schedule_relationship, vehicle_id, trip_timestamp, stop_sequence, stop_id, arrival_time, arrival_delay, departure_time, departure_delay,
      stop_schedule_relationship
    vehicle_positions: one row per vehicle:
      snapshot_time, feed_timestamp, entity_id, trip_id, start_date, route_id, direction_id, vehicle_id,
      vehicle_label, latitude, longitude, bearing, speed, current_stop_sequence, stop_id, current_status,
      occupancy_status, vehicle_timestamp

Times are UTC; feed_timestamp, trip_timestamp, arrival_time, departure_time and vehicle_timestamp are epoch seconds
as 511 sends them. Each file's key-value metadata "rt_archive" holds a JSON record of the day's gaps (snapshots,
rows, empty_snapshots, max_gap_s), as does its line in state/compactions/. A day is compacted only when it is over,
its spool holds nothing not yet uploaded, and check.py passed it (state/checks/); --force skips the last condition.
The bucket refuses to replace an existing Parquet (the VM holds create, not overwrite), so a day once compacted is
final unless a person deletes it.

Usage: compact.py --pending            # every finished day of the last 7 not yet compacted (what the timer runs)
       compact.py --day 2026-11-10 [--force] [--local-only]
"""

import argparse
import datetime as dt
import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rtarchive as R  # noqa: E402

import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

I64, I32, F32, STR = pa.int64(), pa.int32(), pa.float32(), pa.string()
TS = pa.timestamp("ms", tz="UTC")  # Parquet has no seconds unit; declared as what is stored
SCHEMA = {
    "trip_updates": pa.schema([
        ("snapshot_time", TS), ("feed_timestamp", I64), ("entity_id", STR), ("trip_id", STR), ("start_date", STR),
        ("route_id", STR), ("direction_id", I32), ("trip_schedule_relationship", STR), ("vehicle_id", STR),
        ("trip_timestamp", I64),
        ("stop_sequence", I32), ("stop_id", STR), ("arrival_time", I64), ("arrival_delay", I32),
        ("departure_time", I64), ("departure_delay", I32), ("stop_schedule_relationship", STR)]),
    "vehicle_positions": pa.schema([
        ("snapshot_time", TS), ("feed_timestamp", I64), ("entity_id", STR), ("trip_id", STR), ("start_date", STR),
        ("route_id", STR), ("direction_id", I32), ("vehicle_id", STR), ("vehicle_label", STR), ("latitude", F32),
        ("longitude", F32), ("bearing", F32), ("speed", F32), ("current_stop_sequence", I32), ("stop_id", STR),
        ("current_status", STR), ("occupancy_status", STR), ("vehicle_timestamp", I64)]),
}


def opt(msg, field):
    return getattr(msg, field) if msg.HasField(field) else None


def trip_fields(tr):
    return [opt(tr, "trip_id"), opt(tr, "start_date"), opt(tr, "route_id"), opt(tr, "direction_id")]


def rows_tu(m, snap):
    from google.transit import gtfs_realtime_pb2 as g
    srel = g.TripUpdate.StopTimeUpdate.ScheduleRelationship.Name
    trel = g.TripDescriptor.ScheduleRelationship.Name
    ft = m.header.timestamp
    for e in m.entity:
        if not e.HasField("trip_update"):
            continue
        tu = e.trip_update
        head = [snap, ft, e.id] + trip_fields(tu.trip) + [
            trel(tu.trip.schedule_relationship) if tu.trip.HasField("schedule_relationship") else None,
            opt(tu.vehicle, "id") if tu.HasField("vehicle") else None, opt(tu, "timestamp")]
        if not tu.stop_time_update:
            yield head + [None] * 7
        for s in tu.stop_time_update:
            a = s.arrival if s.HasField("arrival") else None
            d = s.departure if s.HasField("departure") else None
            yield head + [opt(s, "stop_sequence"), opt(s, "stop_id"),
                          opt(a, "time") if a else None, opt(a, "delay") if a else None,
                          opt(d, "time") if d else None, opt(d, "delay") if d else None,
                          srel(s.schedule_relationship) if s.HasField("schedule_relationship") else None]


def rows_vp(m, snap):
    from google.transit import gtfs_realtime_pb2 as g
    status = g.VehiclePosition.VehicleStopStatus.Name
    occ = g.VehiclePosition.OccupancyStatus.Name
    ft = m.header.timestamp
    for e in m.entity:
        if not e.HasField("vehicle"):
            continue
        v = e.vehicle
        p = v.position if v.HasField("position") else None
        vd = v.vehicle if v.HasField("vehicle") else None
        yield [snap, ft, e.id] + trip_fields(v.trip) + [
            opt(vd, "id") if vd else None, opt(vd, "label") if vd else None,
            opt(p, "latitude") if p else None, opt(p, "longitude") if p else None,
            opt(p, "bearing") if p else None, opt(p, "speed") if p else None,
            opt(v, "current_stop_sequence"), opt(v, "stop_id"),
            status(v.current_status) if v.HasField("current_status") else None,
            occ(v.occupancy_status) if v.HasField("occupancy_status") else None, opt(v, "timestamp")]


def snapshot_names(feed, day, b):
    """Every snapshot of the day the bucket holds (or the spool, with --local-only)."""
    if b is None:
        d = os.path.join(R.SPOOL, R.day_prefix(feed, day))
        return sorted(os.path.relpath(os.path.join(p, f), R.SPOOL)
                      for p, _, fs in os.walk(d) for f in fs if f.endswith(".pb.gz"))
    return sorted(x.name for x in b.list_blobs(prefix=R.day_prefix(feed, day)) if x.name.endswith(".pb.gz"))


def read_snapshot(name, b):
    try:
        with open(os.path.join(R.SPOOL, name), "rb") as f:
            return gzip.decompress(f.read())
    except FileNotFoundError:  # never spooled here, or pruned since the listing
        return gzip.decompress(b.blob(name).download_as_bytes())


def compact(feed, day, b, out_path, stats=None):
    """Write the day's Parquet; returns (snapshots, rows). The gaps go in the file's key-value metadata under
    "rt_archive" (and into stats, when a dict is passed): empty_snapshots, the snapshots that gave no rows (511 sent
    an empty feed), and max_gap_s, the longest stretch of the day, its ends included, with no snapshot that did."""
    schema = SCHEMA[feed]
    rows_of = rows_tu if feed == "trip_updates" else rows_vp
    names = snapshot_names(feed, day, b)
    by_hour = {}
    for n in names:
        by_hour.setdefault(R.time_of(n).hour, []).append(n)
    total, empty = 0, 0
    t0 = dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc)
    full = [t0]
    with pq.ParquetWriter(out_path, schema, compression="zstd") as w:
        for h in sorted(by_hour):
            rows = []
            for n in by_hour[h]:
                k = len(rows)
                rows.extend(rows_of(R.decode(read_snapshot(n, b)), R.time_of(n)))
                if len(rows) == k:
                    empty += 1
                else:
                    full.append(R.time_of(n))
            rows.sort(key=lambda r: (r[0], r[3] or "", r[10] if feed == "trip_updates" and r[10] is not None else -1,
                                     r[2]))
            cols = list(zip(*rows)) if rows else [[] for _ in schema]
            w.write_table(pa.table([pa.array(list(c), type=f.type) for c, f in zip(cols, schema)], schema=schema))
            total += len(rows)
        full.append(t0 + dt.timedelta(days=1))
        meta = {"snapshots": len(names), "rows": total, "empty_snapshots": empty,
                "max_gap_s": round(max((b_ - a_).total_seconds() for a_, b_ in zip(full, full[1:])))}
        w.add_key_value_metadata({"rt_archive": json.dumps(meta, sort_keys=True)})
    if stats is not None:
        stats.update(meta)
    return len(names), total


def day_ready(day, force):
    if day >= R.utcnow().date():
        return "the day isn't over"
    pend = [n for n in (os.path.relpath(os.path.join(p, f), R.SPOOL)
                        for feed in R.FEEDS for p, _, fs in os.walk(os.path.join(R.SPOOL, R.day_prefix(feed, day)))
                        for f in fs if f.endswith(".pb.gz"))]
    days = [day + dt.timedelta(days=i) for i in range(0, R.KEEP_LOCAL_DAYS + 2)]
    done = {u["name"] for u in R.read_jsonl("uploads", days)}
    left = [n for n in pend if n not in done]
    if left:
        return "%d spool files of that day are not in the bucket yet" % len(left)
    if not force:
        checks = [c for c in R.read_jsonl("checks", days) if c.get("day") == day.isoformat()]
        # A day whose only failure is its own missing Parquet is ready: that failure is the one compaction fixes.
        if not checks or not checks[-1].get("data_ok", checks[-1]["ok"]):
            return "check.py has not passed it (run check.py --day %s, or compact with --force)" % day
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day")
    ap.add_argument("--pending", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--local-only", action="store_true", help="read the spool, write the Parquet locally, no upload")
    a = ap.parse_args()
    today = R.utcnow().date()
    days = [dt.date.fromisoformat(a.day)] if a.day else [today - dt.timedelta(days=i) for i in range(7, 0, -1)]
    b = None if a.local_only else R.bucket()
    outdir = os.path.join(R.ROOT, "parquet")
    os.makedirs(outdir, exist_ok=True)
    rc = 0
    for day in days:
        for feed in sorted(R.FEEDS):
            name = R.parquet_name(feed, day)
            if b is not None and b.blob(name).exists():
                continue
            why = day_ready(day, a.force) if not a.local_only else None
            if why:
                if a.day:
                    print("%s %s: not compacted, %s" % (day, feed, why), flush=True)
                    rc = 1
                continue
            out = os.path.join(outdir, os.path.basename(name).replace(".parquet", "-%s.parquet" % feed))
            try:
                gaps = {}
                nsnap, nrows = compact(feed, day, b, out, gaps)
                if nsnap and b is not None:
                    b.blob(name).upload_from_filename(out, content_type="application/vnd.apache.parquet",
                                                      if_generation_match=0, timeout=300)
            except Exception as e:  # one day or feed failing mustn't stop the rest; check.py reports the gap
                print("%s %s: compaction failed, %s: %s" % (day, feed, type(e).__name__, str(e)[:200]), flush=True)
                rc = 1
                nsnap = 0
            if (b is not None or not nsnap) and os.path.exists(out):
                os.remove(out)
            if not nsnap:
                continue
            rec = {"day": day.isoformat(), "feed": feed, "snapshots": nsnap, "rows": nrows,
                   "empty_snapshots": gaps.get("empty_snapshots"), "max_gap_s": gaps.get("max_gap_s"),
                   "object": name if b is not None else out, "t": R.utcnow().isoformat()}
            R.append_jsonl("compactions", rec)
            print(json.dumps(rec), flush=True)
    sys.exit(rc)


if __name__ == "__main__":
    main()
