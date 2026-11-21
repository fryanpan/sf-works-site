#!/usr/bin/env python3
"""Read San Francisco street names out of the city's own prose.

Every record this repo joins to a project — an engineering hearing order, an
SFMTA Board item, a Board of Supervisors ordinance — names its streets in a
sentence rather than a field. One parser reads all of them, because a second
implementation is a second set of misses and nothing would say the two
disagreed.

    from streetnames import streets, streets_in_order

`streets_in_order` keeps the order, and the order carries the meaning: these
records are written corridor-first, so the first name is the street being
legislated and the rest are the extent's cross streets.
"""

import re

# Street suffixes as San Francisco writes them, long form to the short form the
# CNN centreline file uses. Order matters: the regex tries the longest first, so
# "Avenue" is not matched as "Ave" with "nue" left over.
SUFFIX = {
    "street": "st", "st": "st",
    "avenue": "ave", "ave": "ave", "av": "ave",
    "boulevard": "blvd", "blvd": "blvd",
    "drive": "dr", "dr": "dr",
    "road": "rd", "rd": "rd",
    "way": "way", "wy": "way",
    "place": "pl", "pl": "pl",
    "court": "ct", "ct": "ct",
    "lane": "ln", "ln": "ln",
    "terrace": "ter", "ter": "ter",
    "alley": "aly", "aly": "aly",
    "circle": "cir", "cir": "cir",
    "highway": "hwy", "hwy": "hwy",
    "plaza": "plz", "plz": "plz",
    "parkway": "pkwy", "pkwy": "pkwy",
    "embarcadero": "embarcadero",
}
SUFFIX_RE = "|".join(sorted(SUFFIX, key=len, reverse=True))

# A street name is found by locating its SUFFIX and walking BACKWARDS, because
# these sources put ALL-CAPS action text immediately in front of the name:
# "ESTABLISH – SIDEWALK BIKESHARE STATION Laguna Street". A forward match that
# allows up to three leading words reads that as "bikeshare station laguna st",
# and then nothing links. Walking back and stopping at the first word that is
# not part of a name gives "laguna st", and gives "laguna honda blvd" for
# "...CLASS IV BIKEWAY Laguna Honda Boulevard" — both correct.
SUFFIX_TOKEN = re.compile(r"\b(" + SUFFIX_RE + r")\b", re.IGNORECASE)
WORD = re.compile(r"[A-Za-z0-9'\-]+")
ORDINAL_NUM = re.compile(r"^[0-9]{1,3}(st|nd|rd|th)$", re.IGNORECASE)

# San Francisco writes a street address on a numbered street with a hyphen and
# no space: "1555-6th Street", "471-23rd Avenue". The hyphen makes that one
# token, which is neither an ordinal nor a word starting with a letter, so the
# walk stopped dead and the title produced no street at all — 11 of the 24
# misses the Board sweep's self-check reported on 2026-09-21. The house number
# is not part of the name, so it is dropped and the ordinal kept.
ADDRESS_ORDINAL = re.compile(r"^\d{2,5}-(\d{1,3}(?:st|nd|rd|th))$",
                             re.IGNORECASE)

# Words that sit in front of a suffix but are not part of the street name.
NOT_A_STREET = {
    "the", "of", "and", "no", "on", "to", "from", "at", "in", "a", "an",
    "supervisor", "district", "city", "traffic", "engineer", "board",
    "directors", "approval", "implementation", "one", "two", "both", "all",
    "side", "sides", "any", "time", "slow", "class", "establish", "rescind",
    "tow", "away", "stopping", "parking", "zone", "bikeway", "bikeshare",
    "station", "project", "quick", "build", "public", "hearing", "decision",
    "comments", "received", "item", "items", "bicycles", "bicycle", "bike",
    "except", "existing", "new", "proposed", "corridor", "improvement",
    "improvements", "safety", "between", "near", "along", "across", "this",
    "that", "each", "its", "feet", "foot", "limit", "minute", "hour", "am",
    "pm", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
    "sunday", "school", "bus", "loading", "passenger", "commercial", "red",
    "blue", "green", "yellow", "white", "metered", "meter", "disabled",
    "person", "motorcycle", "angled", "degree", "signal", "crosswalk",
    "crosswalks", "raised", "beacon", "flashing", "rapid", "rectanglar",
    "rectangular", "humps", "hump", "speed", "dead", "end", "left", "right",
    "turn", "only", "stop", "car", "share", "permitted", "residential",
    "permit", "area", "eligibility", "signs", "unmetered", "general",
    "short", "term", "dual", "use", "six", "wheel", "cable", "accessible",
    "north", "south", "east", "west",  # as a bare directional; see below
    "eastbound", "westbound", "northbound", "southbound",
    # A Board of Supervisors title is a sentence, not an order, so it puts a
    # different kind of word in front of a suffix: "making certain streets",
    # "the sidewalk width for Street Design", "Transportation Officials Urban
    # Street Design Guide". None of these is a San Francisco street name.
    "certain", "making", "additional", "emergency", "temporary", "major",
    "minor", "installing", "including", "urban", "state", "travel", "transit",
    "curbside", "for", "by", "bounded", "generally", "acres", "within",
    "under", "funded", "works", "officials", "agency", "transportation",
    "sidewalk", "width", "superior", "summary",
}
# ...except where a direction genuinely opens a street name. "North Point St"
# and "South Van Ness Ave" are real; "north side" is not, and "side" stops the
# walk before the direction is ever reached.
DIRECTION_OK = {"north point", "south van ness", "north view", "south hill"}

