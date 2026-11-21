"""One JSON file per meeting under data/<body>/meetings/, scrubbed, with an index that says what is missing.

Every deciding body's fetch script writes through a Mirror, so each body's
record on disk has one shape and one set of rules:

    data/<body>/meetings/<YYYY-MM-DD>-<id>.json   one meeting, every item
    data/<body>/index.json                        every meeting the body lists,
                                                  and what became of each

A meeting file:

    {"body": "sfcta-board", "committee": "Transportation Authority Full Board",
     "date": "2026-09-22", "id": "g24-53202", "status": "final",
     "sources": {"agenda": "...", "minutes": "..."}, "fetched": "2026-09-28",
     "items": [{"no": "7", "title": "Allocate $22,500,000 in Prop L Funds ...",
                "decision": "...", "url": "..."}]}

`status` is what makes a rerun cheap. A final meeting is never fetched again.
A draft one is: an agenda posted for a meeting not yet held, or a meeting
whose minutes may still appear. `settled()` holds the rule.

The scrub is extract.py's: individual email addresses and phone numbers go,
institutional inboxes stay, and a write that still holds a personal address
is refused rather than made, because these files are tracked.

The index is the coverage record C1 of the audit criteria reads: how many
meetings the body lists in the window, how many are mirrored with at least
one item, and the reason for each that is not.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import datetime as dt
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from extract import EMAIL, KEEP, scrub  # noqa: E402
from lib import stable  # noqa: E402

DATA = os.path.join(ROOT, "data")


def settled(date, has_minutes=False, today=None, final_after_days=45):
    """True when a meeting's record will not change any more.

    Held more than `final_after_days` ago, or held and its minutes are in.
    An agenda for a meeting not yet held, or one held last week whose minutes
    are due at the next meeting, stays a draft and is fetched again.
    """
    today = today or dt.date.today()
    d = dt.date.fromisoformat(date)
    if d > today:
        return False
    return has_minutes or (today - d).days > final_after_days


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def _norm(v):
    return re.sub(r"\W+", " ", str(v or "").lower()).strip()


def item_key(it):
    """What makes one agenda item one item: its number, title, text, file and
    link, compared without case or punctuation. Two items that agree on all of
    them are the same point read twice (Granicus lists some points twice in
    one agenda); the quality checks key the mirror's items on this, with the
    meeting's date and id (pipeline/transportation-quality.py)."""
    return (_norm(it.get("no")), _norm(it.get("title")), _norm(it.get("text")),
            str(it.get("file") or ""), str(it.get("url") or ""))


def unique_items(items):
    """The items in agenda order, each point once."""
    out, seen = [], set()
    for it in items or ():
        k = item_key(it)
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


