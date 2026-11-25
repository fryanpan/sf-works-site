"""Curb weight in pounds for a clean make, model and model year, from Transport Canada's specifications as vPIC serves them.

    from vehicle_weight import Weights
    w = Weights(specs_for=vpic.canadian_specs, vocab_for=lambda make: {"Camry": {"Camry"}, "Corolla Matrix": {"MATRIX"}})
    w.model_year("TOYOTA", "Camry", 2020)        # 3363.4, the mean of that year's Camry trims
    w.window("TOYOTA", "Camry", range(2011, 2021))  # (3301.2, 10): mean of the yearly means, years with data

WHAT A TRIM IS. GetCanadianVehicleSpecifications answers one make and model year with every trim Transport
Canada measured, named like "CAMRY 4DR SEDAN LE" or "3 SERIES 328i xDRIVE 4DR SEDAN AWD", each with a
curb weight `CW`. There is no separate model field, so each trim is assigned to one model of the make:

  1. prefix   the trim starts with the model's words ("CAMRY ...", "C-CLASS ...", "MODEL 3 ..."), or with
              its squashed letters ("CR-V" and "CRV"), or, for a model of three letters or fewer, with
              them followed by a digit ("RX350 ..." is an RX).
              A Mercedes class also matches a trim that starts with its letters ("CLS 450 ..." is a CLS-Class).
  2. within   the model's words appear whole inside the trim ("3 SERIES 328i ..." is a 328i,
              "2500 EXPRESS CARGO VAN" is an Express). Only for models of three characters or more with
              at least one letter, so a bare number such as Mercedes' 1980s "300" takes no later trims.

A trim counts for the longest model that matches by prefix, so "PRIUS C 5DR" is a Prius C and not a
Prius, and also for each model that matches within, so "3 SERIES 328i ..." is both a 3 Series and a 328i.

THE WEIGHT of a model in a year is the plain mean of its trims' curb weights: every trim counts once,
because nothing public says how many of each were sold. It is the weight of the car empty, with fluids
and without people or cargo. A trim far off its neighbours is dropped as a data-entry error (model_year).

What Transport Canada does not cover: motorcycles, buses, heavy trucks, and a model year or model not
sold in Canada. Those come back None and the caller falls back or leaves the weight empty.
"""

import re

OUTLIER_RATIO = 1.6


def norm_words(s):
    """Upper case, hyphens and slashes as spaces, other punctuation dropped, single spaces."""
    s = re.sub(r"[-/]", " ", (s or "").upper())
    s = re.sub(r"[^A-Z0-9 ]", "", s)
    return " ".join(s.split())


def squash(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def match_kind(model, trim):
    """'prefix', 'within' or None: how the trim name `trim` names the model `model`."""
    m, t = norm_words(model), norm_words(trim)
    if not m or not t:
        return None
    if t == m or t.startswith(m + " "):
        return "prefix"
    words, sm = t.split(" "), squash(model)
    for k in (1, 2, 3):
        if squash("".join(words[:k])) == sm:
            return "prefix"
    if len(sm) <= 3 and sm.isalpha() and re.match(r"^%s\d" % re.escape(sm), words[0]):
        return "prefix"
    # "CLS 450 4MATIC" is a CLS-Class: a Mercedes class named by its letters alone.
    cls = re.match(r"^([A-Z]{1,3}) CLASS$", m)
    if cls and words[0] == cls.group(1):
        return "prefix"
    # Within: only names with a letter in them. A bare number (Mercedes' 1980s "300") would otherwise
    # take every "C 300" trim of later years.
    if len(sm) >= 3 and re.search(r"[A-Z]", sm) and (" " + m + " ") in (" " + t + " "):
        return "within"
    return None


def assign(trims, vocab):
    """{model: [curb weights]} for one make and year. `vocab` is {model: set of names it goes by}.

    A trim counts for the longest model it starts with, and also for every model named whole inside it
    that is not part of that longer name: "3 SERIES 328i 4DR" counts for both 3 Series and 328i, and
    "CITY EXPRESS VAN" for City Express but not for Express. A model's other names come from
    model-aliases.csv, so the Corolla Matrix also takes Transport Canada's "MATRIX ..." trims."""
    if not isinstance(vocab, dict):
        vocab = {m: {m} for m in vocab}
    out = {}
    for name, cw in trims:
        kinds = {}
        for m, names in vocab.items():
            got = {match_kind(n, name) for n in names | {m}}
            kinds[m] = "prefix" if "prefix" in got else "within" if "within" in got else None
        prefix = [m for m, k in kinds.items() if k == "prefix"]
        best = max(prefix, key=lambda m: (len(squash(m)), m)) if prefix else None
        hits = [best] if best else []
        for m, k in sorted(kinds.items()):
            if k == "within" and (best is None or (" " + norm_words(m) + " ") not in (" " + norm_words(best) + " ")):
                hits.append(m)
        for m in hits:
            out.setdefault(m, []).append(cw)
    return out


class Weights(object):
    def __init__(self, specs_for, vocab_for):
        self.specs_for, self.vocab_for = specs_for, vocab_for
        self._year = {}

    def by_model(self, make, year):
        key = (make, year)
        if key not in self._year:
            vocab = self.vocab_for(make)
            self._year[key] = assign(self.specs_for(make, year), vocab if isinstance(vocab, dict) else sorted(vocab))
        return self._year[key]

    def model_year(self, make, model, year):
        """Mean curb weight of the model's trims in that model year, or None.

        A trim more than OUTLIER_RATIO times off the median of the model's trims over the five model
        years around it is left out as a data-entry error: Transport Canada lists one Range Rover year
        at 10,935 lb against about 5,500 lb in every year beside it. Needs at least three trims to judge."""
        cws = self.by_model(make, year).get(model)
        if not cws:
            return None
        ref = sorted(w for y in range(year - 2, year + 3) for w in self.by_model(make, y).get(model, ()))
        if len(ref) >= 3:
            mid = ref[len(ref) // 2]
            cws = [w for w in cws if mid / OUTLIER_RATIO <= w <= mid * OUTLIER_RATIO]
        return sum(cws) / len(cws) if cws else None

    def window(self, make, model, years):
        """(mean of the yearly means over `years` that have data, how many years had data), or (None, 0)."""
        vals = [w for w in (self.model_year(make, model, y) for y in sorted(set(years))) if w is not None]
        return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)
