#!/usr/bin/env python3
"""Refresh every source behind the transportation pages, then rebuild what changed.

    pipeline/transportation-update.py              # check sources, rebuild changed steps
    pipeline/transportation-update.py --dry-run    # print the plan, run nothing
    pipeline/transportation-update.py --all        # rebuild every step, even unchanged ones
    pipeline/transportation-update.py --only coordination-projects,department-overlap

Two kinds of step, run in the order of STEPS:

  source  asks each publisher whether anything changed (DataSF rowsUpdatedAt,
          ArcGIS row counts and edit dates, the sfmta.com sitemap's lastmod,
          an Overpass edited-since count, the meeting sites' own listings) and
          reads only what did. Every source step runs on every run; what it
          re-reads is its own business, and each script's --update says how.
  build   turns what is on disk into out/ and site/data/. It is skipped when
          the files it read last time, the directories it listed, the repo
          modules it imported and its own script all hash the same as they did
          then, and every file it wrote still hashes as it wrote it. An output
          reverted, hand-edited or committed stale after the step ran reruns
          the step. The first run of a step, and any run with --all, runs it.
          Reads and writes are recorded by lib/trace_io/sitecustomize.py,
          so nobody keeps a list of inputs or outputs by hand.

Fetch log. Every source step runs with lib/trace_io on its path and
NET_LOG set, so each HTTP request it makes (urllib, or requests through
urllib3) is recorded: method, URL, status, body bytes received. The run prints
one line per source step, requests and bytes by host, and keeps the full list
in data/pipeline-state/net-<step>.jsonl. A run with no new data shows only
change checks there: metadata, statistics, listings, sitemaps, HEADs.

Quality. Every source step has checks in pipeline/transportation-quality.py
(row count against a floor and the previous data, required fields, dates in
range, unique keys, joins that neither drop nor duplicate rows). Before the
step runs, every path it can write is snapshotted (lib/snapshot.py);
after it, its checks run. A failing check, or a step that exits non-zero,
puts the snapshot back (the previous data, byte for byte, with its
modification times and the source markers in sources.json), records the
failure under "quality:<step>" in sources.json, skips every build step and
every step after the first build, and ends the run with exit 1 naming the
check. Other source steps still run, since none reads another's data. A
build step with checks in the same file (coordination-projects,
department-overlap) is guarded the same way: a failing check puts its
previous outputs back and skips every step after it.

Refresh failures. A source whose publisher did not answer keeps its last good
copy (requirement 1), and the script records its own marker check as failed
in sources.json and exits 0, so the builds run on that copy. A script that
reads through lib/fetch.py gets this from read() and upstream_failed():
an HTTP 5xx or a timeout is retried with backoff and then recorded so; any
other read error exits 2, which stops the run like a failed check. Such a source is not recorded as checked: its extract:<src>
entry says failed and keeps the time of its last good check, which is what
the freshness check (F3) ages it from. The run summary names every source whose refresh failed, and the run
exits 2.

Exit codes: 0 every step ran or was current; 1 a source failed its quality
checks and the build stopped (STOPPED: ...), or a step exited non-zero; 2 no
step failed, but a source's refresh did and its last good copy was used.

Idempotence. Every step's outputs are snapshotted before it runs; a file whose
new text differs from the old only in a run stamp ("generated", "queried
2026-09-28") is put back byte for byte (lib/stable.py). Python's hash
seed is fixed, so set iteration and the ties it breaks do not move between
runs. A second run with no new data leaves `git status` as it was.

State lives in data/pipeline-state/ (gitignored): sources.json, the last check
of each source, which the audit's freshness check (F3) reads; steps.json, each
build step's input hash and traced reads.

Board docs: when the BOARD_DOCS setting (lib/settings.py) maps generated files
to review-board docs, the run ends by naming every such file that changed.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import datetime as dt
import glob
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import pipeline_state, quality, stable  # noqa: E402
from lib.snapshot import Snapshot  # noqa: E402

QUALITY = paths.load("transportation-quality.py")

# PIPELINE_STATE_DIR moves all of it, as it moves sources.json (lib/pipeline_state.py).
STATE_DIR = os.environ.get("PIPELINE_STATE_DIR") or os.path.join(ROOT, "data", "pipeline-state")
STATE = os.path.join(STATE_DIR, "steps.json")
TRACE_DIR = os.path.join(paths.LIB, "trace_io")
PY = sys.executable

# DataSF datasets the transportation scripts read through lib/sfdata.py.
SOCRATA = QUALITY.SOCRATA
SNAPSHOTS = os.path.join(STATE_DIR, "snapshots")

# Generated files someone reviews on a board, by repo path -> board doc id: the BOARD_DOCS setting (lib/settings.py),
# empty when unset. The run's summary lists which of them changed, so their board copies can be re-read.
from lib import settings  # noqa: E402
BOUND = settings.get_json("BOARD_DOCS", {})


def where(script):
    """A script's path from the repo root, found by its file name (lib/paths.py); a folder in front is ignored."""
    return os.path.relpath(paths.script(os.path.basename(script)), ROOT)


def py(script, *args):
    return [PY, where(script), *args]


def venv(script, *args):
    """A script that needs numpy, GrowBikeNet or Pillow, run in the analysis
    virtualenv (pipeline/venv-step.py). Without the virtualenv the step keeps
    its last outputs and the run names venv:sf-works-geo under REFRESH FAILED."""
    return py("venv-step.py", where(script), *args)


def node(script, *args):
    return ["node", os.path.join("site", "scripts", script), *args]


