"""The months an early, mid or late season names ("Late spring 2026"), defined once.

Bryan, 2026-09-29, on the Noe Slow Street page, whose timeline says "Late
spring 2026" and whose row showed April 2026: the page "literally does say it
will be done 'Late spring 2026'". A season with a qualifier names part of the
season, and the date read from it is that part's months, not the season's
first month.

A qualified season is read over the season's three months, starting where
the scripts already start a season (winter January, spring April, summer
July, fall October): early is the first two, mid the middle one, late the
last two. So "Late spring" is May to June, "Early fall" October to November,
"Mid-summer" August. A season with no qualifier keeps the months each script
already gives it.

Used by tools/projects/coordination-projects.py (season_date, stage_end),
tools/projects/project-record.py (_season_date) and tools/projects/sfmta-page-dates.py
(read_span).
"""

import re

SEASON_START = {"winter": 1, "spring": 4, "summer": 7, "fall": 10, "autumn": 10}
PART = {"early": (0, 1), "mid": (1, 1), "late": (1, 2)}  # month offsets into the season's three months

QUALIFIED = re.compile(r"\b(early|mid|late)[- ]*(winter|spring|summer|fall|autumn)\b", re.I)


def months(qualifier, season):
    """(first month, last month) of an early, mid or late season: ("late", "spring") -> (5, 6)."""
    a, b = PART[qualifier.lower()]
    s = SEASON_START[season.lower()]
    return s + a, s + b


def first_qualified(text):
    """(first, last) month of the first qualified season in `text`, or None."""
    m = QUALIFIED.search(text or "")
    return months(m.group(1), m.group(2)) if m else None


def last_qualified(text):
    """(first, last) month of the last qualified season in `text`, or None."""
    found = QUALIFIED.findall(text or "")
    return months(*found[-1]) if found else None
