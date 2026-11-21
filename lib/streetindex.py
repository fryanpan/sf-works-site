#!/usr/bin/env python3
"""The city's own list of street names, and the blocks each one covers.

    from streetindex import StreetIndex
    idx = StreetIndex()
    idx.is_street("mission st")        # True
    idx.is_street("following mission st")  # False
    idx.cnns("22nd st")                # {'1234000', ...}
    idx.resolve(streets_in_order(text))    # only the names that exist

`lib/streetnames.py` reads street names out of prose, and it was built for
hearing orders, where the text is terse and formulaic. Pointed at a project
page's paragraphs it also returns things that merely end in a suffix word:
"craut st", "redesigned st", "project-related st", "following mission st". Each
of those is a candidate match waiting to be made against a real project, and a
match on a name that does not exist is the failure this repo already measured
once — a first sample of eight confident project-to-document links came back
eight wrong.

Reading prose more cleverly is the wrong fix, because no amount of grammar tells
you whether "Craut" is a street in San Francisco. The city does. `3psu-pn9h` is
the street centreline: every block of every street, with its name and its CNN.
Checking an extracted name against that list turns a guess into a lookup, and
the same lookup hands back the CNNs, which is what a geographic join needs
anyway.

The names are normalised to the short form `streetnames.py` produces — "22nd st",
"cesar chavez st" — so the two modules speak the same language and a caller does
not have to translate between them.
"""

import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sfdata import fetch  # noqa: E402
from streetnames import SUFFIX  # noqa: E402

STREETS = "3psu-pn9h"

# The centreline writes the type as the city does on a sign — ST, AVE, BLVD, and
# a few this repo's suffix table does not carry because no record it parses ever
# uses them. An unmapped type keeps its own lowercase form rather than being
# dropped, so a street named with it can still be recognised.
def _norm(street, st_type):
    name = re.sub(r"\s+", " ", (street or "").strip().lower())
    suffix = (st_type or "").strip().lower()
    suffix = SUFFIX.get(suffix, suffix)
    return f"{name} {suffix}".strip()


# The city and everybody else spell the same street differently, in three ways
# that each silently drop a CORRECT match — the worst kind of failure here,
# because a lost match looks like a street with no record rather than like a bug:
#
#   zero padding   the centreline has "06TH AVE"; every human source, and every
#                  hearing order, writes "6th Avenue".
#   spacing        the centreline has "BAY SHORE"; SFMTA, the Board and the
#                  press all write "Bayshore Boulevard".
#   the article    the centreline has "THE EMBARCADERO"; prose drops the "the"
#                  about as often as it keeps it.
#
# So comparison runs on a key with all three flattened. It is deliberately not
# fuzzy: nothing here tolerates a typo or a near-miss, because a join that
# guesses is the thing this module exists to stop.
_LEADING_THE = re.compile(r"^the ")
_NUMBER = re.compile(r"\b0+(\d)")


def canon(name):
    """The comparison key for a street name, from either side of the join."""
    n = _LEADING_THE.sub("", (name or "").strip().lower())
    n = _NUMBER.sub(r"\1", n)
    return re.sub(r"[^a-z0-9]", "", n)


class StreetIndex:
    """Every street name the city publishes, with the CNNs behind it."""

    def __init__(self, rows=None):
        # `rows` is for tests and for a caller that already holds the dataset;
        # everything else goes through the shared cache in sfdata.
        if rows is None:
            rows = fetch(STREETS, select="cnn,street,st_type", floor=10000).rows
        self._cnns = {}
        # The name the city prints, for anything that has to show one back.
        self._display = {}
        for r in rows:
            name = _norm(r.get("street"), r.get("st_type"))
            if not name:
                continue
            key = canon(name)
            cnn = str(r.get("cnn") or "").strip()
            if cnn:
                self._cnns.setdefault(key, set()).add(cnn)
                self._display.setdefault(key, name)

    def __len__(self):
        return len(self._cnns)

    def is_street(self, name):
        return canon(name) in self._cnns

    def cnns(self, name):
        return set(self._cnns.get(canon(name), ()))

    def display(self, name):
        """The city's own spelling, so output does not invent one."""
        return self._display.get(canon(name), name)

    def resolve(self, names):
        """The subset of `names` the city actually has, order preserved.

        Order is kept because it carries meaning in these sources: they are
        written corridor-first, so the first surviving name is the street the
        record is about and the rest bound its extent.
        """
        seen, out = set(), []
        for n in names:
            k = canon(n)
            if k in self._cnns and k not in seen:
                seen.add(k)
                out.append(self._display[k])
        return out