# name, kind, command, outputs to guard (globs), extract sources it refreshes,
# minimum days between runs (a source with no change marker to ask).
STEPS = [
    # ---- sources -------------------------------------------------------------
    ("socrata", "source", py("refresh-socrata.py", *SOCRATA), [], [], 0),
    ("extracts", "source", py("refresh-extracts.py"), [],
     ["sfmta-bikeway", "sfmta-bci", "slow-streets", "census-blocks", "libraries", "cpad"], 0),
    ("mirror:bos", "source", py("fetch-bos-meetings.py"), ["data/bos-meetings/**"], [], 0),
    ("mirror:public-works", "source", py("fetch-public-works-commission.py"), ["data/public-works-commission/**"], [], 0),
    ("mirror:rec-park", "source", py("fetch-rec-park-commission.py"), ["data/rec-park-commission/**"], [], 0),
    ("mirror:sfcta", "source", py("fetch-sfcta-board.py"), ["data/sfcta-board/**"], [], 0),
    ("mirror:sfmta-board", "source", py("fetch-sfmta-board.py", "--update"), ["data/sfmta-board/**"], [], 0),
    ("mirror:sfmta-hearings", "source", py("fetch-sfmta-hearings.py"), ["data/sfmta-hearings/**"], [], 0),
    ("mirror:sfpuc", "source", py("fetch-sfpuc-commission.py"), ["data/sfpuc-commission/**"], [], 0),
    # Meetings not yet held at those bodies, and SFMTA's events, for the
    # project record's "upcoming" lists; every listing re-read each run.
    ("upcoming-meetings", "source", py("upcoming-meetings.py", "--update"), ["data/upcoming-meetings/*"], [], 0),
    ("sfmta-projects", "source", py("sfmta-projects.py", "--update"), ["out/sfmta-projects/*"], [], 0),
    # --sitemap: out/sfmta-projects/pages.json holds every sfmta.com project
    # page, which the department matcher and the project record read. Without
    # it the step rewrote that file with the 120 bike pages alone (of 417).
    ("sfmta-project-pages", "source", py("sfmta-project-pages.py", "--sitemap", "--update"),
     ["out/sfmta-projects/pages.json"], ["sfmta-pages"], 0),
    # Construction and consultation dates read off those pages by Claude Opus;
    # only a page whose text changed is re-asked, and a run stops before $50.
    # Needs ANTHROPIC_API_KEY in the environment when a page has changed;
    # without it the last answers are kept and the run exits 2 naming
    # reader:sfmta-page-dates.
    ("sfmta-page-dates", "source", py("sfmta-page-dates.py", "--update"), ["out/sfmta-page-dates/*"], [], 0),
    ("sfmta-hearings", "source", py("sfmta-hearings.py", "--since", "2010-01-01", "--pages", "10", "--update"),
     ["out/sfmta-hearings/*"], ["sfmta-hearings"], 0),
    ("sfmta-board-records", "source", py("sfmta-board-records.py", "--since", "2019-01-01", "--update"),
     ["out/sfmta-board/*"], ["sfmta-board"], 0),
    # Legistar's search has no change marker, so this year's and last year's
    # searches are re-run, at most once a day.
    ("bos-street-records", "source", py("bos-street-records.py", "--update"), ["out/bos-records/*"], [], 1),
    ("sfpuc-commission", "source", py("sfpuc-commission.py", "--update"),
     ["out/sfpuc-commission/*"], ["sfpuc-commission"], 0),
    ("dpw-projects", "source", py("dpw-projects.py", "--update"), ["out/dpw-projects/*"], ["dpw-projects"], 0),
    ("sf-mode-share", "source", py("sf-mode-share.py", "--update"), ["site/data/mode-share.json"], ["census-acs"], 0),
    ("osm-sfmta-compare", "source", py("osm-sfmta-compare.py", "--update"), ["out/osm-compare/*"], [], 0),
    # OpenStreetMap's walkable ways, which every "within reach" distance is
    # walked along (lib/walknet.py); re-read when any was edited.
    ("osm-walk-network", "source", py("osm-walk-network.py", "--update"), ["data/osm-cache/sf-walk.json"], [], 0),
    # OpenStreetMap's drivable ways, which school-sim routes a car along (the
    # walk network leaves out streets whose sidewalks are their own ways).
    ("osm-drive-network", "source", py("osm-drive-network.py", "--update"), ["data/osm-cache/sf-drive.json"], [], 0),
    # Census block outlines, so a block's walk starts at its street frontage.
    ("census-block-outlines", "source", py("census-block-outlines.py", "--update"),
     ["data/extract/census-blocks/outlines-*.json"], [], 0),
    ("census-children", "source", py("census-children.py", "--update"), ["data/extract/census-dhc/*.json"], [], 0),
    # CDE enrolment by grade for the school case study's public schools: the
    # mode split's grade weights and the cars at the bell.
    ("school-enrolment", "source", py("school-enrolment.py", "--update"), ["data/school-case/enrolment.json"], [], 0),
    # Each school's CDE point against the city's address point for its street
    # address (EAS); a point over 500 ft off moves to the EAS point for every
    # school script (CDE put Treasure Island's Life Learning Academy in SoMa).
    ("school-points", "source", py("school-points.py", "--update"), ["data/school-sim/school-points.json"], [], 0),
    # CDE's Census Day enrolment for every SF school and SFUSD's requests per
    # seat, and the distance curve fit to them, which spreads each case study
    # school's students over the blocks they likely live on.
    ("school-gravity", "source", venv("school-gravity.py", "--update"),
     ["data/school-case/enrolment-sf.json", "data/school-case/requests-per-seat.json", "data/school-case/gravity.json",
      "site/data/school-gravity.json"], [], 0),
    # SF Planning's Environmental Justice Communities map and each block's
    # score on it, for school-budget's equity-first strategy.
    ("ej-communities", "source", py("ej-communities.py", "--update"), ["data/extract/ej-communities/*.json"], [], 0),
    # The district outlines behind the bike post's contact-officials block.
    ("supervisor-districts", "source", py("supervisor-districts.py", "--update"), ["site/data/supervisor-districts.json"], [], 0),
    # The city's address points, boiled down for School Trips' address box.
    ("sf-address-points", "source", py("sf-address-points.py", "--update"), ["site/data/sf-addresses.json"], [], 0),
    ("street-work-list", "source", py("street-work-list.py", "--update"), ["out/street-work/*"], [], 0),
    # SFMTA's GTFS schedule (Last-Modified and ETag on one HEAD), and the Muni
    # routes and bell-hour arrivals near the school case study's ten schools.
    ("muni-gtfs", "source", py("muni-gtfs.py", "--update"), [".cache/muni-gtfs/*", "site/data/muni-schools.json"], [], 0),
    # The Muni 511 archive, run on the VM itself (tools/muni/muni-ewt/vm_local.sh):
    # fetch any month 511 has newly posted, rebuild only the months that moved,
    # and copy the summaries into data/muni-ewt/. Off the VM it says so and
    # exits 0, and the builds run on the copy in the repo.
    ("muni-511", "source", ["bash", where("vm_local.sh")], ["data/muni-ewt/**"], [], 0),
    # The Muni daily figures for the days 511's monthly records don't cover yet, rebuilt on the VM from our
    # realtime archive (tools/muni/muni-ewt/rt_daily.py): each new service date once its buses have all run, then
    # that month's excess wait, speed and running time with the monthly scripts. Runs after muni-511 so a month
    # 511 has just posted moves the start, and its comparison with the archive days runs the same morning.
    # Interval: daily (Bryan, 2026-11-12: "Daily"); the timer fires at 13:15 UTC,
    # after yesterday's last bus, and the muni-rt/newest-day check fails once the newest day is over 2 days old.
    ("muni-rt-daily", "source", venv("muni-ewt/rt_daily.py", "--update"), ["data/muni-ewt/rt/**"], [], 0),
    # Each line's timetable by month (buses in service, minutes between buses), for Upgrade a Bus Line's history charts
    # and its newest month: tools/muni/muni-ewt/timetable_month.py --update adds the rows of any month 511 has posted
    # (a DONE file under ~/muni-511/history on the VM, which muni-511 above fetches) that the tracked file lacks, and
    # reads nothing else. Off the VM it says so and exits 0. Interval: daily; a new month arrives about once a month.
    ("muni-timetable-history", "source", venv("muni-ewt/timetable_month.py", "--update"),
     ["data/muni-ewt/optimizer/timetable_month.csv"], [], 0),
    # How full Muni buses are, from SFMTA's live occupancy levels in the same archive (tools/muni/muni-ewt/crowding_update.py,
    # which runs crowding_by_hour.py and crowding_levels.py over the newest four weeks of compacted day files, plus
    # today's UTC day decoded from raw snapshots, on the VM only). Interval: daily; the 13:15 UTC run sees yesterday's
    # whole service day, and the muni-crowding/newest-day check fails once the newest complete one is over 2 days old.
    ("muni-crowding", "source", venv("muni-ewt/crowding_update.py", "--update"),
     ["data/muni-ewt/optimizer/crowding_by_hour.csv", "data/muni-ewt/optimizer/crowding_by_hour.json",
      "data/muni-ewt/optimizer/crowding_levels_hour.csv", "data/muni-ewt/optimizer/crowding_levels_along.csv",
      "data/muni-ewt/optimizer/crowding_levels.json"], [], 0),
    # SFMTA's service hours delivered (DataSF rowsUpdatedAt) and boardings by
    # route (no marker; the whole 1 MB CSV re-read) for the Muni pages.
    ("muni-service-delivered", "source", py("muni-ewt/fetch_service_delivered.py", "--update"),
     ["data/muni-ewt/service_delivered.csv", "data/muni-ewt/service_delivered_target.json"], [], 0),
    # SFMTA's share of scheduled service delivered by mode and month (transtat, no marker; the whole 1 MB table
    # re-read), which Upgrade a Bus Line's fill-missed-trips fix is sized on. Interval: daily.
    ("muni-delivered-by-mode", "source", py("muni-ewt/fetch_delivered_by_mode.py", "--update"),
     ["data/muni-ewt/lever/delivered_by_mode.csv"], [], 0),
    ("muni-ridership", "source", py("muni-ewt/fetch_ridership.py", "--update"),
     ["data/muni-ewt/ridership.csv", "data/muni-ewt/weekday_boardings_published.csv"], [], 0),
    # SFMTA's yearly Muni Rider Survey satisfaction (no marker; a 200-byte CSV re-read).
    ("muni-satisfaction", "source", py("muni-ewt/fetch_satisfaction.py", "--update"),
     ["data/muni-ewt/satisfaction.csv"], [], 0),
    # SFMTA's published percent of trips crowded by route and month (no marker; the whole 110 KB CSV re-read), which
    # the Muni overview sets beside the occupancy levels from our archive.
    ("sfmta-crowding", "source", py("muni-ewt/sfmta_crowding.py", "--update"),
     ["data/muni-ewt/optimizer/sfmta_crowding.csv", "data/muni-ewt/optimizer/sfmta_crowding_read.json"], [], 0),
    # Residents' Telraam window counters (tools/street-safety/telraam-sf.py), which hin-cut-through.py joins to the Street Safety
    # map's traffic stress blocks. Telraam has no change marker: closed three-month chunks are never re-read, the open
    # one is re-read once per window end. Interval: weekly (at most one good run in 7 days; a failed one is retried on the next run). Needs TELRAAM_API_KEY in the
    # environment; without it the last segments.json is kept and the run names telraam:segments under REFRESH FAILED.
    ("telraam", "source", py("telraam-sf.py", "--update"), ["data/extract/telraam/segments.json"], [], 7),
    # SFPD incident reports (DataSF wg3w-h783) for the Street Safety map's crime view: every report since 2018 by place,
    # year, kind, day and time, and the newest 12 months of person crimes (tools/street-safety/sfpd-person-crimes.py). Asks
    # rowsUpdatedAt first; on a change it re-reads the recent years, older ones from a cache of at most 90 days.
    # Interval: daily, with the scheduled run. Before street-safety-map, which reads it.
    ("sfpd-crime", "source", py("sfpd-person-crimes.py", "--update"), ["data/extract/sfpd-person-crimes/*"], [], 0),
    # The Street Safety map's crash cards: one for every injury crash since 2005 at every severity, one file per year and
    # 0.01 degree cell (tools/street-safety/street-safety-cards.py). Asks rowsUpdatedAt of the crash, parties and victims tables; on
    # a change re-reads this year's and last year's queries (older years once their copy is 90 days old), checks them,
    # and rebuilds only the files whose inputs hash differently. Interval: daily, with the scheduled run. Before
    # street-safety-map, which checks that every person it draws with a case number has a card.
    ("street-safety-cards", "source", py("street-safety-cards.py", "--update"),
     ["site/data/street-safety/cards/**", "data/socrata-cache/street-safety-cards/*"], [], 0),
    # The crash reads of the Street Safety map and the injury pages (tools/street-safety/street-safety-crashes.py): every DataSF
    # query of the victims, parties, crashes and fatality log tables that lib/street_safety_reads.py names,
    # held in data/socrata-cache/street-safety/. Reads a query with no held copy cold; asks rowsUpdatedAt of each
    # table and on a change re-reads that table's queries; checks every read before it is held and keeps the last good
    # copy on a failed read. Interval: daily, with the scheduled run. Before hin-injuries, hin-densest,
    # street-safety-light, injury-map and injury-severe-why, which read them.
    ("street-safety-crashes", "source", py("street-safety-crashes.py", "--update"), ["data/socrata-cache/street-safety/*"], [], 0),
    # DataSF's three injury-crash tables with vehicle and street columns added (pipeline/crash-augment/crash-augment.py):
    # a held copy of every row that reads only rows whose data_updated_at moved, then the vehicle lane (clean make,
    # model, estimated curb weight from NHTSA vPIC), the street lane (speed limit, street class, lanes, EPC, and dated
    # safety treatments as of each crash) and the merge, each checked before it replaces the last good build.
    # Interval: daily, with the scheduled run.
    ("crash-augment", "source", py("crash-augment.py", "--update"),
     ["data/socrata-cache/crash-augment/**", "data/socrata-cache/crash-augment-street/**", ".cache/crash-augment/**",
      "out/crash-augment/**", "pipeline/crash-augment/vehicles/make-model-lookup.csv",
      "pipeline/crash-augment/vehicles/body-type-averages.json", "pipeline/crash-augment/vehicles/match-summary.json"],
     [], 0),
    # ---- builds --------------------------------------------------------------
    # Appendix L's rows placed on the street centerline by name, from the
    # plan's appendix PDF; the trace reads which blocks the index names.
    ("north-star-index", "build", py("north-star-index.py"),
     ["out/north-star/segments.geojson", "out/north-star/index.csv", "out/north-star/unmatched.csv",
      "out/north-star/comparison.md"], [], 0),
    # The plan's network, read off SFMTA's North Star map PDF with Appendix L's
    # named blocks. Reruns when the script, the map or the placement changes.
    # First of the builds: sf-streets, the bike history and every plan step
    # after it read the trace.
    ("north-star-trace", "build", py("north-star-map-trace.py"), ["out/north-star/map-trace/*"], [], 0),
    # The plan's own words for each facility class, read off the plan PDF
    # (cached in .cache/north-star-plan/, fetched when missing).
    ("plan-class-definitions", "build", py("plan-class-definitions.py"),
     ["out/north-star/class-definitions.json"], [], 0),
    ("north-star-copy", "copy", None, ["site/data/north-star/*", "site/data/class-definitions.json"], [], 0),
    ("sf-streets", "build", py("sf-streets.py"), ["site/data/sf-streets.json"], [], 0),
    ("project-blocks", "build", py("project-blocks.py"), ["out/project-record/project-blocks.json"], [], 0),
    ("project-record", "build", py("project-record.py"), ["out/project-record/*", "site/data/project-records.json"], [], 0),
    # Reads the project record to match pages to jobs, and re-reads department
    # pages over a week old, so it is a source and runs every time.
    ("department-project-pages", "source", py("department-project-pages.py", "--update"),
     ["out/department-pages/*", "data/extract/sfpuc-projects/*"], [], 0),
    # The same Opus reading for every Public Works and SFPUC project page those
    # two steps keep, re-asked only for a page whose text changed. Without
    # ANTHROPIC_API_KEY the last answers are kept and the run exits 2 naming
    # reader:dept-page-dates.
    ("dept-page-dates", "source", py("sfmta-page-dates.py", "--pages", "departments", "--update"),
     ["out/dept-page-dates/*"], [], 0),
    ("bike-reported-work", "build", py("bike-reported-work.py"), ["site/data/bike-history/*"], [], 0),
    # The typical city block, which the one- and two-block distances use.
    ("sf-block-length", "build", py("sf-block-length.py"), ["out/block-length/*"], [], 0),
    ("bike-network-history", "build", py("bike-network-history.py"),
     ["out/bike-network-history/*", "site/data/bike-history/*"], [], 0),
    # Removed bikeway blocks (from what bike-network-history wrote) and the
    # pandemic Slow Streets SFMTA's Board reports name; fetches nothing.
    ("bike-removals", "build", py("bike-removals.py"), ["site/data/bike-history/removed.json"], [], 0),
    ("bike-network-projects", "build", py("bike-network-projects.py"), ["site/data/bike-history/projects.json"], [], 0),
    ("bike-progress", "build", py("bike-progress.py"),
     ["out/bike-progress/*", "site/data/bike-progress.json", "site/data/north-star/status.json"], [], 0),
    # The explorer's walking distances per bikeway code, today's and the plan's
    # (reads status.json from bike-progress and reach.json from the history).
    ("walk-reach", "build", py("walk-reach.py"), ["site/data/bike-history/walk-reach.json"], [], 0),
    # Community plans' proposed bikeways graded against today's all-ages network (site/data/bike-history) and the
    # plan's traced line, for /transportation/bike/community-plans; reruns when the network changes.
    ("community-plan-bikeways", "build", py("community-plan-bikeways.py"),
     ["out/community-plans/*", "site/data/community-plans/blocks.json"], [], 0),
    ("school-travel-time", "build", venv("school-travel-time.py"), ["out/school-travel/*"], [], 0),
    # Re-derives a random 200 blocks' minutes, and the edge cases, with a plain
    # search written apart from the fast one; exits 1 on any disagreement.
    ("school-travel-check", "build", py("school-travel-check.py"), ["out/school-travel-check/*"], [], 0),
    # Checks access-time.py's last output, out/access/, for the k nearest of
    # several destination types. access-time itself left STEPS on 2026-10-05:
    # nothing reads its output, and it is a heavy venv run.
    ("access-time-check", "build", py("access-time-check.py"), ["out/access-check/*"], [], 0),
    # The full access map: how often Muni comes at every stop (the held GTFS zip), every
    # destination's points (Rec and Park and Planning's zoning through the socrata step), walk and low-stress bike
    # minutes (access-time on School Trips' protected network, and again with Furth's LTS 1 streets as the check),
    # the LTS comparison, and the per-block table. The Muni minutes it merges, out/full-map/transit.json, come from
    # a sim VM (scripts/full-map-transit-vm.sh), never this Mac, and are committed like any other input.
    ("muni-frequency", "build", py("muni-frequency.py"), ["out/full-map/muni-stops.json"], [], 0),
    ("full-map-destinations", "build", venv("full-map-destinations.py"), ["data/full-map/destinations.json"], [], 0),
    ("full-map-bike", "build", venv("access-time.py", "--dests", "data/full-map/destinations.json", "--rule", "protected",
                                    "--nets", "today", "--k", "1", "--workers", "3", "--out", "out/full-map/bike"),
     ["out/full-map/bike/*"], [], 0),
    ("full-map-bike-furth1", "build", venv("access-time.py", "--dests", "data/full-map/destinations.json", "--rule",
                                           "furth1", "--nets", "today", "--k", "1", "--workers", "3",
                                           "--out", "out/full-map/bike-furth1"),
     ["out/full-map/bike-furth1/*"], [], 0),
    ("full-map-lts", "build", venv("full-map-lts.py"), ["out/full-map/lts.json"], [], 0),
    ("full-map-transit-origins", "build", venv("full-map-transit.py", "--origins"),
     ["data/full-map/transit-origins.json"], [], 0),
    ("full-map", "build", venv("full-map.py"), ["out/full-map/blocks.json", "out/full-map/summary.json"], [], 0),
    # The Daily Trips map's slim copy for the site, with block outlines; its checks reproduce summary.json's counts.
    ("daily-trips-site", "build", py("daily-trips-site.py"), ["site/data/daily-trips.json"], [], 0),
    # SFMTA's Safe School Connections map read school by school, which school-sim
    # reads for its walk to today's network.
    ("ssc-school-map-compare", "build", venv("ssc-school-map-compare.py"), ["out/ssc-school-map/*"], [], 0),
    ("repave-lever", "build", py("repave-lever.py"), ["out/repave-lever/*", "site/data/repave-lever.json"], [], 0),
    ("coordination-projects", "build", py("coordination-projects.py"),
     ["site/data/coordination.json", "out/coordination/*", "data/project-ids.json",
      "data/coordination/held-listing.json"], [], 0),
    # The one-school case studies, every school in data/school-case/dropoff.json,
    # whose ranked blocks school-sim reads; after coordination-projects, whose
    # site/data/coordination.json gives their street work tables.
    ("school-case", "build", venv("school-case.py"), ["site/data/school-case/*"], [], 0),
    # One modelled city of SFUSD and charter students: every block's expected
    # students per school and mode, today and under each change (reads
    # school-gravity's fit, school-case's ranked blocks, both OSM networks).
    # Trip times are cached per school by their inputs, so a rerun on the same
    # inputs recomputes none; its quality checks, the car-route one among them,
    # run after every build and stop the step.
    # Each school's grounds, so every distance to a school runs from the edge of the grounds as state law
    # measures a school zone, and the 500 ft zones the School Trips maps draw.
    ("school-grounds", "build", venv("school-grounds.py"), ["data/school-sim/grounds.json", "site/data/school-zones.json"], [], 0),
    # Crashes near each school at its bell hours, measured from the grounds.
    ("school-hour-crashes", "build", venv("school-hour-crashes.py"), ["out/school-hour-crashes/*"], [], 0),
    # Where the 20 mph business districts, speed humps and speed cameras go near each school.
    ("school-speed-levers", "build", venv("school-speed-levers.py"), ["data/school-sim/speed-levers.json"], [], 0),
    # The order School Trips' calming budget takes schools in: kids hurt near each over ten years.
    ("school-calm-priority", "build", venv("school-calm-priority.py"), ["data/school-sim/calm-priority.json"], [], 0),
    # Each street block's grade from USGS DEM tiles, and the blocks Muni runs on: school-sim and school-segments read
    # both (steep blocks leave the bikeway candidates, Muni streets are kept apart). Each script's checks stop its step.
    ("street-grades", "build", venv("street-grades.py"), ["data/street-grades/*"], [], 0),
    ("muni-streets", "build", venv("muni-streets.py"), ["data/muni-streets/*"], [], 0),
    # The new bikeway stretches the City view's budget buttons switch on: the integer program in
    # tools/school-trips/school-segments-ip.py, run through school-sim.py so it reads the sim's cells and trip times. Its route
    # menu is cached by its inputs, so a rerun on the same network and candidates only re-solves.
    ("school-segments", "build", venv("school-sim.py", "--segments", "--workers", "3"), ["out/school-sim/segments.json"], [], 0),
    # Kids hurt on SF weekdays by street type and distance from the grounds, and the model's injury shares; its
    # bikeways block reads the stretches school-segments chose.
    ("school-kids-hurt", "build", venv("school-kids-hurt.py"), ["site/data/school-kids-hurt.json", "site/data/school-crossings.json"], [], 0),
    # The street changes and the chosen stretches as map lines (reads segments.json).
    ("school-overlays", "build", venv("school-sim.py", "--overlays"), ["site/data/school-sim/overlays.json"], [], 0),
    ("school-sim", "build", venv("school-sim.py", "--workers", "3"), ["out/school-sim/*", "site/data/school-sim/*"], [], 0),
    # School Trips' rules the simulation doesn't write: each School Connector priced
    # block by block by street type, and the TK-8 students free Muni reaches.
    # Its checks stop the step and keep the last good rules.json.
    ("school-sim-rules", "build", venv("school-sim-rules.py"), ["site/data/school-sim/rules.json"], [], 0),
    # Which changes go to which schools, and which new bikeway set, for $5M to $80M over 4 years, from the per-school
    # simulation files and the kids hurt per school (the School Trips scenarios Best for Car Mode Shift, Best for
    # Safety and Balanced). After school-sim and school-sim-rules, whose files it reads.
    ("school-budget-plans", "build", ["node", where("school-budget-plans.mjs")], ["site/data/school-budget-plans.json"], [], 0),
    # The heat map layer's points: kids hurt near schools at school hours over 20 school years. After school-sim,
    # which rewrites site/data/school-sim/.
    ("school-injury-points", "build", venv("school-injury-points.py"), ["site/data/school-sim/injuries.json"], [], 0),
    # The Mobility section's injury page: where people are hurt, the fixes before and after, and each school's
    # quarter-mile count. After school-sim (index.json) and project-record (projects.json), which it reads.
    ("injury-map", "build", venv("injury-map.py"), ["site/data/injury-map.json"], [], 0),
    # The injury page's "why more people are severely hurt" section: ten hypotheses against the crash reports.
    # After injury-map, whose street snapping it reuses.
    ("injury-severe-why", "build", venv("injury-severe-why.py"), ["site/data/injury-severe-why.json"], [], 0),
    # Through traffic per street block for the Street Safety map: MTC 2023 car trips routed on SF-CHAMP's network
    # (tools/street-safety/through-traffic.py). The routing runs on the sim VM (scripts/through-traffic-vm.sh) and writes the
    # tracked links.json; this step joins it to the blocks. Before street-safety-map, which reads blocks.json.
    ("through-traffic", "build", venv("through-traffic.py", "blocks"), ["data/extract/through-traffic/blocks.json"], [], 0),
    # Where traffic comes from, for the Street Safety map's where-from view: the same VM run's select stage
    # (scratch/runs/through-traffic/select.json) to one file per neighborhood and Supervisor district, the bubbles' units and the cordon table.
    ("where-traffic-comes-from", "build", venv("where-traffic-comes-from.py"), ["site/data/street-safety/where-from/*"], [], 0),
    # How people travel between each area and each bubble's place, for the bubbles' cards: MTC's trip files and skims
    # for the same 2023 run (scratch/runs/through-traffic/mtc-2023, scratch/runs/mode-skims-prior-work). After
    # where-traffic-comes-from, whose units.json it reads.
    ("where-traffic-modes", "build", venv("where-traffic-modes.py"), ["site/data/street-safety/where-from/modes-*.json"], [], 0),
    # The Street Safety map's chain, daily with the scheduled run. Each build reruns only when a file it read moved:
    # the crash reads street-safety-crashes keeps, the Telraam counters (weekly), the SFPD reports and the crash cards.
    # The severe injuries and deaths of 2022 to 2024 placed on the streets (scratch/runs/hin-injuries/points.geojson,
    # tools/street-safety/hin-injury-kinds.py), which hin-cut-through and street-safety-map read. Needs numpy.
    ("hin-injuries", "build", venv("hin-injury-kinds.py"), ["scratch/runs/hin-injuries/points.geojson"], [], 0),
    # The 2024 and 2022 HIN segments ranked worst to best (tools/street-safety/hin-densest-stretches.py), for the map's HIN groups.
    # After project-record, whose blocks it reads.
    ("hin-densest", "build", py("hin-densest-stretches.py"), ["out/hin-densest/*"], [], 0),
    # Every injured person since 2005 without a card (tools/street-safety/street-safety-light.py): the map's dots. Needs numpy.
    ("street-safety-light", "build", venv("street-safety-light.py"), ["data/extract/street-safety/light-injuries.json"], [], 0),
    # Cars per minute at rush hour on every block (tools/street-safety/hin-cut-through.py), the map's traffic stress layer, with the
    # Telraam read date the map's test checks against segments.json. After telraam and hin-injuries.
    ("hin-cut-through", "build", py("hin-cut-through.py"), ["data/extract/residential-traffic/blocks.json",
                                                           "out/hin-cut-through/*"], [], 0),
    # The Street Safety map's data (site/data/street-safety/), from the HIN people map's build
    # (tools/street-safety/hin-people-map.py) and the four steps above. Last of the chain; its read date is the newest of the
    # people's, the crime reports' and the Telraam counters' own read dates.
    ("street-safety-map", "build", py("street-safety-map.py"), ["site/data/street-safety/*"], [], 0),
    # The board's school embeds: the four school maps, the top 40 and the $20M bikeway map. After school-sim
    # (index.json) and school-segments (segments.json), which it reads.
    ("school-hurt-maps", "build", venv("school-hurt-maps.py"), ["site/data/school-hurt-maps.json"], [], 0),
    # School Trips' Your Trip: the simulation's network and each school's
    # changes, shrunk for routing in the browser (reads site/data/school-sim/).
    ("school-trip-graph", "build", venv("school-trip-graph.py"), ["site/data/school-trip-graph.json"], [], 0),
    # The browser router against the simulation on 400 sampled block-school
    # trips; exits 1 when walk or car minutes drift apart or the car goes untimed.
    ("school-trip-check", "build", ["node", where("school-trip-check.mjs")], [], [], 0),
    # Each case study school's per-block inputs (gravity shares, walk, drive and
    # bike times, feet off safe streets) as one reusable file for the next stage.
    ("school-block-inputs", "build", venv("school-block-inputs.py"), ["data/school-case/blocks/*"], [], 0),
    # The audit's C1 reads the body rows from this file.
    ("record-coverage", "build", py("record-coverage.py", "--json", "out/record-coverage/coverage.json"),
     ["out/record-coverage/*"], [], 0),
    ("department-overlap", "build", py("department-overlap.py"), ["site/data/department-overlap.json"], [], 0),
    # The Muni dashboard's data (site/data/muni.json, muni-heat.json, muni-map.json, muni-lines.json), the files the
    # pages at sf-works.org/transportation/muni read. muni.json carries "read", the date its newest data was read,
    # which the pages print as "Data updated".
    # They read data/muni-ewt/, whose 511 figures the muni-511 step above refreshes
    # on the VM's scheduled run (vm_sync.sh pull does the same by hand from a
    # laptop), the three SFMTA sources above, and the GTFS zip the muni-gtfs step keeps.
    # Interval: daily (the default), though 511 posts its stop observations a
    # month at a time, so a new month lands within a day of posting.
    ("muni-site-data", "build", venv("muni-ewt/site_data.py"), ["site/data/muni.json", "site/data/muni-heat.json"], [], 0),
    ("muni-map", "build", venv("muni-ewt/muni_map.py"), ["site/data/muni-map.json"], [], 0),
    # Speed along each line, from the stop-to-stop times post_all.sh keeps on the VM (~/muni-511/ewt/pairs, rebuilt
    # only for months that moved); muni-detail below carries it into muni-lines.json. Off the VM it says so and
    # keeps the last good data/muni-ewt/speed_along_line.json.
    ("muni-speed-along", "build", venv("muni-ewt/speed_along_line.py"), ["data/muni-ewt/speed_along_line.json"], [], 0),
    ("muni-detail", "build", venv("muni-ewt/muni_detail.py"), ["site/data/muni-lines.json"], [], 0),
    # Upgrade a Bus Line's results (site/data/muni-optimizer/<month>.json, the page at /transportation/muni/optimizer):
    # each line's wait, speed and crowding today and every combination of fixes, from the three dashboard files above,
    # the 511 summaries, SFMTA's crowding file, the timetable zip the muni-gtfs step keeps (unpacked by the script)
    # and the lever model's tracked outputs under data/muni-ewt/lever/. Nothing is fetched; it reruns when an input
    # moves, runs its own checks before it writes (a failure exits 1 and keeps the previous file) and the
    # muni-optimizer checks after. When the dashboard has moved to a month whose timetable (muni-timetable-history)
    # or delivered share (muni-delivered-by-mode) isn't in yet, it keeps the last month's file and passes; the
    # newest-month check and pipeline/refresh-freshness.py fail once that month ended over 40 days back.
    # Interval: daily, with the scheduled run.
    ("muni-optimizer", "build", venv("muni-ewt/optimizer_build.py"), ["site/data/muni-optimizer/*.json"], [], 0),
    # One daily series from both sources (site/data/muni-daily.json): 511's records for the months it has posted,
    # the archive's rebuilt days after them, each day marked with its source, and the date the data was read.
    ("muni-daily", "build", py("muni-ewt/muni_daily.py"), ["site/data/muni-daily.json"], [], 0),
    ("muni-stop-reach", "build", py("muni-stop-reach.py"), ["site/data/bike-history/muni-reach.json"], [], 0),
    ("parking-reach", "build", py("parking-reach.py"), ["site/data/bike-history/parking-reach.json"], [], 0),
    # The site's own collectors are node and fast; they run every time and
    # write only when their output changes.
    ("collect-transportation", "node", node("collect-transportation.mjs"), ["site/data/transportation.json"], [], 0),
]

