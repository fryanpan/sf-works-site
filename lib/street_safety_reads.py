"""The crash reads behind the Street Safety map and the injury pages: one list of DataSF queries, held in their own cache folder, checked before any copy is held, so one step keeps exactly them current.

Four tables:

  nwes-mmgh  police crash reports, one row per injured person (victims)
  8gtc-pjc6  the parties to each crash
  ubvf-ztfx  one row per crash
  dau3-4s8f  the Vision Zero fatality log

QUERIES names every query the pages' scripts send (tools/street-safety/hin-injury-kinds.py, street-safety-light.py,
hin-densest-stretches.py, hin-people-map.py, hin_crash_cards.py, injury-map.py and injury-severe-why.py). Each lands
in data/socrata-cache/street-safety/ (gitignored). tools/street-safety/street-safety-crashes.py --update reads every one of them:
a missing copy (a new machine, a new query) is read cold, and a held one is re-read when DataSF's rowsUpdatedAt for
its table moves. Either way the rows pass check_query() and the joins before they replace anything, and a held file
no query names any more is deleted. A script reads its rows with read(name); a copy that is not held yet is read
through the same checks first, so a hand run is checked too.

Every query also selects its table's key, unique_id and data_updated_at (with_keys()), whatever fields the script
asked for. DataSF corrects a row by appending a new one under the same key with a newer data_updated_at, so
resolve() keeps the newest row of each key and names the older ones as warnings. Two rows under one key with the same
data_updated_at and different contents can't be told apart and fail the check, except case 260408381's parties (see
TIES).

    from lib import street_safety_reads
    V = street_safety_reads.read("kinds-victims")   # an sfdata.Result: .rows, .tag, .fetched_on
"""

import datetime as dt
import json
import os
import re
import shutil
import time

import sfdata

CACHE = sfdata.CACHE_ROOT / "street-safety"
STAGE = sfdata.CACHE_ROOT / "street-safety.stage"
MANIFEST = CACHE / "_manifest.json"   # each held copy's rows hash; inside CACHE so the pipeline's snapshot covers it
DATASETS = ("nwes-mmgh", "8gtc-pjc6", "ubvf-ztfx", "dau3-4s8f")
KEYS = {"nwes-mmgh": ("case_id_pkey", "victim_id"), "8gtc-pjc6": ("case_id_pkey", "party_number_ckey"),
        "ubvf-ztfx": ("case_id_pkey",), "dau3-4s8f": ("unique_id",)}
STAMP = {"nwes-mmgh": "data_updated_at", "8gtc-pjc6": "data_updated_at", "ubvf-ztfx": "data_updated_at", "dau3-4s8f": None}
DATE = "collision_datetime"
FIRST_DAY = "2005-01-01"      # the crash tables' first year
MAX_DROP = 0.10
MAX_UNJOINED = 0.005
# Case 260408381's two parties each come twice with the same data_updated_at (2026-09-28), alike but for party 2's
# injured count (0 in unique_id 986274, 1 in 986567; DataSF 8gtc-pjc6, queried 2026-11-22). The pair is resolved to
# the higher unique_id, the row appended later. Any other such tie stops the read.
TIES = {("8gtc-pjc6", "260408381")}

_V22 = "collision_datetime between '2022-01-01T00:00:00' and '2024-12-31T23:59:59'"
_SEVERE = "victim_degree_of_injury in ('Fatal Injury','Severe Injury')"
_LIGHT_SELECT = ("case_id_pkey,victim_id,collision_datetime,collision_time,victim_degree_of_injury,victim_role,"
                 "party_number_ckey,tb_latitude,tb_longitude,vz_pcf_code,intersection")
