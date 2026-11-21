"""The one definition of Muni's frequent and infrequent service: SFMTA's line types.

Bryan, 2026-11-17, answering "Split frequent and infrequent Muni by SFMTA's line type?": "SFMTA's
line types". Infrequent is SFMTA's Connector lines and its Owl service, judged by on time (SFMTA's window, 1 minute
early to 4 late); every other line is frequent, judged by TfL's excess wait, in every hour it runs. That follows the
city's scorecard: "Connector and Owl routes are not measured by headway adherence" (sf.gov, 2024 Transit and Street
Safety Scorecard, Percentage of evenly spaced Muni arrivals). This replaces the 2026-11-09 rule that switched per stop
and hour at a bus every 10 minutes.

INFREQUENT holds the GTFS route ids, raw and as the scripts rename them (L-OWL is LOWL, N-OWL is NOWL), of every line
data/muni-ewt/line_types.csv marks infrequent: the twelve Connector lines in SFMTA's ridership-by-route file and the
Owl lines (90, 91, the L Owl and N Owl buses). The pipeline's hours are 5 am to 11 pm, so it sees only the Owl lines'
edge hours (5 to 7 am, 9 to 11 pm), and the owl trips that other lines run between 1 and 5 am are outside it entirely.
Cable cars, the historic streetcars and SFMTA's Specialized express lines count as frequent, since only Connector and
Owl are left out of SFMTA's headway measure. The list is written out here, not read from the CSV, because the VM runs
these scripts without the repo's data; site_data.py fails when the two disagree or when SFMTA's ridership file names a
Connector or Owl line missing from it.
Imported by every script that makes the split (ewt_aggregate.py, ewt_stops.py, ewt_daily.py, ewt_stop_period.py,
ontime_month.py, ewt_sched_month.py, site_data.py), and hashed into post_all.sh's stamps, so changing it here reruns
all of them.
"""
CONNECTOR = ("25", "35", "36", "37", "39", "52", "55", "56", "57", "58", "66", "67")
OWL = ("90", "91", "L-OWL", "LOWL", "N-OWL", "NOWL")
INFREQUENT = CONNECTOR + OWL


def is_frequent(route):
    """True for a line judged by excess wait; route is a GTFS id, raw or renamed."""
    return route not in INFREQUENT


def frequent_sql(p=""):
    """SQL true for a row of a frequent line; p is a table prefix such as "h."; the row's route is the raw or renamed GTFS id."""
    return f"({p}route NOT IN ({', '.join(repr(r) for r in INFREQUENT)}))"