# How often each step must run (pipeline/README.md, update intervals). The
# scheduled run on the GCP VM (pipeline/site-refresh/run.sh, daily at 13:15 UTC) runs every step not in MANUAL, and
# pipeline/refresh-freshness.py fails when a step's last good check is older than its interval allows. Every step
# not named in INTERVAL_DAYS runs daily; a build step that finds its inputs unchanged counts as checked.
DEFAULT_INTERVAL_DAYS = 1
INTERVAL_DAYS = {
    # Legistar's search has no change marker; STEPS runs it at most once a day, so daily is its floor.
    "bos-street-records": 1,
    # Telraam's counters upload hourly, but a 12-month median moves little in a week (Bryan, 2026-11-09: "weekly is a
    # good first stab").
    "telraam": 7,
}
# Steps the scheduled run leaves out, and why. School Trips is a model, not a feed: its runs are decided by hand and
# run on the simulation VM (memory note one-heavy-job-at-a-time), and a daily OSM edit would otherwise move its
# figures every morning without anyone reviewing them. Its sources still refresh daily; only the model builds wait.
MANUAL = {name: "School Trips model build; rerun by hand on the simulation VM" for name in [
    "school-travel-time", "school-travel-check", "access-time-check", "ssc-school-map-compare", "school-case",
    "school-grounds", "school-hour-crashes", "school-speed-levers", "school-kids-hurt", "school-calm-priority",
    "school-segments", "school-overlays", "school-sim", "school-sim-rules", "school-budget-plans",
    "school-injury-points", "school-trip-graph", "school-trip-check", "school-block-inputs"]}
