"""Read an officer's free-text vehicle_make ("Toyota/Highlander/Silver", "TOYT", "HONDA CIVIC/WH") as a clean make and model.

    from vehicle_parse import Matcher
    m = Matcher(vpic_makes, models_for_make)      # see vehicle-fields.py for how both are built
    m.parse("Toyota/Highlander/Silver")
    # Parse(make="TOYOTA", model="Highlander", make_how="vpic", model_how="exact", reason=None)

THE FIELD. DataSF's parties (8gtc-pjc6) and victims (nwes-mmgh) tables have one `vehicle_make` field and no
model field. Before 2018 it mostly holds a make, often as a four-letter NCIC code (TOYT, MERZ, CHEV). Since
2018 it usually holds the officer's make, model and colour, split by slashes, spaces, bars or commas, in
whatever spelling the officer typed.

HOW A STRING IS READ, in order. Nothing is guessed: a step that is not sure leaves the field empty and
says why, in `reason`.

  1. Normalise: upper case, one space between words, separators (/ | , ; \\ and " - ") as segment
     breaks, parenthesised notes and colour words dropped (lookup_key). Everything below reads that key.
  2. Make. The longest run of one to three leading words whose letters and digits, squashed together,
     equal a make vPIC lists for cars, trucks, MPVs, buses, motorcycles or low speed vehicles, or an
     alias in make-aliases.csv (NCIC codes and misspellings seen in the data). A make vPIC lists only
     as a low speed vehicle, or one in NOT_MAKES (ordinary words and bicycle brands that vPIC also lists,
     such as TITAN and COLUMBIA), counts only through an alias. Failing that, the first
     word within one edit of exactly one *common* make (one with at least COMMON_MAKE_ROWS rows spelled
     exactly), for words of five letters or more with the same first letter; in a five-letter word the
     edit may not change a letter (SPART is Spartan, not SMART). Words that are not makes (UNKNOWN, OTHER, BICYCLE,
     colours) give reason "no make named".
  3. Model, from the words after the make, against vPIC's model names for that make (GetModelsForMake),
     squashed the same way so "RAV-4", "RAV 4" and "Rav4" are one key. Tried in order:
       exact      one to three words equal a model name.
       series     a letters-and-number code reduced to its family: C250 to C-Class, RX350 to RX,
                  328 to 328i. Only when the family is a vPIC model of that make.
       abbrev     a word of three or more letters that begins exactly one model name (HIGHLAND, ODYS),
                  or begins several that all extend the shortest (CAM: Camry, Camry Solara -> Camry).
                  Three letters count only when they are the only model word (TOY/CAM, not PRE RUNNER).
       fuzzy      a word of five or more letters, no digits, with the same first letter as exactly one
                  all-letter model name and within one edit of it, or two with at most one changed
                  letter from seven letters; an adjacent swap is one edit (CORROLLA, PRUIS). Never when
                  the word begins some model name (NINJA is not Ninja 7), and CHEVELLE is not Chevette.
     A generic word (VAN, TRUCK, SEDAN, UNK, a colour) is not a model.

What it cannot do: tell a model the officer abbreviated beyond recognition from one that vPIC does not
list. Both come back with model None and a reason; vehicle-fields.py then falls back to a body-type weight.
"""

import csv
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ALIASES = os.path.join(HERE, "make-aliases.csv")
MODEL_ALIASES = os.path.join(HERE, "model-aliases.csv")

# A make needs this many rows spelled exactly before a misspelling may be read as it.
COMMON_MAKE_ROWS = 50