def _selftest():
    idx = StreetIndex()
    print(f"{len(idx):,} distinct street names")
    # The last four are the spellings that used to miss: the city writes
    # "BAY SHORE", "06TH AVE", "03RD ST" and "THE EMBARCADERO".
    real = ["mission st", "22nd st", "cesar chavez st", "bayshore blvd",
            "6th ave", "3rd st", "embarcadero"]
    fake = ["redesigned st", "project-related st", "following mission st"]
    for n in real:
        print(f"  {n:<24} {'yes' if idx.is_street(n) else 'NO'}  {len(idx.cnns(n))} blocks")
    for n in fake:
        print(f"  {n:<24} {'STILL MATCHES' if idx.is_street(n) else 'rejected'}")


if __name__ == "__main__":
    _selftest()


# ---------------------------------------------------------------------------
# Blocks, not just names.
#
# A street name is not a place. Third Street runs seven miles, so a library on
# Third and a paving job on Third share a name and share no ground — which is
# exactly how a project page got offered beside an unrelated sewer job, and
# what Bryan sent back on 2026-09-22: "none of these look related ... the
# method is broken."
#
# The centreline already carries what fixes it. Every row is ONE BLOCK, with
# its own geometry in `line` and the cross street at each end in `f_st` and
# `t_st`. That gives two things this repo has been missing:
#
#   an extent   "Mission St from 14th St to 16th St" resolves to the blocks
#               between those cross streets, rather than to all 138 of them.
#   a shape     a project's blocks can be drawn on a map, because each one
#               knows where it is.
#
# It is a heavier fetch than StreetIndex — six fields over 17,000 rows — so it
# is a separate class, and a caller that only needs to know whether a name is
# real should keep using StreetIndex.
BLOCK_FIELDS = "cnn,street,st_type,f_st,t_st,line"


class BlockIndex:
    """Every block of every street, with its ends and its geometry."""

    def __init__(self, rows=None):
        if rows is None:
            rows = fetch(STREETS, select=BLOCK_FIELDS, floor=10000).rows
        self.blocks = {}
        self._by_street = {}
        for r in rows:
            cnn = str(r.get("cnn") or "").strip()
            name = _norm(r.get("street"), r.get("st_type"))
            if not cnn or not name:
                continue
            key = canon(name)
            # The end labels are themselves street names most of the time, but
            # not always: the centreline also writes "END: EAST" and similar
            # for a block that stops at nothing. Those canonicalise to
            # something no street matches, which is the right outcome — they
            # simply never resolve as a cross street.
            block = {
                "cnn": cnn,
                "street": key,
                "from": canon(r.get("f_st")),
                "to": canon(r.get("t_st")),
                "line": (r.get("line") or {}).get("coordinates") or [],
            }
            self.blocks[cnn] = block
            self._by_street.setdefault(key, []).append(block)

    def __len__(self):
        return len(self.blocks)

    def geometry(self, cnns):
        """The line segments for these blocks, as [[ [lon,lat], ... ], ...]."""
        out = []
        for c in cnns:
            b = self.blocks.get(str(c))
            if b and b["line"]:
                out.append(b["line"])
        return out

    def extent(self, street, start=None, end=None):
        """The blocks of `street` between two cross streets, as a set of CNNs.

        With no cross streets it is the whole street, which is honest but
        rarely useful: a record that names no extent has not told you one.
        With them, it walks the street's blocks from the one touching `start`
        to the one touching `end`.

        It returns the EMPTY SET when the cross streets are named but cannot
        be found on this street, rather than falling back to the whole street.
        That distinction is the point of the class: a failed extent must not
        silently become a seven-mile one.
        """
        blocks = self._by_street.get(canon(street), [])
        if not blocks:
            return set()
        a, b = canon(start), canon(end)
        if not a or not b:
            return {x["cnn"] for x in blocks}

        # Order the blocks along the street by chaining each one's end to the
        # next one's start. The centreline does not publish a sequence number,
        # so the chain IS the order, and a street that branches or has a gap
        # produces more than one chain.
        for chain in self._chains(blocks):
            names = [x["from"] for x in chain] + [chain[-1]["to"]]
            if a in names and b in names:
                i, j = names.index(a), names.index(b)
                lo, hi = (i, j) if i <= j else (j, i)
                return {x["cnn"] for x in chain[lo:hi]}
        return set()

    @staticmethod
    def _chains(blocks):
        """The street's blocks, grouped into runs that join end to end."""
        starts = collections.defaultdict(list)
        for b in blocks:
            starts[b["from"]].append(b)
        # A block whose start is nobody else's end begins a chain.
        ends = {b["to"] for b in blocks}
        heads = [b for b in blocks if b["from"] not in ends] or blocks[:1]
        out, used = [], set()
        for head in heads:
            if head["cnn"] in used:
                continue
            chain, cur = [], head
            while cur is not None and cur["cnn"] not in used:
                used.add(cur["cnn"])
                chain.append(cur)
                nxt = [x for x in starts.get(cur["to"], [])
                       if x["cnn"] not in used]
                cur = nxt[0] if nxt else None
            out.append(chain)
        # Anything not reached from a head — a loop — is its own chain.
        for b in blocks:
            if b["cnn"] not in used:
                used.add(b["cnn"])
                out.append([b])
        return out