# Through traffic's trip table is MTC's 2023 model run and its network one fixed SF-CHAMP run; neither updates, so
# there is nothing to fetch on a schedule. A new MTC run means rerunning scripts/through-traffic-vm.sh by hand.
MANUAL["through-traffic"] = ("its trip table (MTC Travel Model 1.6, 2023) and network (one undated SF-CHAMP run) don't "
                             "update; rerun scripts/through-traffic-vm.sh when MTC publishes a new run")
MANUAL["where-traffic-comes-from"] = ("reads the select stage's output from scripts/through-traffic-vm.sh, which runs by hand on the VM "
                                      "for the same fixed trip table and network as through-traffic")
MANUAL["where-traffic-modes"] = ("its trip files and skims are MTC's fixed 2023 run; rerun tools/street-safety/where-traffic-modes.py "
                                 "by hand when MTC publishes a new run")
# The full map's Muni minutes (out/full-map/transit.json) come from a sim-VM run (scripts/full-map-transit-vm.sh) on
# these origins, and full-map refuses minutes built on other origins. A daily OSM walk edit would rebuild the origins
# and stop full-map and every step after it until someone reran the sim, so the origins move only with that rerun.
MANUAL["full-map-transit-origins"] = "rebuilt by hand with the Muni minutes' sim-VM run (scripts/full-map-transit-vm.sh)"
# The destinations' points are the Muni minutes' other input, keyed by full_map_dests.points_sha, and they move with
# OSM too: a park or district edge sample is kept only within EDGE_M of a walk-network street, so a daily walk edit
# adds or drops a few points. Each rebuild from 2026-11-11 to 11-19 moved them (by 11-19 commercial 8,161 to 8,180
# and the GGNRA 286 to 285, with the zoning and CPAD polygons unchanged) and full-map refused transit.json on every
# one. A zoning or parks change moves them as well and needs the same rerun, so they move with it.
MANUAL["full-map-destinations"] = "rebuilt by hand with the Muni minutes' sim-VM run (scripts/full-map-transit-vm.sh)"