SEP = re.compile(r"\s*[/|,;\\]+\s*")
# Colours and colour abbreviations officers write after the model. Stripped before a model is matched.
COLOURS = set("""
BLACK BLK BLAC BLCK BK BL WHITE WHT WHI WHIT WH WT GREY GRAY GRY GRE GR SILVER SLV SIL SILV SLVR SI
RED RD BLUE BLU BLE BU GREEN GRN GN TAN BEIGE BGE BEI BRONZE BRZ GOLD GLD GOL MAROON MAR MRN BURGUNDY
BURGANDY BURG BUR BRN BROWN BRO BRWN ORANGE ORG ONG ORN YELLOW YEL YLW PURPLE PUR PRP PLE PINK PNK TEAL
NAVY CHARCOAL CHAR CREAM CRM CHAMPAGNE CHAMP COPPER CPR BRONZ PEARL SILVR MAGENTA TURQUOISE TURQ
BLA GRA SILVE SLIVER GREE GRAYISH LIGHT LT DARK DK DRK METALLIC MET MULTI MULTICOLOR MULTICOLORED CAMO OLIVE LAVENDER INDIGO VIOLET
""".split())
# Words that name no make or model.
GENERIC = set("""
UNK UNKN UNKNOWN UNKOWN UNKWN NONE NA N A NOTSTATED OTHER OTH MISC UNKNOWNMAKE UNKNOWNMODEL NO NOT STATED
VEH VEHICLE AUTO CAR SEDAN SDN 2D 4D 2DR 4DR 4DSD 2DSD COUPE CPE HATCH HATCHBACK WAGON WGN CONV CONVERTIBLE
SUV VAN MINIVAN TRUCK TRK PICKUP PICK UP PU BUS MC MOTORCYCLE MOTO MOTORBIKE SCOOTER MOPED BICYCLE BIKE
EBIKE TRAILER CARGO PASSENGER PASS COMMERCIAL TAXI CAB LIMO PARKED HIT AND RUN HITANDRUN
LLC INC CORP CO COMPANY MOTORS MOTOR MFG INDUSTRIES CUSTOM PK CLASS SERIES
""".split())
# Words dropped from the model words wherever they stand: a performance line, not a model ("AMG C63" is a C-Class).
SKIP_WORDS = {"AMG"}
# vPIC makes whose names are also ordinary words or bicycle brands; read as a make only through
# make-aliases.csv. Found in the 2026-11-25 self-check (TITAN BIKE, RHINO/MTN GORGE, COLUMBIA/CROSSTRAIN).
NOT_MAKES = {"TITAN", "RHINO", "WOLF", "BOOM", "ALIEN", "EPIC", "STAR", "RIDLEY", "DIAMONBACK", "COLUMBIA",
             "STINGRAY", "FUSION", "VENOM", "WESTERN", "GOOGLE", "ECO", "USA", "VOLT", "FX", "PURE", "ROVER",
             "STREETCAR", "MANGOSTEEN", "INTI", "ZAP", "OBX", "TROLLEY"}
# Model names vPIC lists that are body words, not models; never matched.
GENERIC_MODELS = {"VAN", "CARGOVAN", "PICKUP", "TRUCK", "BUS", "SEDAN", "WAGON", "COUPE", "CAB", "CHASSIS",
                  "CABCHASSIS", "MOTORHOME", "OTHER", "UNKNOWN", "TRAILER", "CONVERTIBLE", "SUV", "MC"}


def squash(s):
    """Letters and digits only, upper case: the key two spellings of one name share."""
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def clean_model_name(name):
    """vPIC's model name without a parenthesised note: "Prius Prime (PHEV)" -> "Prius Prime"."""
    return re.sub(r"\s*\([^)]*\)", "", name).strip()


