#!/usr/bin/env python3
"""Mirror every SFPUC Commission agenda item since 2019 from SFGovTV's Granicus archive, with decisions from the minutes extract, to data/sfpuc-commission/.

    tools/meetings/fetch-sfpuc-commission.py              # since 2019-01-01; fetches only what is new or draft

tools/meetings/sfpuc-commission.py reads the Commission's minutes PDFs off
sfpuc.gov, which lists them from 2021-01-26 on. That left 2019 and 2020
unread, and the minutes arrive a meeting late. This reads the agenda index
for every meeting SFGovTV recorded on Granicus view 22, then, where the
minutes extract (data/extract/sfpuc-commission/minutes.json, built by
sfpuc-commission.py) has the same meeting, gives each item its motion and
resolution number by item number.

A water-main or sewer contract award names the streets it opens, so for an
SFPUC job the award is usually its first dated city decision.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib.fetch import Fetcher  # noqa: E402
from lib.mirror import Mirror, summary  # noqa: E402
from lib import granicus  # noqa: E402

VIEWS = {22: "SFPUC Commission"}
MINUTES = os.path.join(ROOT, "data", "extract", "sfpuc-commission", "minutes.json")


def _words(t):
    return set(re.findall(r"[a-z0-9]{3,}", (t or "").lower()))


_CODE = re.compile(r"\b(?:[A-Z]{2,4}-\d{2,4}[A-Z]?|PRO\.\d{4})", re.I)


def same_item(agenda_title, minutes_title, loose=False):
    """True when two titles are the same item.

    Loose: most of the shorter title's words are in the other, which is right
    when the two already share an item number. Otherwise the overlap must
    also be a fair share of the longer title, or a short heading such as
    "Communications" is found inside every long award.
    """
    ca, cb = set(_CODE.findall(agenda_title or "")), set(_CODE.findall(minutes_title or ""))
    if ca and cb and not ca & cb:
        return False  # two awards read alike; their contract numbers do not
    a, b = _words(agenda_title), _words(minutes_title)
    if not a or not b:
        return False
    small = a if len(a) <= len(b) else b
    large = b if small is a else a
    common = len(a & b)
    return len(small) >= 3 and common >= 0.8 * len(small) and (loose or common >= 0.4 * len(large))


# Bumped whenever the reading of the minutes changes; a run re-reads from disk
# every meeting stamped with an older one (granicus.reparse). 2: severed
# consent items, no staff-report sub-bullets.
PARSER = 2

_EXCLUDING = re.compile(r"(?i)\bexclud\w*\s+(?:items?\s+)?((?:\d{1,2}[a-z]?\b(?:\s*(?:,|and|&)\s*)?)+)")


def excluded(decision):
    """Items a consent vote leaves out: "approve Consent Calendar, excluding 8h" -> {"8h"}."""
    m = _EXCLUDING.search(decision or "")
    return {x.lower() for x in re.findall(r"\d{1,2}[a-z]?", m.group(1))} if m else set()


def keep_minutes_item(m):
    """True for a minutes item that is a decision the agenda index lacks.

    The minutes also number the bullets of staff reports, presentations and
    communications ("Final HHWP Datasheets", a speaker's name run into a
    budget heading) and the minutes approved; those carry no resolution and
    sit under no consent calendar, and are not decisions."""
    parent = str(m.get("parent") or "")
    return bool(m.get("resolution")) or bool(re.match(r"(?i)\s*consent calendar", parent))


def item_order(no):
    """Agenda order of an item number: 7 before 7a before 7b before 8."""
    m = re.match(r"^(\d+)(?:\.(\d+))?([a-z]?)", str(no).lower())
    return (int(m.group(1)), int(m.group(2) or 0), m.group(3)) if m else (999, 0, str(no))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2019-01-01")
    ap.add_argument("--refetch", action="store_true")
    ap.add_argument("--offline", action="store_true",
                    help="no fetch: re-apply the clean-up and the minutes to every meeting already mirrored")
    args = ap.parse_args()
    by_date = {}
    if os.path.exists(MINUTES):
        for m in json.load(open(MINUTES, encoding="utf-8"))["records"][0]["meetings"]:
            by_date.setdefault(m["date"], m)

    def vote_for(no, decision):
        """(decision, severed): a consent vote that excludes this item is not its vote."""
        if decision and str(no).lower() in excluded(decision):
            return None, True
        return decision, False

    def enrich(rec):
        rec["parser"] = PARSER
        mt = by_date.get(rec["date"])
        if not mt:
            return rec
        rec["sources"]["minutes"] = mt["url"]
        rec["status"] = "final"
        # Idempotent: what an earlier run took from the minutes is dropped and
        # read again, so a rule change reaches meetings already mirrored.
        rec["items"] = [{k: v for k, v in it.items() if k not in ("decision", "resolution", "text", "severed")}
                        for it in rec["items"] if it.get("from") != "minutes"]
        by_no = {str(i["item"]).lower(): i for i in mt["items"]}
        have = {it["no"].lower() for it in rec["items"]}
        for it in rec["items"]:
            m = by_no.get(it["no"].lower())
            # The minutes of a few meetings number one step off the agenda
            # (2024-08-27: agenda 5e is minutes 6e), so a number alone would
            # hand an item another item's vote. The titles have to agree.
            if not m or not same_item(it["title"], m.get("title"), loose=True):
                continue
            decision, cut = vote_for(it["no"], m.get("decision"))
            if decision:
                it["decision"] = decision
            if cut:
                it["severed"] = True
            if m.get("resolution"):
                it["resolution"] = m["resolution"]
            # The minutes print the whole item; the agenda index often a
            # shortened title. Keep the longer, since names are matched on it.
            if len(m.get("title") or "") > len(it["title"]) and re.search(r"[a-z]", m["title"]):
                it["text"] = m["title"][:1500]
        # Granicus indexes a consent calendar as one point, "7 CONSENT
        # CALENDAR", and never its lettered items, which is where most
        # contract awards sit: WD-2780 was awarded on 2026-06-23 as item 7c.
        # The minutes print every lettered item with its own resolution, so
        # each one the index lacks is added from them, after its parent.
        added = []
        for m in mt["items"]:
            no = str(m.get("item") or "")
            # Keyed on the title, not the number: the minutes extract numbers
            # some meetings off the agenda (2026-07-28's consent items read as
            # 5c and 5d), and a number clash would drop a real award.
            if not no or not (m.get("title") or "").strip():
                continue
            if any(same_item(x.get("text") or x["title"], m["title"], loose=x["no"].lower() == no.lower())
                   for x in rec["items"]):
                continue
            if m.get("procedural") is True or str(m.get("procedural")) == "True":
                continue
            if not keep_minutes_item(m):
                continue
            decision, cut = vote_for(no, m.get("decision"))
            added.append({"no": no, "title": re.sub(r"\s+", " ", m["title"]).strip()[:1500],
                          "parent": m.get("parent") if m.get("parent") not in (None, "None") else None,
                          "decision": decision, "resolution": m.get("resolution"),
                          "from": "minutes", **({"severed": True} if cut else {})})
            have.add(no.lower())
        if added:
            rec["items"] = sorted(rec["items"] + added, key=lambda it: item_order(it["no"]))
        return rec

    mirror = Mirror("sfpuc-commission", "SFPUC Commission", granicus.listing_url(22))
    if args.offline:
        print("  rewrote %d meetings from disk" % granicus.rewrite(mirror, enrich))
        return
    idx = granicus.mirror_views(mirror, Fetcher("sfpuc-commission-granicus", pause=0.5, refetch=args.refetch),
                                VIEWS, args.since, enrich=enrich,
                                notes=["Agendas from SFGovTV's Granicus view 22; decisions from the minutes on sfpuc.gov "
                                       "(tools/meetings/sfpuc-commission.py), which start 2021-01-26."])
    # Final meetings are never fetched again: a change in how the minutes are
    # read, or minutes read after a meeting went final, reach them from disk.
    n = granicus.reparse(mirror, enrich, PARSER,
                         stale=lambda rec: not (rec.get("sources") or {}).get("minutes") and rec["date"] in by_date)
    if n:
        idx = json.load(open(os.path.join(mirror.dir, "index.json"), encoding="utf-8"))
    print("  re-read %d meetings from disk (parser %d)" % (n, PARSER))
    print(summary(idx))


if __name__ == "__main__":
    main()