class Mirror(object):
    def __init__(self, body, name, source, root=None):
        self.body, self.name, self.source = body, name, source
        self.dir = root or os.path.join(DATA, body)
        self.meetings_dir = os.path.join(self.dir, "meetings")

    def path(self, date, mid):
        return os.path.join(self.meetings_dir, "%s-%s.json" % (date, slug(mid)))

    def read(self, date, mid):
        p = self.path(date, mid)
        if not os.path.exists(p):
            return None
        return json.load(open(p, encoding="utf-8"))

    def is_final(self, date, mid):
        rec = self.read(date, mid)
        return bool(rec and rec.get("status") == "final" and rec.get("items"))

    def write(self, rec):
        """Scrub one meeting, refuse on a leak, write it. Returns the clean record."""
        for k in ("date", "id", "items", "status"):
            if k not in rec:
                raise ValueError("meeting record lacks %r" % k)
        clean = scrub(dict(rec, body=self.body, items=unique_items(rec["items"])))
        text = json.dumps(clean, ensure_ascii=False)
        leaked = [e for e in set(EMAIL.findall(text)) if not KEEP.match(e)]
        if leaked:
            raise ValueError("REFUSING TO WRITE %s %s: %d personal email address(es) survived the scrub"
                             % (self.body, rec["date"], len(leaked)))
        os.makedirs(self.meetings_dir, exist_ok=True)
        # A draft re-read that found nothing new keeps the file as it was.
        stable.write_json(self.path(rec["date"], rec["id"]), clean, indent=1)
        return clean

    def all(self):
        """Every mirrored meeting, oldest first."""
        out = []
        for p in sorted(glob.glob(os.path.join(self.meetings_dir, "*.json"))):
            out.append(json.load(open(p, encoding="utf-8")))
        return out

    def write_index(self, listed, since, notes=None):
        """Record what the body lists since `since` and what became of each.

        `listed` is a list of {"date", "id", "committee"?, "outcome", "reason"?}
        where outcome is one of mirrored, unreachable, empty, no-agenda. A
        meeting counts as missing unless it is mirrored with at least one item.
        """
        # Date then id: the body's own listing order for meetings on one day
        # varies between reads, and the index flipped with no new meeting.
        want = sorted((m for m in listed if m["date"] >= since), key=lambda m: (m["date"], m["id"]))
        # A final meeting is never fetched again, so one written before
        # write() kept each point once is put right here, once.
        for m in self.all():
            if m.get("items") and len(unique_items(m["items"])) < len(m["items"]):
                self.write(m)
        held = {(m["date"], slug(m["id"])): m for m in self.all() if m.get("items")}
        have = set(held)
        for m in want:
            # A re-read of a draft that failed (the page would not load, or it
            # parsed to nothing this time) leaves the copy we had on disk. That
            # meeting is still mirrored, from its last good read, and the run log says so. The note stays out of
            # the index: one re-read of SFPUC's 2022-07-12 agenda parsed to nothing and the next did not, so the
            # tracked index flipped between two runs with no new meeting (2026-11-10).
            k = (m["date"], slug(m["id"]))
            if m.get("outcome") in ("unreachable", "empty") and k in held:
                print("  %s %s: re-read failed (%s); the copy fetched %s is kept"
                      % (m["date"], m["id"], m.get("reason") or m["outcome"], held[k].get("fetched")))
                m.pop("reason", None)
                m["outcome"] = "mirrored"
        for m in want:
            if m.get("outcome") == "mirrored" and (m["date"], slug(m["id"])) not in have:
                m["outcome"], m["reason"] = "empty", "mirrored with no items"
        missing = [m for m in want if m.get("outcome") != "mirrored"]
        held = [m for m in want if m["date"] <= dt.date.today().isoformat()]
        idx = {
            "body": self.body, "name": self.name, "source": self.source,
            "generated": dt.date.today().isoformat(), "since": since,
            "range": [want[0]["date"], want[-1]["date"]] if want else None,
            "listed": len(want), "held": len(held),
            "mirrored": len(want) - len(missing), "missing": len(missing),
            "missingShare": round(len(missing) / len(want), 4) if want else None,
            "items": sum(len(m.get("items") or ()) for m in self.all() if m["date"] >= since),
            "notes": notes or [],
            "meetings": want,
        }
        os.makedirs(self.dir, exist_ok=True)
        stable.write_json(os.path.join(self.dir, "index.json"), idx, indent=1)
        return idx


# A dash the source lost in transit: Granicus serves some Public Works
# Commission titles with "?" where the en dash was ("Sewer Replacement ?
# Contract Award"). A question mark never follows a space in English, so a
# " ? " between two words is a dash. Mended when a reader loads the mirror,
# not in the file, which keeps what the source served.
LOST_DASH = re.compile(r"(?<=[\w.)\]]) \? (?=[\w(\[])")


def mend(text):
    """A title or text with lost dashes put back; anything else unchanged."""
    return LOST_DASH.sub(" \u2013 ", text) if isinstance(text, str) else text


class MirrorMissing(RuntimeError):
    pass


def load(body, strict=True):
    """Every mirrored meeting of one body, oldest first.

    The index is tracked; for the Board of Supervisors the meeting files are
    not (about 30 MB, gitignored), so a fresh checkout holds an index that
    says 1,627 meetings are mirrored and no files behind it. Reading that as
    "no meetings" silently dropped 31,621 items from every project record
    while the coverage report still read the index and said the body was
    covered. So when the files on disk fall short of what the index says was
    mirrored, this raises and names the script that rebuilds them.
    `strict=False` returns what is there.
    Item titles and text come back with lost dashes mended (`mend`).
    """
    m = Mirror(body, body, None)
    recs = m.all()
    idx = index(body)
    if strict and idx:
        want = idx.get("mirrored") or 0
        have = len([r for r in recs if r["date"] >= (idx.get("since") or "")])
        if have < want:
            raise MirrorMissing(
                "%s: the index says %d meetings are mirrored but %d are on disk under %s. "
                "Rebuild them with tools/meetings/fetch-%s.py (see data/%s/README.md if there is one) "
                "before reading this body." % (body, want, have, os.path.relpath(m.meetings_dir, ROOT), body, body))
    for r in recs:
        for it in r.get("items") or []:
            for k in ("title", "text"):
                if it.get(k):
                    it[k] = mend(it[k])
    return recs


def index(body):
    p = os.path.join(DATA, body, "index.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def summary(idx):
    return ("%s: %d listed %s..%s, %d mirrored, %d missing (%.1f%%), %d items"
            % (idx["body"], idx["listed"], *(idx["range"] or ["-", "-"]), idx["mirrored"],
               idx["missing"], 100 * (idx["missingShare"] or 0), idx["items"]))
