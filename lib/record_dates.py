"""What counts as a city-body record dated before a project's start (audit criterion C4), defined once.

tools/projects/record-coverage.py (out/record-coverage/coverage.json) and
pipeline/transportation-audit.py (C4) both count projects with such a record.
They used to carry a rule each, one "on or before" and one "before", and
reported 75 and 74 of the same 220 projects. Both now call this module.

The rule: a record counts when a city body made it (not the project's own
web page), the matcher graded it as the project's own (exact, strong or
probable), and its date is earlier than the start at the coarser precision of
the two. A start published as "2022-10" and a Commission award of 2022-10-21
are the same month, and nothing in either says which came first, so that
record is not counted as before the start.
"""

TRUSTED = frozenset({"exact", "strong", "probable"})
OWN_PAGE = "listed on this project's own page"
# Every city body tools/projects/project-record.py attaches records from (its MIRRORS).
CITY_KINDS = frozenset({"hearing", "board", "supervisors", "sfpuc", "pwc", "pwdelegated", "sfcta", "recpark"})


def before_start(rec_date, start):
    """True when a record's date (YYYY, YYYY-MM or YYYY-MM-DD) is earlier than a start of any of those precisions."""
    if not rec_date or not start:
        return False
    n = min(len(rec_date), len(start))
    return rec_date[:n] < start[:n]


def is_city_record(r):
    """A record a city body made and the matcher counts as the project's own."""
    return r.get("kind") in CITY_KINDS and r.get("relation") != OWN_PAGE and r.get("grade") in TRUSTED


def records_before_start(p):
    """A project's city-body records dated before its start (empty when it has no start)."""
    return [r for r in p.get("records") or () if is_city_record(r) and before_start(r.get("date"), p.get("start"))]