CARD_FIELDS = {   # hin_crash_cards.py's three reads, the same fields street-safety-cards.py reads by year
    "crashes": ("case_id_pkey,collision_datetime,collision_time,primary_rd,secondary_rd,distance,direction,weather_1,"
                "type_of_collision,mviw,ped_action,road_surface,road_cond_1,road_cond_2,lighting,control_device,intersection,"
                "vz_pcf_code,vz_pcf_description,party_at_fault"),
    "parties": ("case_id_pkey,party_number_ckey,party_type,at_fault,party_age,party_sobriety,party_drug_physical,dir_of_travel,"
                "move_pre_acc,stwd_vehicle_type,street_of_travel,sp_info_1,sp_info_2,vehicle_autonomous"),
    "victims": "case_id_pkey,victim_id,party_number_ckey,victim_role,victim_age,victim_degree_of_injury",
}
CARDS_SINCE = "collision_datetime >= '2022-01-01T00:00:00'"
QUERIES = {
    # tools/street-safety/hin-injury-kinds.py: the severe injuries and deaths of 2022 to 2024 (every field), their parties (by date,
    # filtered to the people's cases there) and the fatality log for the same years.
    "kinds-victims": dict(fxf="nwes-mmgh", select=None, where=_SEVERE + " and " + _V22, floor=800),
    "kinds-parties": dict(fxf="8gtc-pjc6", where=_V22, floor=12000,
                          select="case_id_pkey,party_number_ckey,party_type,at_fault,street_of_travel,move_pre_acc,"
                                 "stwd_vehicle_type,party_sobriety,party_age"),
    "kinds-deaths": dict(fxf="dau3-4s8f", select="unique_id,case_id_fkey,collision_datetime,on_vz_hin_2022,latitude,longitude",
                         where=_V22, floor=80),
    # tools/street-safety/street-safety-light.py: every injured person since 2005 but the carded ones, their parties, the carded
    # rows, and a dates-and-levels read to count against.
    "light-victims": dict(fxf="nwes-mmgh", select=_LIGHT_SELECT, floor=75000,
                          where="victim_degree_of_injury in ('Fatal Injury','Severe Injury','Other Visible Injury','Complaint of Pain') and "
                                "collision_datetime >= '2005-01-01T00:00:00' and not (" + _SEVERE + " and " + _V22 + ")"),
    "light-parties": dict(fxf="8gtc-pjc6", where="collision_datetime >= '2005-01-01T00:00:00'", floor=100000,
                          select="case_id_pkey,party_number_ckey,party_type,stwd_vehicle_type,move_pre_acc,collision_datetime,"
                                 "party_number_injured,at_fault,party_age,party_sex"),
    "light-cards": dict(fxf="nwes-mmgh", select=_LIGHT_SELECT, where=_SEVERE + " and " + _V22, floor=900),
    "light-totals": dict(fxf="nwes-mmgh", select="collision_datetime,victim_degree_of_injury",
                         where=_SEVERE + " and collision_datetime >= '2005-01-01T00:00:00'", floor=5000),
    # tools/street-safety/hin-densest-stretches.py: severe injuries and deaths since 2015 and their parties (by date, filtered there).
    "densest-victims": dict(fxf="nwes-mmgh", floor=3000, where=_SEVERE + " and collision_datetime >= '2015-01-01T00:00:00'",
                            select="case_id_pkey,victim_id,collision_datetime,victim_degree_of_injury,tb_latitude,tb_longitude,"
                                   "primary_rd,supervisor_district,victim_role,party_number_ckey"),
    "densest-parties": dict(fxf="8gtc-pjc6", select="case_id_pkey,party_number_ckey,party_type,stwd_vehicle_type",
                            where="collision_datetime >= '2015-01-01T00:00:00'", floor=50000),
    # tools/street-safety/hin_crash_cards.py (through hin-people-map.py): crashes, parties and victims since 2022.
    "cards-crashes": dict(fxf="ubvf-ztfx", select=CARD_FIELDS["crashes"], where=CARDS_SINCE, floor=8000),
    "cards-parties": dict(fxf="8gtc-pjc6", select=CARD_FIELDS["parties"], where=CARDS_SINCE, floor=15000),
    "cards-victims": dict(fxf="nwes-mmgh", select=CARD_FIELDS["victims"], where=CARDS_SINCE, floor=10000),
    # tools/street-safety/hin-people-map.py: the fatality log since 2022.
    "people-map-deaths": dict(fxf="dau3-4s8f", select=None, where="collision_datetime >= '2022-01-01T00:00:00'", floor=100),
    # tools/street-safety/injury-map.py: every party, every victim, and two reads of the crashes since September 2021.
    "injury-map-parties": dict(fxf="8gtc-pjc6", select="case_id_pkey,party_number_ckey,party_type,at_fault,stwd_vehicle_type",
                               where=None, floor=100000),
    "injury-map-victims": dict(fxf="nwes-mmgh", where=None, floor=80000,
                               select="case_id_pkey,victim_id,victim_age,victim_degree_of_injury,victim_role,collision_datetime,"
                                      "collision_time,tb_latitude,tb_longitude,primary_rd,secondary_rd,intersection,distance,ped_action,"
                                      "street_of_travel,move_pre_acc,party_type,party_number_ckey,type_of_collision,vz_pcf_code"),
    "injury-map-crash-road": dict(fxf="ubvf-ztfx", select="case_id_pkey,lighting,road_surface,road_cond_1,road_cond_2,weather_1",
                                  where="collision_datetime >= '2021-09-01T00:00:00'", floor=10000),
    "injury-map-crash-causes": dict(fxf="ubvf-ztfx", where="collision_datetime >= '2021-09-01T00:00:00'", floor=10000,
                                    select="case_id_pkey,collision_datetime,vz_pcf_code,vz_pcf_group,vz_pcf_description,type_of_collision,"
                                           "dph_col_grp_description,intersection,distance,number_killed,number_injured"),
    # tools/street-safety/injury-severe-why.py: every victim and party, and the fatality log.
    "severe-why-victims": dict(fxf="nwes-mmgh", where=None, floor=80000,
                               select="case_id_pkey,victim_id,party_number_ckey,collision_datetime,collision_time,victim_degree_of_injury,"
                                      "victim_role,victim_age,stwd_vehicle_type,party_type,lighting,vz_pcf_code,tb_latitude,tb_longitude,"
                                      "intersection,primary_rd,secondary_rd"),
    "severe-why-parties": dict(fxf="8gtc-pjc6", where=None, floor=100000,
                               select="case_id_pkey,party_number_ckey,party_type,stwd_vehicle_type,party_sobriety,party_drug_physical,"
                                      "party_age,collision_datetime"),
    "severe-why-deaths": dict(fxf="dau3-4s8f", select="unique_id,case_id_fkey,collision_year,collision_datetime,deceased",
                              where=None, floor=300),
}


