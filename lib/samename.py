"""One fuzzy rule for "the same project under nearly the same name".

Used by pipeline/transportation-audit.py (A1, A3, B1, B3) and by
tools/projects/coordination-projects.py when it pairs an SFMTA project with Public
Works' page for it, so the pipeline and the audit cannot disagree about which
two names are one project.
"""

import re


STOP = {"the", "and", "of", "a", "an", "to", "on", "at", "in", "for", "from", "&", "phase", "project", "projects",
        "program", "programme", "improvement", "improvements", "pw", "sfmta", "mta", "sf", "joint", "lead", "w"}
ABBR = {"st": "street", "ave": "avenue", "av": "avenue", "blvd": "boulevard", "dr": "drive", "rd": "road",
        "upgrades": "upgrade", "streets": "street", "lanes": "lane", "rehab": "rehabilitation"}


def name_tokens(s):
    s = (s or "").lower().replace("–", " ").replace("—", " ")
    words = [ABBR.get(w, w) for w in re.findall(r"[a-z0-9]+", s)]
    return {w for w in words if w not in STOP}


# Words every street project shares. Two names match on what is left: the
# street, the place, the contract number.
# The kind of work (sewer, pavement) stays distinctive, so a repave and a
# safety project on the same street do not match.
STREET_WORDS = {"street", "avenue", "boulevard", "drive", "road", "way"}
KIND = {"pavement", "renovation", "sewer", "replacement", "water", "main", "rehabilitation", "installation"}
GENERIC = STREET_WORDS | {
    "quick", "build", "slow", "safety", "transit", "streetscape", "upgrade", "various", "locations", "location",
    "traffic", "calming", "signal", "signals", "new", "pedestrian", "bike", "bikeway", "lane", "lanes", "no", "rapid",
    "muni", "forward", "access", "connections", "corridor", "plan", "study", "implementation", "intersection",
    "multimodal", "vision", "zero", "enhancement", "infrastructure", "accessibility"}


def same_name(a, b):
    """Same or nearly the same project name, also with a subtitle after a colon dropped ("J Church …: San Jose Avenue")."""
    if _same_name(a, b):
        return True
    a2, b2 = (a or "").split(":")[0], (b or "").split(":")[0]
    return (a2, b2) != (a, b) and _same_name(a2, b2)


def _same_name(a, b):
    """Same or nearly the same project name.

    The distinctive words (street, place, contract number, kind of work) must
    be the same, or three or more of one name's must sit inside the other's.
    When they are the same and only one or two, the two names must also share
    a word for the kind of project (quick-build, slow street, streetscape), so
    "Divisadero Intersection Improvements" is not "Divisadero Streetscape".
    """
    ta, tb = name_tokens(a), name_tokens(b)
    if ta and ta == tb:
        return True
    # Street, avenue and park stay distinctive: Golden Gate Park is not Golden Gate Avenue.
    A, B = ta - (GENERIC - STREET_WORDS), tb - (GENERIC - STREET_WORDS)
    if not (A - STREET_WORDS) or not (B - STREET_WORDS):
        return ta == tb and bool(ta)
    if A == B:
        return len(A - STREET_WORDS) >= 3 or bool((ta & tb & GENERIC) - STREET_WORDS)
    small, big = (A, B) if len(A) <= len(B) else (B, A)
    # One name inside the other: at least two words beyond the kind of work, or
    # a contract number; no more extra words than it shares; and no kind of
    # work in the longer name that the shorter does not name (a repave on San
    # Bruno Avenue is not the San Bruno Avenue multimodal project).
    core = small - KIND - STREET_WORDS
    extra = big - small
    return (small <= big and (len(core) >= 2 or any(w.isdigit() for w in core)) and len(extra) <= len(small)
            and not (extra & KIND and not small & KIND) and not any(w.isdigit() for w in extra))