# Builds that read another step's output, and the steps they read. When one of those fails (or is itself held back),
# the build is skipped for that run and keeps its last good files. Unlike a source failing its checks, which stops
# every build, this holds back only the chain: the Street Safety map never pairs one input's new data with another's
# failed rebuild (a blocks.json from an older Telraam read beside today's segments.json, say).
AFTER = {
    "hin-injuries": ("street-safety-crashes",),
    "hin-densest": ("street-safety-crashes", "project-record"),
    "street-safety-light": ("street-safety-crashes",),
    "hin-cut-through": ("telraam", "hin-injuries"),
    "street-safety-map": ("street-safety-crashes", "street-safety-cards", "sfpd-crime", "telraam", "hin-injuries",
                          "hin-densest", "street-safety-light", "hin-cut-through"),
    "injury-map": ("street-safety-crashes",),
    "injury-severe-why": ("street-safety-crashes", "injury-map"),
}

_named = (set(MANUAL) | set(INTERVAL_DAYS) | set(AFTER) | {u for v in AFTER.values() for u in v}) - {s[0] for s in STEPS}
assert not _named, "MANUAL, INTERVAL_DAYS or AFTER names a step not in STEPS: %s" % ", ".join(sorted(_named))


def interval_days(name):
    """Days between runs this step must keep to, or None for a MANUAL step."""
    return None if name in MANUAL else INTERVAL_DAYS.get(name, DEFAULT_INTERVAL_DAYS)