class Stop(Exception):
    """A read failed its checks; nothing was held."""


def with_keys(q):
    """The query's select with its table's key fields, unique_id and data_updated_at added (None stays every field)."""
    if q["select"] is None:
        return None
    have = q["select"].split(",")
    extra = [f for f in KEYS[q["fxf"]] + ("unique_id", STAMP[q["fxf"]]) if f and f not in have]
    return ",".join(have + extra)


def kwargs(name):
    q = QUERIES[name]
    return dict(select=with_keys(q), where=q["where"])


def path_of(name):
    q = QUERIES[name]
    params = {k: v for k, v in (("$select", with_keys(q)), ("$where", q["where"])) if v}
    params["$order"] = ":id"
    return CACHE / ("%s.json" % sfdata._key(q["fxf"], params))


def resolve(fxf, rows):
    """(rows with one per key, warnings, errors). Of a key's repeats, the newest data_updated_at is kept; an identical
    repeat is dropped; a repeat with the same stamp and other contents is an error, unless TIES lists its case."""
    keys = KEYS[fxf]
    if not rows or not all(k in rows[0] for k in keys):
        return rows, [], []
    stamp = STAMP[fxf]
    best, order, warn, err = {}, [], [], []
    for r in rows:
        k = tuple(r.get(f) for f in keys)
        if k not in best:
            best[k] = r
            order.append(k)
            continue
        had = best[k]
        if had == r:
            continue
        a, b = (had.get(stamp) or "", r.get(stamp) or "") if stamp else ("", "")
        if a != b:
            best[k] = r if b > a else had
            warn.append("%s %s: a corrected row (data_updated_at %s) replaces %s" % (fxf, "/".join(k), max(a, b)[:10], min(a, b)[:10]))
        elif (fxf, r.get("case_id_pkey")) in TIES:
            best[k] = max(had, r, key=lambda x: int(x.get("unique_id") or 0))
        else:
            err.append("%s %s: two rows with the same data_updated_at %s that differ" % (fxf, "/".join(k), a[:10] or "(none)"))
    return [best[k] for k in order], warn, err