def edits(a, b):
    """(edits, substitutions) to turn a into b, an adjacent swap counting as one edit and no substitution.

    Optimal string alignment, minimising edits first and substitutions second. A dropped, doubled or
    swapped letter is the usual typo; a changed letter is as often a different name (SPART is not SMART,
    CHEVELLE is not CHEVETTE), so the fuzzy rules below limit substitutions separately."""
    n, m = len(a), len(b)
    d = [[(0, 0)] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = (i, 0)
    for j in range(m + 1):
        d[0][j] = (j, 0)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            same = a[i - 1] == b[j - 1]
            opts = [(d[i - 1][j][0] + 1, d[i - 1][j][1]), (d[i][j - 1][0] + 1, d[i][j - 1][1]),
                    (d[i - 1][j - 1][0] + (0 if same else 1), d[i - 1][j - 1][1] + (0 if same else 1))]
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                opts.append((d[i - 2][j - 2][0] + 1, d[i - 2][j - 2][1]))
            d[i][j] = min(opts)
    return d[n][m]


def near_make(word, name):
    """A misspelt make: same first letter, one edit, and no changed letter in a five-letter word."""
    if len(word) < 5 or word[0] != name[0] or abs(len(word) - len(name)) > 1:
        return False
    e, subs = edits(word, name)
    return e <= 1 and (len(word) > 5 or subs == 0)


def near_model(word, name):
    """A misspelt model: same first letter; one edit, or two with at most one changed letter from seven letters."""
    if len(word) < 5 or word[0] != name[0] or abs(len(word) - len(name)) > 2:
        return False
    e, subs = edits(word, name)
    return e <= 1 or (len(word) >= 7 and e <= 2 and subs <= 1)


class Parse(object):
    __slots__ = ("make", "model", "make_how", "model_how", "reason")

    def __init__(self, make=None, model=None, make_how=None, model_how=None, reason=None):
        self.make, self.model, self.make_how, self.model_how, self.reason = make, model, make_how, model_how, reason

    def __repr__(self):
        return "Parse(%r, %r, %s, %s, %r)" % (self.make, self.model, self.make_how, self.model_how, self.reason)

    def __eq__(self, other):
        return all(getattr(self, k) == getattr(other, k) for k in self.__slots__)


def load_aliases(path=ALIASES):
    """{squashed alias: (make, model prefix or None)} from make-aliases.csv."""
    out = {}
    with open(path, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            out[squash(r["alias"])] = (r["make"].strip().upper(), (r.get("model_prefix") or "").strip() or None)
    return out


def load_model_aliases(path=MODEL_ALIASES):
    """{(make, squashed alias): model} from model-aliases.csv: names officers use that vPIC spells otherwise."""
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            out[(r["make"].strip().upper(), squash(r["alias"]))] = r["model"].strip()
    return out


def normalise(raw):
    """The raw string as a list of segments, each a list of upper-case words; [] when it says nothing."""
    s = (raw or "").upper().replace(" ", " ").strip()
    s = re.sub(r"\s+-\s+", "/", s)          # "FORD - F150" is two segments
    s = re.sub(r"\([^)]*\)", " ", s)      # "DUCATI (MOTORCYCLE)", "AMERICAN MOTORS (AMC)"
    s = re.sub(r"[.]", " ", s)
    segs = []
    for part in SEP.split(s):
        words = [w for w in re.split(r"\s+", part.strip()) if w and w not in {"-", "--"}]
        if words:
            segs.append(words)
    return segs


def lookup_key(raw):
    """The string as the parser reads it: colours dropped, segments joined by "/", words by one space.

    Two raw strings with one key always parse alike, so the committed lookup (make-model-lookup.csv) is
    keyed by it: "Toyota/Highlander/Silver" and "TOYOTA / HIGHLANDER / GRY" are both "TOYOTA/HIGHLANDER".
    """
    segs = []
    for seg in normalise(raw):
        words = [w for w in seg if squash(w) and squash(w) not in COLOURS]
        if words:
            segs.append(" ".join(words))
    return "/".join(segs)


class Matcher(object):
    """Parses raw strings against vPIC makes (a {NAME: types} dict) and a models_for(make) -> set callable."""

    def __init__(self, vpic_makes, models_for, common_makes=(), aliases=None, model_aliases=None):
        self.aliases = load_aliases() if aliases is None else aliases
        self.model_aliases = load_model_aliases() if model_aliases is None else model_aliases
        self.makes = {}
        for name in sorted(vpic_makes):
            types = vpic_makes[name] if isinstance(vpic_makes, dict) else None
            # vPIC's low speed vehicle makers are mostly golf-cart and e-scooter firms with names like
            # ROVER and VOLT; a make it lists only as a low speed vehicle needs an alias.
            if types is not None and set(types) <= {"low speed vehicle (lsv)"}:
                continue
            k = squash(name)
            if k and k not in GENERIC and k not in COLOURS and k not in NOT_MAKES:
                self.makes.setdefault(k, name)
        self.common = sorted({squash(m) for m in common_makes} | {squash(a[0]) for a in self.aliases.values()})
        self.models_for = models_for
        self._index = {}

    # -- makes ---------------------------------------------------------------------------------------
    def _make_of(self, key):
        if key in self.aliases:
            return self.aliases[key] + ("alias",)
        if key in self.makes:
            return self.makes[key], None, "vpic"
        return None

    def find_make(self, words):
        """(make, model prefix, how, words used) for the leading words, or None."""
        for n in (3, 2, 1):
            if len(words) >= n:
                hit = self._make_of(squash("".join(words[:n])))
                if hit:
                    return hit[0], hit[1], hit[2], n
        w = squash(words[0]) if words else ""
        if len(w) >= 5 and w not in GENERIC and w not in COLOURS:
            near = [c for c in self.common if near_make(w, c)]
            if len(near) == 1:
                hit = self._make_of(near[0])
                if hit:
                    return hit[0], hit[1], "fuzzy", 1
        return None

    # -- models --------------------------------------------------------------------------------------
    def index(self, make):
        """{squashed model: clean model} for one make, built once."""
        if make not in self._index:
            idx = {}
            for name in sorted(self.models_for(make)):
                clean = clean_model_name(name)
                for k in {squash(clean), squash(name)}:
                    if k and k not in GENERIC_MODELS:
                        idx.setdefault(k, clean)
                # "Scion xB" is also reachable as "xB" once the make alias put "Scion" in front.
            for (mk, alias), model in self.model_aliases.items():
                if mk == make:
                    idx[alias] = model
            self._index[make] = idx
        return self._index[make]

    def _series(self, key, idx):
        m = re.match(r"^([A-Z]{1,3})(\d{2,4})([A-Z]{0,3})$", key)
        if m:
            letters = m.group(1)
            for cand in (letters + "CLASS", letters):
                if cand in idx and cand not in GENERIC_MODELS:
                    return idx[cand]
        if re.match(r"^\d{3}$", key):
            hits = sorted({v for k, v in idx.items() if re.match(r"^%s[A-Z]{1,3}$" % key, k)})
            if len(hits) == 1:
                return hits[0]
            if key + "I" in idx:
                return idx[key + "I"]
        return None

    def find_model(self, make, words, prefix=None):
        """(model, how) from the words after the make, or (None, reason)."""
        idx = self.index(make)
        words = [w for w in words if squash(w) and squash(w) not in COLOURS and squash(w) not in SKIP_WORDS]
        # "MERCEDEZ BENZ ML350": a second word of the make's own name is not the model.
        while words and squash(words[0]) not in idx and (
                squash(words[0]) in self.aliases and self.aliases[squash(words[0])][0] == make
                or squash(words[0]) in {squash(x) for x in re.split(r"[\s-]+", make)}
                or squash(words[0]) in self.common):
            # ...and nor is another make's name ("VESPA/PIAGGIO", "PIAGGIO/VESPA"): Vespa is Piaggio's line.
            words = words[1:]
        if prefix:
            for n in (3, 2, 1):
                if len(words) >= n:
                    k = squash(prefix + "".join(words[:n]))
                    if k in idx:
                        return idx[k], "exact"
            if squash(prefix) in idx:
                return idx[squash(prefix)], "exact"
        if not words:
            return None, "no model named"
        if squash(words[0]) in GENERIC:
            return None, "no model named"
        for n in (3, 2, 1):
            if len(words) >= n:
                k = squash("".join(words[:n]))
                if k in idx:
                    return idx[k], "exact"
        first = squash(words[0])
        s = self._series(first, idx)
        if s:
            return s, "series"
        meaningful = [w for w in words if squash(w) not in GENERIC]
        extended = sorted({v for k, v in idx.items() if k.startswith(first)}, key=lambda v: (len(squash(v)), v))
        # A three-letter abbreviation counts only when it is the only model word ("TOY/CAM"), so "PRE RUNNER"
        # is not read as Previa and "CAM OR COR" is not read as Camry.
        if first.isalpha() and (len(first) >= 4 or (len(first) == 3 and len(meaningful) == 1)):
            # One model, or one model that every other hit merely extends (CAM: Camry, Camry Solara).
            if extended and all(squash(h).startswith(squash(extended[0])) for h in extended):
                return extended[0], "abbrev"
        if extended:
            return None, "model abbreviation matches more than one vPIC model"
        # Misspellings are read only in words of letters: in a code like YW125 or CMX500 one character is
        # a different model, not a typo.
        if len(first) >= 5 and first.isalpha():
            near = sorted({v for k, v in idx.items() if len(k) >= 4 and k.isalpha() and near_model(first, k)})
            if len(near) == 1:
                return near[0], "fuzzy"
            if len(near) > 1:
                return None, "model spelling matches more than one vPIC model"
        return None, "model not in vPIC for this make"

    # -- the whole string ----------------------------------------------------------------------------
    def parse(self, raw):
        """The Parse of a raw string; the same as parse_key(lookup_key(raw))."""
        return self.parse_key(lookup_key(raw))

    def parse_key(self, key):
        segs = [seg.split(" ") for seg in key.split("/") if seg]
        words = [w for seg in segs for w in seg]
        if not words or all(squash(w) in GENERIC for w in words):
            return Parse(reason="no make named")
        # A leading generic word ("OTHER/HONDA") is skipped, unless it is a make ("AUTO CAR" is Autocar).
        while len(segs) > 1 and all(squash(w) in GENERIC for w in segs[0]) and not self.find_make(segs[0]):
            segs = segs[1:]
        # The make is read from the first segment when the officer used separators, so a model in the
        # second segment is never taken for part of the make.
        first = segs[0]
        hit = self.find_make(first)
        if not hit:
            return Parse(reason="make not recognised")
        make, prefix, how, used = hit
        rest = first[used:] + [w for seg in segs[1:] for w in seg]
        model, mhow = self.find_model(make, rest, prefix)
        if model is None:
            return Parse(make=make, make_how=how, reason=mhow)
        return Parse(make=make, model=model, make_how=how, model_how=mhow)
