"""The blocks a Public Works project page's Location field puts it on: the corridor between the limits it names, never whole cross streets.

    from lib.pw_extent import Extents
    ext = Extents()                      # reads the centreline (3psu-pn9h) once
    r = ext.of("Beale Street between Market Street and Folsom Street")
    r.cnns      # the three Beale blocks from Market to Folsom
    r.basis     # "corridor between limits"
    r.flag      # None, or why the limits could not be read

Public Works' Location field names a corridor and the streets that bound it
("Masonic Avenue from Geary Boulevard to Fell Street"), or an intersection
("The intersection of 20th Street and De Haro Street"). tools/projects/dpw-projects.py
resolves every street the field names and keeps every block of each, so the
cross streets came along whole: Beale Street Improvement Project, three blocks
of Beale, held 195 blocks including every block of Market and Folsom (review of
2026-09-29). This reads the field as the page writes it:

  corridor between limits   "<street> between <a> and <b>", "<street> from <a>
                            to <b>", "<street> (<a> to <b>)", "<street>: <a> to
                            <b>", "<street>, <a> to <b>". The corridor's blocks
                            from the block touching <a> to the block touching <b>.
  intersection              "The intersection of <a> and <b>", or a list of
                            "<a> and <b>" pairs: the blocks of both streets that
                            meet at that corner.
  interchange               "<street> underneath the 280 freeway and 101
                            freeway interchange": the corridor's blocks that
                            sit between ramps, in the run that carries a ramp
                            of every named freeway, as the centreline labels
                            them ("I280 N ON RAMP", "HWY 101 S OFF RAMP"); not
                            one freeway's own exit further along the street.
  address                   a building's street address and nothing else
                            ("747 Howard St", "1490 Mason St., San Francisco,
                            CA 94133"): the one block whose address range
                            holds the number (DataSF 3psu-pn9h's lf_/rt_ fadd
                            and toadd), never the whole street. Every
                            in-progress Public Works page with such a Location
                            is a building or a park (read 2026-09-29), so
                            reading it as its street put Moscone Expansion on
                            29 blocks of Howard. An address no block's range
                            holds places nothing, flagged.
  corridor only (flagged)   a street named with no limits the centreline can
                            find ("McAllister Street, 20th Street and 24th
                            Street", "Various intersections along Geneva
                            Avenue"). The first street named, which the page
                            writes corridor-first, and nothing else; `flag` says
                            the limits were not published or not found.

A limit is matched to the centreline's own cross-street labels with and
without its type, so "Jefferson Street, Jones to Powell" finds Jones St. A
limit whose name the corridor's labels do not carry still matches the corner
its own blocks meet the corridor at: the centreline labels Innes Avenue's
corner "FITCH ST", the street's name before it became Arelious Walker Drive,
while Arelious Walker Dr's own block ends at that corner (read 2026-09-29).
Nothing here guesses a limit: a limit that is not a cross street of the
corridor leaves the row corridor-only and flagged.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from streetindex import BlockIndex, canon  # noqa: E402
from streetnames import SUFFIX, streets_in_order  # noqa: E402

_TYPES = sorted({v for v in SUFFIX.values()} | {"ter", "aly", "hwy", "plz", "pkwy", "stwy", "walk", "row", "tunl",
                                                  "ramp", "path", "hl"}, key=len, reverse=True)
_TYPE_TAIL = re.compile(r"(?:%s)$" % "|".join(_TYPES))
_MAIN_TYPES = {"st", "ave", "blvd", "dr", "rd", "way", "ln", "ter", "pl", "ct"}
_WORD_NUM = {"first": "1st", "second": "2nd", "third": "3rd", "fourth": "4th", "fifth": "5th", "sixth": "6th",
             "seventh": "7th", "eighth": "8th", "ninth": "9th", "tenth": "10th", "eleventh": "11th",
             "twelfth": "12th"}

# "<corridor> <joiner> <a> <to|and> <b>", the forms Public Works writes.
_LIMITS = [
    re.compile(r"^(?P<c>.+?)\s*\(\s*(?:from\s+)?(?P<a>[^()]+?)\s+(?:to|and|through|-|–)\s+(?P<b>[^()]+?)\s*\)", re.I),
    re.compile(r"^(?P<c>.+?),?\s+between\s+(?P<a>.+?)\s+and\s+(?P<b>.+?)$", re.I),
    re.compile(r"^(?P<c>.+?),?\s+from\s+(?P<a>.+?)\s+(?:to|through)\s+(?P<b>.+?)$", re.I),
    re.compile(r"^(?P<c>.+?)\s*(?:[:,]|\s-\s)\s*(?P<a>.+?)\s+(?:to|through|-|–)\s+(?P<b>.+?)$", re.I),
]
# "Alemany Blvd. underneath the 280 freeway and 101 freeway interchange."
_INTERCHANGE = re.compile(r"^(?P<c>.+?)\s+(?:underneath|beneath|under|at)\s+(?:the\s+)?(?P<f>.*?\b\d{2,3}\b.*?)"
                          r"\s+interchange\b", re.I)
# "747 Howard St", "1490 Mason St., San Francisco, CA 94133": a number, then a
# street, then at most a city line. "24th Street" is a street, not an address.
_ADDRESS = re.compile(r"^(?P<n>\d{1,5})[A-Za-z]?\s+(?!(?:st|nd|rd|th)\b)(?P<s>[^,]+?)\.?\s*"
                      r"(?:,\s*san francisco\b.*)?$", re.I)
_INTERSECTION = re.compile(r"^(?:at\s+)?(?:the\s+)?(?:intersection\s+of\s+)?(?P<a>.+?)\s+(?:and|&|/|at)\s+(?P<b>.+?)$",
                           re.I)


def _bare(key):
    """A canon key without its street type: 'jonesst' -> 'jones'."""
    return _TYPE_TAIL.sub("", key) or key


class Extent(object):
    def __init__(self, cnns, basis, flag=None, corridor=None, limits=()):
        self.cnns, self.basis, self.flag = set(cnns), basis, flag
        self.corridor, self.limits = corridor, list(limits)
        self.corridor_name = None  # the corridor as the page names it, when only the corridor is held


class Extents(object):
    def __init__(self, blocks=None):
        self.bi = blocks or BlockIndex()
        self._ranges = None  # cnn -> address spans, read on the first address asked for
        # Every street key, and the same without its type, for names written
        # without one ("Junipero Serra", "Jones").
        self._bare = {}
        for k in self.bi._by_street:
            self._bare.setdefault(_bare(k), set()).add(k)

    # -- names
    def street_key(self, phrase, bare=True):
        """The centreline key for a street phrase, or None. `bare` also accepts a name written without its type."""
        phrase = re.sub(r"\([^)]*\)", " ", phrase or "")
        phrase = re.sub(r"\b(" + "|".join(_WORD_NUM) + r")\b", lambda m: _WORD_NUM[m.group(1).lower()], phrase,
                        flags=re.I)
        phrase = re.sub(r"\b(Blvd|Ave|St|Dr)\.", r"\1", phrase)
        for n in streets_in_order(phrase):
            k = canon(n)
            if k in self.bi._by_street:
                return k
        if not bare:
            return None
        words = re.findall(r"[A-Za-z0-9]+", phrase)
        # A phrase that ends in a street type names its type, and the typed
        # lookup above has already failed on it: a bare match would take the
        # type word for a name ("1 Sgt. John V. Young Lane" read as Lane
        # Street in the Bayview; Fable review, 2026-09-30). Only a name
        # written without a type ("Junipero Serra") is read bare.
        if words and words[-1].lower() in SUFFIX and words[-1].lower() != "embarcadero":
            return None
        # The longest run of trailing words that names one street without a type.
        for i in range(len(words)):
            cand = canon(" ".join(words[i:]))
            hit = self._bare.get(cand)
            if not hit:
                continue
            # "Junipero Serra" is JUNIPERO SERRA BLVD, not its ramps; two
            # ordinary types (Geneva Ave and Geneva St) are ambiguous.
            main = sorted(k for k in hit if k[len(_bare(k)):] in _MAIN_TYPES)
            return main[0] if len(main) == 1 else (next(iter(hit)) if len(hit) == 1 else None)
        return None

    def _limit_match(self, label, limit):
        """Does a block end's label (a canon key) name this limit phrase?"""
        if not label:
            return False
        # "Baker streets" in "between Scott and Baker streets".
        limit = re.sub(r"\s+(?:streets|avenues|boulevards)\b", "", limit or "", flags=re.I)
        lk = self.street_key(limit)
        # Among one corridor's cross streets the name without its type is
        # enough: the centreline labels Market Street's end at Octavia
        # "OCTAVIA ST" where the page writes Octavia Boulevard.
        if lk:
            return label == lk or _bare(label) == _bare(lk)
        words = re.findall(r"[A-Za-z0-9]+", limit)
        if len(words) > 1 and words[-1].lower() in SUFFIX:
            words = words[:-1]  # "Octavia Boulevard", which the centreline has only as Octavia St
        return bool(words) and _bare(label) == canon(" ".join(words))

    # -- places
    def between(self, corridor, a, b):
        """The corridor's blocks on the shortest run from cross street `a` to cross street `b`, or an empty set.

        Each block joins the two cross streets at its ends. The centreline
        draws blocks in either direction and a divided street twice, so the
        run is found as a path between cross-street labels rather than by
        chaining one block's end to the next one's start (which breaks where
        the drawing direction flips: Market Street, 13th Street). Both
        carriageways of a divided street are kept.
        """
        blocks = self.bi._by_street.get(corridor, [])
        adj = {}
        for x in blocks:
            if x["from"] and x["to"] and x["from"] != x["to"]:
                adj.setdefault(x["from"], []).append((x["to"], x["cnn"]))
                adj.setdefault(x["to"], []).append((x["from"], x["cnn"]))
        src = {n for n in adj if self._limit_match(n, a)} or self._corner_of(blocks, a)
        dst = {n for n in adj if self._limit_match(n, b)} or self._corner_of(blocks, b)
        if not src or not dst or src & dst:
            return set()
        # Breadth first over cross streets; every block joining two
        # consecutive labels on a shortest path is part of the run.
        dist = {n: 0 for n in src}
        frontier = sorted(src)
        while frontier and not dst & set(dist):
            nxt = []
            for n in frontier:
                for m, _ in adj[n]:
                    if m not in dist:
                        dist[m] = dist[n] + 1
                        nxt.append(m)
            frontier = sorted(set(nxt))
        hit = dst & set(dist)
        if not hit:
            return set()
        end = min(dist[n] for n in hit)
        # Walk back from the reached limit, keeping every label one step closer.
        keep, layer = set(), {n for n in hit if dist[n] == end}
        while layer:
            prev = set()
            for n in layer:
                for m, cnn in adj[n]:
                    if dist.get(m) == dist[n] - 1:
                        keep.add(cnn)
                        prev.add(m)
            layer = prev
        return keep

    def _corner_of(self, blocks, limit, tol_m=15.0):
        """The corridor's cross-street labels at the corners where the limit street's own blocks end.

        For a limit the corridor's labels name differently (a renamed street:
        the centreline still labels Innes Avenue's corner FITCH ST where
        Arelious Walker Dr's block ends). Positions are compared within
        15 m (50 ft); the limit must be a street the centreline has.
        """
        lk = self.street_key(re.sub(r"\s+(?:streets|avenues|boulevards)\b", "", limit or "", flags=re.I))
        if not lk:
            return set()
        ends = [pt for x in self.bi._by_street.get(lk, ()) if x.get("line") for pt in (x["line"][0], x["line"][-1])]
        if not ends:
            return set()
        k = 111320.0 * 0.7907  # metres per degree of longitude at 37.76 N
        out = set()
        for x in blocks:
            line = x.get("line")
            if not line:
                continue
            for label, pt in ((x["from"], line[0]), (x["to"], line[-1])):
                if label and any(((pt[0] - e[0]) * k) ** 2 + ((pt[1] - e[1]) * 110950.0) ** 2 <= tol_m ** 2
                                 for e in ends):
                    out.add(label)
        return out

    @staticmethod
    def _freeway_ramp(label, f):
        return bool(label) and "ramp" in label and re.search(r"(?:hwy|i|us)%s[nsew]?" % f, label) is not None

    def interchange(self, corridor, freeways):
        """The corridor's blocks inside the interchange where the named freeways ("280", "101") meet.

        The interchange is where the freeways meet, so it is held to the
        blocks that sit between ramps: both ends at a ramp corner, meaning a
        ramp label ("HWY 101 S OFF RAMP", "ALEMANY BLVD OFF RAMP") or a cross
        street that has its own ramp on the corridor (INDUSTRIAL ST, beside
        "INDUSTRIAL ST ON RAMP"; the corridor's own name does not count). Of
        those, the connected run that carries a ramp of every named freeway
        is kept. A block with a ramp of only one freeway at one end and a
        plain street at the other is that freeway's own exit, not the
        interchange: on Alemany Boulevard the I-280 ramps at Stoneybrook
        Avenue and Folsom Street are 0.6 to 0.8 mi west of the 280/101
        interchange (review of 2026-09-29). With no run that carries every
        named freeway, the corridor's blocks with an end at a ramp of any of
        them are kept, as before.
        """
        blocks = self.bi._by_street.get(corridor, ())
        labels = {lab for x in blocks for lab in (x["from"], x["to"]) if lab}
        own = _bare(corridor)
        ramps = {lab for lab in labels if "ramp" in lab}

        def ramp_corner(lab):
            if not lab:
                return False
            if lab in ramps:
                return True
            b = _bare(lab)
            return b != own and any(r.startswith(b) and r != lab for r in ramps)

        inner = [x for x in blocks if x["from"] != x["to"] and ramp_corner(x["from"]) and ramp_corner(x["to"])]
        # Connected runs of those blocks, joined at a shared corner.
        parent = {x["cnn"]: x["cnn"] for x in inner}

        def find(c):
            while parent[c] != c:
                parent[c] = parent[parent[c]]
                c = parent[c]
            return c

        at = {}
        for x in sorted(inner, key=lambda x: x["cnn"]):
            for lab in (x["from"], x["to"]):
                if lab in at:
                    parent[find(x["cnn"])] = find(at[lab])
                else:
                    at[lab] = x["cnn"]
        runs = {}
        for x in inner:
            runs.setdefault(find(x["cnn"]), []).append(x)
        out = set()
        for run in runs.values():
            labs = {lab for x in run for lab in (x["from"], x["to"])}
            if all(any(self._freeway_ramp(lab, f) for lab in labs) for f in freeways):
                out |= {x["cnn"] for x in run}
        if out:
            return out
        for x in blocks:
            if any(self._freeway_ramp(lab, f) for lab in (x["from"], x["to"]) for f in freeways):
                out.add(x["cnn"])
        return out

    def address_block(self, street, number):
        """The block of `street` whose left or right address range holds `number`, or None.

        The ranges come from the whole-row centreline query (sfdata.fetch("3psu-pn9h"),
        refreshed by pipeline/refresh-socrata.py), read once and only when an
        address is asked for."""
        if self._ranges is None:
            from sfdata import fetch
            self._ranges = {}
            for r in fetch("3psu-pn9h").rows:
                spans = []
                for a, b in (("lf_fadd", "lf_toadd"), ("rt_fadd", "rt_toadd")):
                    try:
                        lo, hi = sorted((int(float(r.get(a) or 0)), int(float(r.get(b) or 0))))
                    except ValueError:
                        continue
                    if hi > 0:
                        spans.append((lo, hi))
                if spans:
                    self._ranges[str(r.get("cnn") or "").strip()] = spans
        # A side of a block holds odd numbers or even ones; where two blocks'
        # ranges overlap (733 Kearny lies in 7758000's 701-749 and
        # 7759000's 730-798), the side whose parity matches holds it.
        blocks = self.bi._by_street.get(street, ())
        for same_side in (True, False):
            hits = sorted(b["cnn"] for b in blocks
                          if any(lo <= number <= hi and (not same_side or lo % 2 == number % 2)
                                 for lo, hi in self._ranges.get(b["cnn"], ())))
            if hits:
                return hits[0]
        return None

    def meeting(self, street, cross):
        """The blocks of `street` that start or end at `cross`."""
        return {b["cnn"] for b in self.bi._by_street.get(street, ()) if self._limit_match(b["from"], cross)
                or self._limit_match(b["to"], cross)}

    def _place(self, cl):
        """(cnns, basis, corridor, limits) for one clause, or None."""
        for rx in _LIMITS:
            m = rx.match(cl)
            if not m:
                continue
            ck = self.street_key(m.group("c"))
            if not ck:
                continue
            ext = self.between(ck, m.group("a"), m.group("b"))
            if ext:
                return ext, "corridor between limits", ck, [m.group("a").strip(), m.group("b").strip()]
        m = _INTERCHANGE.match(cl)
        if m:
            ck = self.street_key(m.group("c"))
            fw = re.findall(r"\b(\d{2,3})\b", m.group("f"))
            ext = self.interchange(ck, fw) if ck and fw else set()
            if ext:
                return ext, "interchange", ck, ["the %s interchange" % " and ".join(fw)]
        m = _INTERSECTION.match(cl)
        # Each side of an intersection is one street, not a clause with its
        # own limits ("13th St. between Valencia St." is not a corner).
        if m and not any(re.search(r"\b(?:between|from|to)\b|\s-\s", m.group(g), re.I) for g in ("a", "b")):
            ka, kb = self.street_key(m.group("a")), self.street_key(m.group("b"))
            if ka and kb and ka != kb:
                ext = self.meeting(ka, m.group("b")) | self.meeting(kb, m.group("a"))
                if ext:
                    return ext, "intersection", ka, [m.group("b").strip()]
        return None

    def of(self, location):
        """The Extent a Location field describes."""
        text = re.sub(r"\s+", " ", (location or "").replace("’", "'")).strip()
        if not text:
            return Extent((), "no location", "the page publishes no Location")
        # A list of places: semicolons, line breaks, ") and " between two
        # corridors, "----" or a leading bullet. A clause that reads as no
        # place is split again on " - " ("Islais Creek Bridge - Third Street
        # between Cargo Way and Marin Street", "- Page Street and Buchanan
        # Street - Page Street and Laguna Street").
        text = re.sub(r"^-\s*", "", text)
        # ", Mission Street between ..." starts a second corridor; ", between
        # Clay Street and ..." after an address does not.
        clauses = [c.strip(" -.") for c in re.split(
            r";|\n|(?<=\))\s+and\s+|-{3,}|,\s+(?!between\b|from\b)(?=[^,]*\b(?:between|from)\b)", text)
            if c.strip(" -.")]
        cnns, bases, corridor, limits = set(), [], None, []
        for cl in clauses:
            got = None
            if re.search(r"\s-\s", cl):
                # Split on " - " when every piece that names a street is a
                # place on its own; a piece naming no street is a label.
                pieces = [p.strip(" -.") for p in re.split(r"\s+-\s+", cl) if p.strip(" -.")]
                placed = [(p, self._place(p)) for p in pieces]
                streety = [(p, g) for p, g in placed if g or self.street_key(p, bare=False)]
                if streety and all(g for _, g in streety):
                    parts = [g for _, g in streety]
                    got = (set().union(*(g[0] for g in parts)), " and ".join(sorted({g[1] for g in parts})),
                           parts[0][2], [x for g in parts for x in g[3]])
            if got is None:
                got = self._place(cl)
            if got:
                cnns |= got[0]
                bases.append(got[1])
                corridor = corridor or got[2]
                limits += got[3]
        if cnns:
            return Extent(cnns, " and ".join(sorted(set(bases))), None, corridor, limits)
        # A building's street address: the block that carries the number.
        m = _ADDRESS.match(text)
        if m:
            key = self.street_key(m.group("s"), bare=False) or self.street_key(m.group("s"))
            if key:
                got = self.address_block(key, int(m.group("n")))
                if got:
                    return Extent({got}, "address", None, key, [m.group("n")])
                return Extent((), "address", "no block of %s carries number %s in the centreline's address ranges"
                              % (key, m.group("n")), key)
        # No limits read: the first street named, alone, and say so. Only a
        # name written with its type counts here: "Excelsior" or "Sunset" in
        # a list of neighbourhoods is not Excelsior Avenue.
        first = next(((canon(n), n) for c in re.split(r",|\band\b|:|\(", text) for n in streets_in_order(c)
                      if canon(n) in self.bi._by_street), None)
        if first is None:
            return Extent((), "no street", "the Location names no street the centreline has")
        e = Extent({b["cnn"] for b in self.bi._by_street[first[0]]}, "corridor only",
                   "the Location names no limits the centreline has, so the row holds the corridor street "
                   "only, whole", first[0])
        e.corridor_name = first[1]
        return e