def date_range(where):
    """The query's own collision_datetime bounds as (low, high), where its $where holds one date clause."""
    w = where or ""
    if w.count("collision_datetime") != 1:   # a compound clause (an exclusion, an or) has no one range to hold rows to
        return None, None
    m = re.search(r"collision_datetime\s+between\s+'([^']+)'\s+and\s+'([^']+)'", w)
    if m:
        return m.group(1), m.group(2)
    m = re.search(r"collision_datetime\s*>=?\s*'([^']+)'", w)
    return (m.group(1), None) if m else (None, None)


def check_query(name, rows, held_n, today):
    """The per-query checks: (failures, warnings). held_n: the held copy's row count, the baseline for the drop."""
    q = QUERIES[name]
    fxf, bad = q["fxf"], []
    n = len(rows)
    if n < q["floor"]:
        bad.append("%s: %d rows, floor %d" % (name, n, q["floor"]))
    if held_n and n < (1 - MAX_DROP) * held_n:
        bad.append("%s: %d rows, down from %d held (more than %d%%)" % (name, n, held_n, MAX_DROP * 100))
    if not n:
        return bad, []
    fields = set(k for r in rows[:500] for k in r)
    for f in [k for k in KEYS[fxf] if k in fields] + ([DATE] if DATE in fields else []):
        miss = sum(1 for r in rows if not r.get(f))
        if miss:
            bad.append("%s: %d rows with no %s" % (name, miss, f))
    if DATE in fields:
        lo, hi = date_range(q["where"])
        low = max(FIRST_DAY, (lo or FIRST_DAY)[:10])
        high = min((today + dt.timedelta(days=1)).isoformat(), (hi or "9999-12-31")[:10])
        out = [r[DATE] for r in rows if r.get(DATE) and not low <= r[DATE][:10] <= high]
        if out:
            bad.append("%s: %d rows dated outside %s to %s, e.g. %s" % (name, len(out), low, high, out[0]))
    _, warn, err = resolve(fxf, rows)
    return bad + ["%s: %s" % (name, e) for e in err[:5]] + (["%s: %d more ties" % (name, len(err) - 5)] if len(err) > 5 else []), warn


def check_joins(reads):
    """Every victim's and party's case dated within the crash reads' range is in the crash reads, at most MAX_UNJOINED
    missing. reads: {fxf: [rows of each query]}. Returns (failures, note)."""
    crash = [r for rows in reads.get("ubvf-ztfx", []) for r in rows if r.get(DATE)]
    if not crash:
        return [], "no crash read held, so no join to check"
    cases = {r["case_id_pkey"] for r in crash}
    lo, hi = min(r[DATE] for r in crash), max(r[DATE] for r in crash)
    bad, notes = [], []
    for fxf in ("nwes-mmgh", "8gtc-pjc6"):
        ids = {r["case_id_pkey"] for rows in reads.get(fxf, []) for r in rows
               if r.get(DATE) and r.get("case_id_pkey") and lo <= r[DATE] <= hi}
        if not ids:
            continue
        missing = ids - cases
        notes.append("%s %d of %d cases joined" % (fxf, len(ids) - len(missing), len(ids)))
        if len(missing) > MAX_UNJOINED * len(ids):
            bad.append("%s: %d of %d cases from %s to %s are not in the crash reads, e.g. %s" % (
                fxf, len(missing), len(ids), lo[:10], hi[:10], sorted(missing)[:3]))
    return bad, "; ".join(notes)


