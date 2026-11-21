"""Download 511's current Muni timetable (GTFS, operator_id=SF) into ~/muni-511/rt/gtfs/, one file per feed version.

The Muni daily figures (rt_daily.py) rebuild stop arrivals from the realtime archive against this timetable, because
its trip and stop ids are the ones the realtime feeds carry. The zip is kept as sf-<feed_version>.zip, where
feed_version comes from its feed_info.txt (20260829 for the edition in effect from 29 August 2026); a download whose
version is already on disk is dropped and only the check time is recorded (gtfs/checked).

One request per run, counted in ~/muni-511/history/requests.log, the log pull_all.py keeps and the realtime archive's
poller counts against the shared 58 an hour (tools/muni/rt-archive/rtarchive.py, SHARED_MAX). Like pull_all.py it never
makes more than MAXH requests from that log in any 3,600 s, nor two within GAP seconds, so the token stays inside
511's 60 an hour. Reads the token from ~/.511token and never prints it or the URL; run it without NET_LOG (rt_daily.py
does), since the orchestrator's request log would otherwise hold the URL.
Exit 0 with the path on stdout's last line; exit 1 on a failed download (the timetables already on disk stay).
Usage: python3 fetch_gtfs_511.py [root, default ~/muni-511]
"""
import io, json, os, sys, time, urllib.error, urllib.request, zipfile

H = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/muni-511")
G = os.path.join(H, "rt", "gtfs")
REQLOG = os.path.join(H, "history", "requests.log")
MAXH, GAP = 8, 190  # pull_all.py's limits, on the same log


def wait_for_slot():
    while True:
        now = time.time()
        ts = [float(x) for x in open(REQLOG).read().split()] if os.path.exists(REQLOG) else []
        recent = [t for t in ts if now - t < 3600]
        if len(recent) < MAXH and (not ts or now - max(ts) >= GAP):
            with open(REQLOG, "a") as f:
                f.write("%d\n" % now)
            return
        time.sleep(15)


def main():
    os.makedirs(G, exist_ok=True)
    tok = open(os.path.expanduser("~/.511token")).read().strip()
    url = "https://api.511.org/transit/datafeeds?operator_id=SF&api_key=%s" % tok
    wait_for_slot()
    try:
        with urllib.request.urlopen(url, timeout=600) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        print("http", e.code, flush=True)
        sys.exit(1)
    except Exception as e:  # noqa: BLE001 - a timeout or reset; the timetables on disk stay
        print("fetch failed:", type(e).__name__, flush=True)
        sys.exit(1)
    try:
        z = zipfile.ZipFile(io.BytesIO(body))
        info = z.read("feed_info.txt").decode("utf-8-sig").splitlines()
        head, row = info[0].split(","), info[1].split(",")
        version = row[head.index("feed_version")].strip()
        for need in ("trips.txt", "stop_times.txt", "shapes.txt", "calendar.txt", "stops.txt"):
            z.getinfo(need)
    except Exception as e:  # noqa: BLE001
        print("not a usable GTFS zip:", type(e).__name__, str(e)[:100], flush=True)
        sys.exit(1)
    out = os.path.join(G, "sf-%s.zip" % version)
    if not os.path.exists(out):
        with open(out + ".part", "wb") as f:
            f.write(body)
        os.replace(out + ".part", out)
        print("new feed version", version, len(body), "bytes", flush=True)
    else:
        print("feed version", version, "already on disk", flush=True)
    json.dump({"t": int(time.time()), "version": version}, open(os.path.join(G, "checked"), "w"))
    print(out)


if __name__ == "__main__":
    main()