def source_interval_days(key, entry):
    """Days between good checks a "<kind>:<source>" record in sources.json must keep to: the interval of the step
    that records it. The step is the one main() named on the entry (pipeline_state.set_step), or for an
    "extract:<src>" record the step that lists the extract in STEPS. A record with no known step, or a MANUAL
    step's, keeps the daily default."""
    step = (entry or {}).get("step")
    if not step and key.startswith("extract:"):
        step = next((s[0] for s in STEPS if key[len("extract:"):] in s[4]), None)
    days = interval_days(step) if step in {s[0] for s in STEPS} else None
    return days or DEFAULT_INTERVAL_DAYS


# source step keeps. An extract is recorded as checked only when its own
# marker check succeeded this run; an extract with no entry here has no
# marker of its own, and its step's exit code is the check.
EXTRACT_MARKERS = {
    "sfmta-bikeway": ["arcgis:sfmta-bikeway"],
    "sfmta-bci": ["arcgis:sfmta-bci"],
    "slow-streets": ["socrata:hkz3-itiu"],
    "census-blocks": ["socrata:p2fw-hsrv"],
    "libraries": ["socrata:nc68-ngbr"],
    "cpad": ["arcgis:cpad-sf"],
    "census-acs": ["census:acs1-b08301"],
    # Document sources. sfmta.com's sitemap carries a lastmod; the other four
    # publish no marker, so each script re-reads a bound named in its
    # docstring and records the check failed when anything in it was not
    # reached (pipeline_state.refreshed).
    "sfmta-pages": ["sitemap:sfmta-pages"],
    "sfmta-hearings": ["listing:sfmta-hearings"],
    "sfmta-board": ["listing:sfmta-board"],
    "sfpuc-commission": ["listing:sfpuc-commission"],
    "dpw-projects": ["pages:dpw-projects"],
}


def refresh_failures(since, before=None):
    """Every source marker a step recorded as failed at or after `since` (ISO
    seconds). With `before`, the state as the step started, an entry left as it
    was is not this step's: an earlier step's failure in the same second would
    otherwise be named again."""
    before = before or {}
    return sorted(k for k, v in pipeline_state.load().items()
                  if v.get("status") == "failed" and (v.get("checked") or "") >= since
                  and before.get(k) != v
                  and not k.startswith(("quality:", "step:", "extract:")))


def output_hashes(trace, guard):
    """The files a build step wrote, as they are now: those the trace saw it
    write, plus its guarded outputs it read and left alone (stable.write_text
    leaves a file with nothing new unwritten, and reads it to know)."""
    reads = set(trace.get("r", []))
    outs = {f for f in trace.get("w", []) if not f.endswith(".tmp") and os.path.isfile(os.path.join(ROOT, f))}
    outs |= {os.path.relpath(f, ROOT) for f in expand(guard)} & reads
    return {f: file_hash(f) for f in sorted(outs)}


# The North Star plan layers are traced once from the plan's map
# (tools/bike-network/north-star-map-trace.py, tools/bike-network/north-star-index.py) and copied
# into the site, with the plan's class definitions (tools/bike-network/plan-class-definitions.py).
# The copy was done by hand; it is a step now.
NORTH_STAR_COPY = [
    ("out/north-star/map-trace/traced.geojson", "site/data/north-star/traced.geojson"),
    ("out/north-star/map-trace/georeference.json", "site/data/north-star/georeference.json"),
    ("out/north-star/segments.geojson", "site/data/north-star/segments.geojson"),
    ("out/north-star/class-definitions.json", "site/data/class-definitions.json"),
]


