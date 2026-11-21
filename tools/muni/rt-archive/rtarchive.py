"""Shared settings and helpers for the 511 realtime archive (poll.py, compact.py, check.py), run on a cloud VM.

Muni's two GTFS-realtime feeds from 511 (agency SF) are saved raw, one gzip file per poll, first to a local spool that
mirrors the bucket's paths and then to gs://$RT_ARCHIVE_BUCKET/sf/{feed}/YYYY/MM/DD/HH/{ts}.pb.gz (UTC).
The bucket and its Google Cloud project come from the environment, RT_ARCHIVE_BUCKET and GCP_PROJECT, which the
systemd units read from ~/.config/sf-works/env (vm-setup.sh writes it); neither is kept in the repo.
The spool keeps every file for 7 days and never drops one that has not reached the bucket. The 511 token is read
from ~/.511token, where the VM's other 511 scripts read it, and is never printed or logged; neither is a request URL.
"""

import datetime as dt
import json
import os
import subprocess

HOME = os.path.expanduser("~")
ROOT = os.environ.get("RT_ARCHIVE_ROOT", os.path.join(HOME, "rt-archive"))
SPOOL = os.path.join(ROOT, "spool")
STATE = os.path.join(ROOT, "state")
BUCKET = os.environ.get("RT_ARCHIVE_BUCKET", "")
PROJECT = os.environ.get("GCP_PROJECT") or None  # None: the client's default project
AGENCY = "sf"
TOKEN_FILE = os.path.join(HOME, ".511token")
REPO = os.environ.get("ALERT_REPO", "fryanpan/sf-works-site")
LABEL = "data-refresh"
HEARTBEAT_LABEL = "rt-archive"

# feed name in the bucket -> (511 endpoint, poll interval in seconds). Intervals are whole minutes; poll.py fires a feed
# on the minutes divisible by its interval, so Trip Updates take 30 requests an hour and Vehicle Positions 20.
FEEDS = {
    "trip_updates": ("tripupdates", 120),
    "vehicle_positions": ("vehiclepositions", 180),
}
# 511 allows 60 requests per 3,600 s per token. The archive holds itself to 50 in any rolling hour; pull_all.py in
# tools/muni/muni-ewt/ keeps its own log and holds to 8, which leaves 2 spare.
MAX_PER_HOUR = 50
# The token's other user: scripts/muni-ewt/pull_all.py logs every request here. The poller counts those too and keeps
# its own plus theirs at or under SHARED_MAX, so the total stays under 60 whatever cap pull_all.py runs with.
OTHER_REQLOGS = [os.path.join(HOME, "muni-511", "history", "requests.log")]
SHARED_MAX = 58
KEEP_LOCAL_DAYS = 7
ENTITY_RANGE = (10, 3000)  # entities in one snapshot; Muni runs about 600 vehicles at peak and about 50 at 3 am


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def stamp(t):
    return t.strftime("%Y%m%dT%H%M%SZ")


def parse_stamp(s):
    return dt.datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)


def rel_path(feed, t):
    """Bucket-relative object name of a snapshot fetched at t."""
    return "%s/%s/%s/%s.pb.gz" % (AGENCY, feed, t.strftime("%Y/%m/%d/%H"), stamp(t))


def time_of(name):
    return parse_stamp(os.path.basename(name).split(".")[0])


def day_prefix(feed, day):
    return "%s/%s/%s/" % (AGENCY, feed, day.strftime("%Y/%m/%d"))


def parquet_name(feed, day):
    return "%s/parquet/%s/%s/%s.parquet" % (AGENCY, feed, day.strftime("%Y/%m"), day.isoformat())


def append_jsonl(kind, rec, t=None):
    """Append one record to state/<kind>/YYYY-MM-DD.jsonl (UTC day)."""
    t = t or utcnow()
    d = os.path.join(STATE, kind)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, t.strftime("%Y-%m-%d") + ".jsonl"), "a") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")


def read_jsonl(kind, days):
    out = []
    for day in days:
        p = os.path.join(STATE, kind, day.isoformat() + ".jsonl")
        if os.path.exists(p):
            with open(p) as f:
                for line in f:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass  # a line torn by a run killed mid-write; the next run repeats what it recorded
    return out


def bucket():
    from google.cloud import storage  # imported here so poll.py's fetch never waits on it
    if not BUCKET:
        raise SystemExit("RT_ARCHIVE_BUCKET is not set (see ~/.config/sf-works/env)")
    return storage.Client(project=PROJECT).bucket(BUCKET)


def decode(raw):
    from google.transit import gtfs_realtime_pb2
    m = gtfs_realtime_pb2.FeedMessage()
    m.ParseFromString(raw)
    return m


def entity_times(m):
    """The per-entity data timestamps of a snapshot: vehicle.timestamp or trip_update.timestamp, where set."""
    out = []
    for e in m.entity:
        if e.HasField("vehicle") and e.vehicle.timestamp:
            out.append(e.vehicle.timestamp)
        elif e.HasField("trip_update") and e.trip_update.timestamp:
            out.append(e.trip_update.timestamp)
    return out


def gh(*args):
    exe = os.path.join(HOME, ".local", "bin", "gh")
    return subprocess.run([exe, *args, "-R", REPO], capture_output=True, text=True)


def alert(title, body):
    """Open the data-refresh issue, or comment on the open one, as pipeline/site-refresh/refresh.py does."""
    print("ALERT:", title, flush=True)
    text = "%s\n\nFrom the 511 realtime archive (tools/muni/rt-archive/).\n\n```\n%s\n```" % (title, body[-6000:])
    append_jsonl("alerts", {"t": utcnow().isoformat(), "title": title})
    gh("label", "create", LABEL, "--color", "efb118", "--description", "Scheduled data refresh")
    p = gh("issue", "list", "--label", LABEL, "--state", "open", "--json", "number", "--limit", "1")
    try:
        n = (json.loads(p.stdout) or [{}])[0].get("number")
    except ValueError:
        n = None
    if p.returncode and n is None:
        print("gh could not list issues, so the alert stays in state/alerts only:", p.stderr[-300:], flush=True)
        return
    if n:
        gh("issue", "comment", str(n), "--body", text)
    else:
        gh("issue", "create", "--label", LABEL, "--title", "Data refresh failed: " + title, "--body", text)


def heartbeat(what):
    """Record a good check where GitHub can see it; .github/workflows/refresh-watch.yml alerts when it goes stale."""
    gh("label", "create", HEARTBEAT_LABEL, "--color", "4269d0", "--description", "511 realtime archive")
    gh("label", "edit", HEARTBEAT_LABEL, "--description",
       "511 realtime archive; last good %s %s" % (what, utcnow().strftime("%Y-%m-%dT%H:%MZ")))