ORDINAL = {"first": "1st", "second": "2nd", "third": "3rd", "fourth": "4th",
           "fifth": "5th", "sixth": "6th", "seventh": "7th", "eighth": "8th",
           "ninth": "9th", "tenth": "10th", "eleventh": "11th",
           "twelfth": "12th"}


def _name_word(w, first):
    """Can this word be part of a street name, reading right to left?"""
    low = w.lower()
    if low in SUFFIX:
        return False          # a second suffix ends the name
    if ORDINAL_NUM.match(low) or low in ORDINAL:
        return True
    if not w[:1].isalpha():
        return False
    if w.isupper() and len(w) > 1:
        return False          # ALL-CAPS is action text in these sources
    if low in NOT_A_STREET:
        return False
    return True


def streets_in_order(text):
    """Street names in the order the text names them, de-duplicated.

    The order carries the meaning. These orders are written corridor-first —
    "Valencia Street, east side, from 175 feet south of 21st Street" — so the
    first name is the street being legislated and the rest are the extent's
    cross streets. Matching a project on a cross street alone links the Bayview
    Community Pathway to every project whose page mentions Third Street.
    """
    out = []
    if not text:
        return out
    for name, _ in _walk(text):
        if name not in out:
            out.append(name)
    return out


def streets(text):
    """Normalised street names in a blob of text, as a set."""
    return {name for name, _ in _walk(text)}


def corridors(text):
    """Street names the text legislates, with the ones it only addresses dropped.

    A Board of Supervisors title names a street for either of two reasons, and
    they mean opposite things for a link. "occupy portions of Presidio Avenue"
    is the street itself. "located at 2245 Post Street" is one building, and
    treating it as the corridor put a zoning district at one address beside a
    sewer job that runs the length of Post Street. The tell is a house number
    immediately in front of the name, which is how San Francisco writes an
    address and never how it names a street.
    """
    out = []
    for name, is_address in _walk(text):
        if not is_address and name not in out:
            out.append(name)
    return out


# A house number, including the range form San Francisco uses for a building
# that spans lots: "1523-1525 Franklin Street", "1301-1341 Evans Avenue".
HOUSE_NUMBER = re.compile(r"^\d{1,5}(-\d{1,5})?-?$")  # "548- 5th Street" splits as "548-"


# "Palou, Quesada, and Revere Avenues" and "17th and Church Streets" name two
# or more streets and write the suffix once, in the plural. Walking back from
# one suffix finds one name at most, so the list is first rewritten with the
# suffix on every member — "Palou Avenue, Quesada Avenue, and Revere Avenue".
# SFPUC contract titles are written this way almost every time.
PLURAL = {"streets": "Street", "avenues": "Avenue", "boulevards": "Boulevard",
          "roads": "Road", "drives": "Drive", "ways": "Way", "places": "Place",
          "lanes": "Lane", "courts": "Court", "terraces": "Terrace", "alleys": "Alley",
          "sts": "Street", "aves": "Avenue", "blvds": "Boulevard"}
# A member of the list: a capitalised word or ordinal that is not itself a suffix.
_NAME = r"(?!(?:" + SUFFIX_RE + "|" + "|".join(PLURAL) + r")\b)(?-i:[A-Z0-9])[\w'\-]*"
_LIST = re.compile(
    r"((?:" + _NAME + r"(?:\s+" + _NAME + r")?(?:\s+and)?,?\s+(?:and\s+)?){1,7}" + _NAME + r")\s+("
    + "|".join(PLURAL) + r")\b", re.IGNORECASE)


def _expand_plurals(text):
    def one(m):
        names = [n.strip() for n in re.split(r",\s*(?:and\s+)?|\s+and\s+", m.group(1)) if n.strip()]
        suffix = PLURAL[m.group(2).lower()]
        return ", ".join(f"{n} {suffix}" for n in names)
    return _LIST.sub(one, text)


def _walk(text):
    """(name, is_address) for every street name in the text, in order."""
    if not text:
        return
    text = _expand_plurals(text)
    words = []
    for m in WORD.finditer(text):
        w = m.group(0)
        addr = ADDRESS_ORDINAL.match(w)
        words.append(((addr.group(1) if addr else w), bool(addr)))
    for i, (w, _) in enumerate(words):
        if w.lower() not in SUFFIX:
            continue
        parts, first = [], i
        for j in range(i - 1, max(-1, i - 4), -1):
            if not _name_word(words[j][0], j == i - 1):
                # "North Point St" and "South Van Ness Ave" really do open with
                # a direction, so the walk takes one more word for those and
                # stops for "north side".
                w0 = words[j][0].lower()
                if parts and f"{w0} {' '.join(parts)}" in DIRECTION_OK:
                    parts.insert(0, w0)
                    first = j
                break
            parts.insert(0, words[j][0].lower())
            first = j
        while parts and parts[0] in ("of", "the"):
            parts.pop(0)
            first += 1
        if not parts:
            continue
        # "790 Pennsylvania Avenue" and "1555-6th Street" are both addresses;
        # the second arrives as one token and is flagged when it is split.
        is_address = words[first][1] or (
            first > 0 and HOUSE_NUMBER.match(words[first - 1][0]) is not None)
        parts = [ORDINAL.get(x, x) for x in parts]
        yield f"{' '.join(parts)} {SUFFIX[w.lower()]}", is_address
        if len(parts) > 1:
            # Also the last word alone, so "Van Ness Ave" in one source meets
            # "Ness Ave" in another.
            yield f"{parts[-1]} {SUFFIX[w.lower()]}", is_address