def load_state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    stable.write_json(STATE, state, indent=1, sort_keys=True)


def file_hash(rel):
    h = hashlib.sha256()
    try:
        with open(os.path.join(ROOT, rel), "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except (FileNotFoundError, IsADirectoryError):
        return "missing"
    return h.hexdigest()


def inputs_hash(trace, cmd=None):
    """One hash over everything a step read last time: files, listings, modules,
    and the step's own script, which runs as __main__ and so is never traced as
    an import: an edit to the script alone must rebuild its step. A step run
    through pipeline/venv-step.py names its script as an argument, so every
    .py or .mjs argument counts as the step's own."""
    h = hashlib.sha256()
    own = [a for a in (cmd or [])[1:] if a.endswith((".py", ".mjs"))]
    for rel in own + trace.get("r", []) + trace.get("m", []):
        h.update(("f %s %s\n" % (rel, file_hash(rel))).encode())
    for rel in trace.get("d", []):
        try:
            names = sorted(os.listdir(os.path.join(ROOT, rel)))
        except (FileNotFoundError, NotADirectoryError):
            names = ["<missing>"]
        h.update(("d %s %s\n" % (rel, "\0".join(names))).encode())
    return h.hexdigest()


def expand(patterns):
    out = set()
    for p in patterns:
        out.update(f for f in glob.glob(os.path.join(ROOT, p), recursive=True) if os.path.isfile(f))
    return sorted(out)


def snapshot(patterns):
    snap = {}
    for f in expand(patterns):
        with open(f, "rb") as fh:
            snap[f] = fh.read()
    return snap


def settle(patterns, snap):
    """Restore stamp-only rewrites; return the files that really changed."""
    changed = []
    for f in sorted(set(snap) | set(expand(patterns))):
        r = stable.keep_if_same(f, snap.get(f))
        if r in ("changed", "new"):
            changed.append(os.path.relpath(f, ROOT))
    return changed


def run(cmd, trace_log=None, net_log=None):
    env = dict(os.environ, PYTHONHASHSEED="0")
    if trace_log or net_log:
        env["PYTHONPATH"] = TRACE_DIR + os.pathsep + env.get("PYTHONPATH", "")
        env["TRACE_ROOT"] = ROOT
    if trace_log:
        env["TRACE_LOG"] = trace_log
    if net_log:
        env["NET_LOG"] = net_log
    p = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def last_trace(path):
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except FileNotFoundError:
        return {}
    merged = {"r": set(), "w": set(), "d": set(), "m": set()}
    for line in lines:
        rec = json.loads(line)
        for k in merged:
            merged[k].update(rec.get(k, []))
    merged["r"] -= merged["w"]
    return {k: sorted(v) for k, v in merged.items()}


def net_summary(path):
    """One line for what a source step fetched: requests and body bytes, by host.

    The full list, one request per line, stays in `path` for inspection."""
    try:
        recs = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    except FileNotFoundError:
        recs = []
    if not recs:
        return "fetched nothing"
    hosts = {}
    for r in recs:
        h = re.sub(r"^https?://([^/]+).*$", r"\1", r["u"])
        n, b = hosts.get(h, (0, 0))
        hosts[h] = (n + 1, b + r["b"])
    return "%d requests, %s: %s" % (len(recs), kb(sum(r["b"] for r in recs)),
                                     ", ".join("%s %d (%s)" % (h, n, kb(b)) for h, (n, b) in sorted(hosts.items())))


def kb(n):
    return "%.0f KB" % (n / 1024) if n < 10 << 20 else "%.1f MB" % (n / (1 << 20))


def copy_north_star():
    changed = []
    for src, dst in NORTH_STAR_COPY:
        a, b = os.path.join(ROOT, src), os.path.join(ROOT, dst)
        if file_hash(src) != file_hash(dst):
            shutil.copyfile(a, b)
            changed.append(dst)
    return changed


def guarded(name, cmd, spec, root=None, snap_root=None, runner=None):
    """Run one step inside a snapshot of everything it may write, then its quality checks.

    Returns (code, out, results, touched, restored): the step's exit code and
    output, every check's Result, the files the step changed, and whether they
    were put back. They are put back when the step exits non-zero or any check
    fails, and the source markers in sources.json go back with them, so the
    next run sees the change again rather than a marker that says it was read.
    """
    runner, root, snap_root = runner or run, root or ROOT, snap_root or SNAPSHOTS
    state_rel = os.path.relpath(pipeline_state.PATH, root)
    snap = Snapshot(root, list(spec.paths) + [state_rel], os.path.join(snap_root, re.sub(r"[^\w.-]", "_", name)))
    snap.take()
    try:
        code, out = runner(cmd)
        results = quality.run(spec.checks(root), root, snap.dir) if code == 0 else []
        touched = [f for f in snap.changed() if f != state_rel]
        restored = bool(code or any(not r.ok for r in results))
        if restored:
            snap.restore()
    finally:
        snap.discard()
    return code, out, results, touched, restored


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="rebuild every build step")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", help="comma-separated step names")
    ap.add_argument("--skip-sources", action="store_true", help="run build steps only")
    ap.add_argument("--scheduled", action="store_true",
                    help="the scheduled run: every step but MANUAL's (pipeline/site-refresh/run.sh passes it)")
    args = ap.parse_args()
    only = set(args.only.split(",")) if args.only else None
    unknown = (only or set()) - {s[0] for s in STEPS}
    if unknown:
        sys.exit("unknown step(s): %s" % ", ".join(sorted(unknown)))
    if args.scheduled:
        only = (only or {s[0] for s in STEPS}) - set(MANUAL)
    # A fetch without checks is not an updater (pipeline/README.md, rule 2).
    # An extract with no marker check would be stamped checked whatever its
    # refresh did, and F3 could never expire it.
    unmarked = sorted({x for s in STEPS for x in s[4]} - set(EXTRACT_MARKERS))
    if unmarked:
        sys.exit("extract(s) with no change marker or bounded re-read in EXTRACT_MARKERS: %s" % ", ".join(unmarked))
    unchecked = [s[0] for s in STEPS if s[1] == "source" and s[0] not in QUALITY.SPECS]
    if unchecked:
        sys.exit("source step(s) with no quality checks in pipeline/transportation-quality.py: %s"
                 % ", ".join(unchecked))

    state = load_state()
    today = dt.date.today()
    all_changed, failed = [], []
    refresh_failed = {}  # source step -> markers whose refresh failed; last good copy kept
    blocked = None      # (step, check) of the first source that failed its checks
    held_back = set()   # steps skipped this run because a step in AFTER failed or was itself held back
    past_sources = False
    t_all = time.time()
    for name, kind, cmd, guard, extracts, min_days in STEPS:
        past_sources = past_sources or kind != "source"
        if only and name not in only:
            continue
        if args.skip_sources and kind == "source":
            continue
        if blocked and past_sources:
            # Downstream of a source whose new data failed its checks: that
            # data was put back, and nothing is built until the source passes.
            print(f"  {name:26} skipped: {blocked[0]} failed {blocked[1]}")
            pipeline_state.record("step:" + name, "skipped", detail="upstream %s failed %s" % blocked)
            continue
        waits = [u for u in AFTER.get(name, ()) if u in failed or u in held_back]
        if waits:
            # Its inputs come from a step that failed this run: build nothing on a half-refreshed chain.
            held_back.add(name)
            print(f"  {name:26} skipped: {', '.join(waits)} failed or was held back this run")
            pipeline_state.record("step:" + name, "skipped", detail="upstream %s failed or was held back" % ", ".join(waits))
            continue
        st = state.get(name, {})
        # The throttle counts only a run whose refresh succeeded ("good"). A run that kept its last copy because the
        # publisher did not answer, or the host had no key, is tried again on the next run.
        if kind == "source" and min_days and not args.all and st.get("good"):
            age = (today - dt.date.fromisoformat(st["good"][:10])).days
            if age < min_days:
                print(f"  {name:26} skipped: ran {st['good'][:10]}, runs at most every {min_days} day(s)")
                continue
        trace = st.get("trace")
        if kind == "build" and not args.all and trace and all(os.path.exists(f) for f in expand(guard)):
            outs = st.get("outputs")
            moved = [f for f, h in (outs or {}).items() if file_hash(f) != h]
            if inputs_hash(trace, cmd) == st.get("inputs") and outs is not None and not moved:
                print(f"  {name:26} skipped: {len(trace['r'])} inputs and {len(outs)} outputs unchanged")
                continue
            if moved:
                print(f"  {name:26} reruns: {len(moved)} output(s) differ from what it last wrote: {', '.join(moved[:3])}")
        if args.dry_run:
            print(f"  {name:26} would run: {' '.join(cmd) if cmd else 'copy'}"
                  + ("  [+ %s checks]" % name if name in QUALITY.SPECS else ""))
            continue

        spec = QUALITY.SPECS.get(name)
        snap = snapshot(guard)
        t0 = time.time()
        started = dt.datetime.now().isoformat(timespec="seconds")
        state_before = pipeline_state.load()
        results, touched, restored = [], [], False
        if kind == "copy":
            code, out = 0, ""
            copy_north_star()
        else:
            log = net = None
            if kind == "source":
                # Every request the step makes, for the per-source fetch log.
                net = os.path.join(os.path.dirname(STATE), "net-%s.jsonl" % re.sub(r"[^\w.-]", "_", name))
                if os.path.exists(net):
                    os.remove(net)
            if kind == "build":
                log = os.path.join(os.path.dirname(STATE), "trace-%s.jsonl" % name)
                if os.path.exists(log):
                    os.remove(log)
            if spec:
                code, out, results, touched, restored = guarded(name, cmd, spec,
                                                                runner=lambda c, log=log, net=net: run(c, log, net))
            else:
                code, out = run(cmd, log, net)
        changed = settle(guard, snap)
        secs = time.time() - t0
        bad = [r for r in results if not r.ok]
        if spec:
            pipeline_state.record("quality:" + name, "failed" if (bad or code) else "passed",
                                  detail=("; ".join(repr(r) for r in bad[:10]) if bad else
                                          "step exited %d; checks not run" % code if code else
                                          "%d checks passed" % len(results)))
        if code != 0 or bad:
            failed.append(name)
            # A build step with checks stops the run the same way: its
            # previous files are back, and no later step reads the new ones.
            # A MANUAL step is the exception: the scheduled run never runs it, so a later step already builds on
            # its last good files every day, and a hand run that includes it (any run without --scheduled) must
            # not stop every later build because a held step failed. It still fails the run and is named.
            if spec and not blocked and name not in MANUAL:
                blocked = (name, bad[0].check if bad else "exit %d" % code)
            what = (f"{len(bad)} of {len(results)} quality checks failed:\n" +
                    "\n".join("      %r" % r for r in bad[:12])) if bad else (
                f"exit {code}:\n" + "\n".join("      " + l for l in out.splitlines()[-15:]))
            print(f"  {name:26} FAILED ({secs:.0f}s), {what}" +
                  (f"\n      restored {len(touched)} files to their state before the step" if restored else ""))
            pipeline_state.record("step:" + name, "failed",
                                  detail=("; ".join(r.check for r in bad[:10]) if bad else out[-500:]))
            # Forget its last build, so the next run reruns it rather than finding its inputs unchanged.
            if state.pop(name, None) is not None:
                save_state(state)
            continue
        # A source whose publisher did not answer: the script kept its last
        # good copy and exited 0, and recorded its own marker as failed. A
        # build step run through pipeline/venv-step.py without its virtualenv
        # does the same; it is not recorded as built, so it runs next time.
        failed_markers = refresh_failures(started, state_before) if kind in ("source", "build") else []
        if failed_markers:
            refresh_failed[name] = failed_markers
        if kind == "build" and failed_markers and state.pop(name, None) is not None:
            save_state(state)
        if not (kind == "build" and failed_markers):
            entry = {"ran": dt.datetime.now().isoformat(timespec="seconds")}
            if kind == "build":
                tr = last_trace(log)
                entry["trace"] = tr
                entry["inputs"] = inputs_hash(tr, cmd)
                entry["outputs"] = output_hashes(tr, guard)
            state[name] = entry
            save_state(state)
        moved = changed or touched
        # Each extract a source step keeps current, as checked today: F3 reads
        # this rather than the extract's read date, which by design stays put
        # while the data does. Only when the extract's own marker was checked
        # this run: a marker that failed, or was never recorded, leaves the
        # extract aging from its last good check.
        state_now = pipeline_state.load()
        for src in extracts:
            keys = EXTRACT_MARKERS.get(src, [])
            bad = [k for k in keys if k in failed_markers or (state_now.get(k, {}).get("checked") or "") < started]
            if bad:
                pipeline_state.record("extract:" + src, "failed",
                                      detail="marker check %s did not succeed in step %s; last good copy kept" % (", ".join(bad), name))
                refresh_failed.setdefault(name, [])
                refresh_failed[name] = sorted(set(refresh_failed[name]) | {"extract:" + src})
                continue
            pipeline_state.record("extract:" + src, "changed" if moved else "unchanged",
                                  detail="checked by pipeline/transportation-update.py step " + name)
        # A source step's run is good, and counts toward its "at most every N days", only when no marker or extract
        # of its refresh failed.
        if kind == "source" and name not in refresh_failed:
            state[name]["good"] = state[name]["ran"]
            save_state(state)
        # Every marker and extract this step recorded carries the step's name, so the freshness check ages it on the
        # step's own interval.
        pipeline_state.set_step([k for k, v in pipeline_state.load().items() if state_before.get(k) != v
                                 and not k.startswith(("step:", "quality:", "run:"))], name)
        # A build that could not run (its virtualenv missing) kept its last outputs: failed, so freshness ages it.
        pipeline_state.record("step:" + name, "failed" if kind == "build" and failed_markers else
                              "changed" if moved else "unchanged",
                              detail=", ".join((changed or touched)[:20]) or None)
        all_changed += changed
        print(f"  {name:26} {secs:5.0f}s  " + (f"changed {len(changed)}: {', '.join(changed[:4])}"
                                                + (" …" if len(changed) > 4 else "") if changed else "no change")
              + (f"; {len(results)} checks passed" if spec else ""))
        if kind == "source":
            print(f"  {'':26} net: {net_summary(net)}")
        elif kind == "node":
            # The collectors say per dataset whether they re-read it.
            for line in out.splitlines():
                if re.match(r"\s+[a-z0-9]{4}-[a-z0-9]{4}: ", line):
                    print(f"  {'':26} {line.strip()}")

    print(f"\n{len(all_changed)} files changed in {time.time() - t_all:.0f}s"
          + (f"; FAILED: {', '.join(failed)}" if failed else ""))
    if refresh_failed:
        print("\nREFRESH FAILED, last good copy kept:")
        for step, keys in sorted(refresh_failed.items()):
            print(f"  {step:26} {', '.join(keys)}")
    rebound = [(f, BOUND[f]) for f in all_changed if f in BOUND]
    if rebound:
        print("\nBoard docs to re-read (BOARD_DOCS):")
        for f, d in rebound:
            print(f"  {d}  {f}")
    if blocked:
        print(f"\nSTOPPED: {blocked[0]} failed quality check {blocked[1]}. Its previous data is back in "
              f"place and no build step ran on the new data.")
    sys.exit(1 if failed else 2 if refresh_failed else 0)


if __name__ == "__main__":
    main()