def stage_read(name, tries=4, backoff=(10, 30, 60)):
    """The query read into STAGE (the held copy put there first, so a re-read with the same rows keeps its date),
    retried after a transient failure. Returns the staged sfdata.Result."""
    from lib.fetch import is_transient
    held = path_of(name)
    STAGE.mkdir(parents=True, exist_ok=True)
    if held.exists():
        shutil.copy2(held, STAGE / held.name)
    for t in range(tries):
        try:
            r = sfdata.fetch(QUERIES[name]["fxf"], cache_dir=STAGE, refresh=True, floor=0, **kwargs(name))
            break
        except Exception as e:  # noqa: BLE001
            if not is_transient(e) or t == tries - 1:
                raise
            time.sleep(backoff[min(t, len(backoff) - 1)])
    assert (STAGE / held.name).exists(), "%s staged under another key" % name
    return r


def read(name):
    """The held rows of one query, one row per key (resolve()). A copy not held yet is read and checked first; a
    failed check raises Stop and holds nothing."""
    q = QUERIES[name]
    p = path_of(name)
    if not p.exists():
        r = stage_read(name)
        bad, _ = check_query(name, r.rows, 0, dt.date.today())
        if bad:
            os.remove(STAGE / p.name)
            raise Stop("; ".join(bad[:5]))
        CACHE.mkdir(parents=True, exist_ok=True)
        os.replace(STAGE / p.name, p)
    blob = json.loads(p.read_text())
    rows, _, err = resolve(q["fxf"], blob["rows"])
    if err:
        raise Stop("%s: %s" % (name, "; ".join(err[:5])))
    return sfdata.Result(q["fxf"], blob["params"], rows, dt.date.fromisoformat(blob["fetched_on"]), True)


# The people severely injured or killed in 2022 to 2024 that the map draws with a card: 922 placed of 923 in nwes-mmgh
# (read 2026-11-18). The window is closed, but DataSF revises
# old reports, so a re-read may move the count a little. A revision inside the band passes; a drop or jump outside it
# means a broken read or a changed query and stops the build.
PEOPLE_READ = 922
PEOPLE_BAND = (0.97, 1.05)
# The one published total the base reproduces: SFDPH counts 282 police-recorded severe injuries in 2022 (San Francisco
# Severe Traffic Injury Trends: 2015-2022, December 2024, Figure 14, p. 23,
# https://visionzerosf.org/wp-content/uploads/2024/12/Severe-Injury-Trends_2015-2022.pdf [primary — read 2026-11-20]),
# and our 2022 Severe Injury rows are 282 (research/sources/datasf-traffic-crashes.md, "Published total").
SEVERE_2022_PUBLISHED = 282
SEVERE_2022_TOLERANCE = 6     # about 2%: late reports and reclassified injuries, not a different count


def people_in_band(n):
    """None when the 2022 to 2024 people count is within PEOPLE_BAND of PEOPLE_READ, else the failure."""
    lo, hi = round(PEOPLE_READ * PEOPLE_BAND[0]), round(PEOPLE_READ * PEOPLE_BAND[1])
    return None if lo <= n <= hi else "%d people severely injured or killed in 2022 to 2024, outside %d to %d (read as %d)" % (
        n, lo, hi, PEOPLE_READ)


def severe_2022_matches(n):
    """None when the 2022 severe injuries are within SEVERE_2022_TOLERANCE of SFDPH's published 282, else the failure."""
    return None if abs(n - SEVERE_2022_PUBLISHED) <= SEVERE_2022_TOLERANCE else (
        "%d severe injuries in 2022, against SFDPH's published %d (more than %d apart)" % (n, SEVERE_2022_PUBLISHED, SEVERE_2022_TOLERANCE))
