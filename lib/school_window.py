"""Which kids hurt count as hurt on the way to or from school: one definition for every count of kids hurt near schools.

Bryan, 2026-10-21, on the public comment: "Let's please keep it to school hours (6AM to 6PM) on weekdays during the
school year. And make the school year from August to end of May. And please use this same definition throughout the
whole post".

So a victim in DataSF nwes-mmgh (one row per person injured or killed) counts when they were:
  - aged 5 to 18 (AGE_MIN to AGE_MAX),
  - injured or killed, so any degree but "No Injury",
  - hurt on a weekday, Monday to Friday,
  - from 6 am up to 6 pm (FIRST_HOUR <= hour < END_HOUR, by the report's collision_time),
  - in the school year, August 1 to May 31. June and July are out.

A school year is labelled by the August it starts in: "2021-22" runs 2021-08-01 to 2022-05-31. A date in June or July
has no school year, so school_year() and school_year_start() return None for it.

Used by tools/school-trips/school-calm-priority.py, tools/school-trips/school-kids-hurt.py, tools/school-trips/school-hurt-maps.py,
tools/school-trips/school-injury-points.py and tools/street-safety/injury-map.py. Holidays and school breaks
inside August to May stay in: the dataset carries no school calendar, and tools/school-trips/school-hour-crashes.py is the one
analysis that reads SFUSD's calendar day by day.
"""
import datetime
import re

AGE_MIN, AGE_MAX = 5, 18
FIRST_HOUR, END_HOUR = 6, 18          # 6 am up to 6 pm
FIRST_MONTH, LAST_MONTH = 8, 5        # August to May
RULE = "kids 5 to 18 injured or killed on a weekday, 6 am to 6 pm, August 1 to May 31"


def school_year_start(d):
    """The year of the August a date's school year starts in, or None in June and July."""
    if d.month >= FIRST_MONTH:
        return d.year
    if d.month <= LAST_MONTH:
        return d.year - 1
    return None


def school_year(d):
    """'2021-22' for 2021-08-01 to 2022-05-31; None in June and July."""
    y = school_year_start(d)
    return None if y is None else label(y)


def label(y):
    """The school year starting in August of y: 2021 -> '2021-22'."""
    return "%d-%02d" % (y, (y + 1) % 100)


def years(first, last):
    """Labels of the school years starting in August of first to last, inclusive: years(2021, 2024) is 2021-22 to 2024-25."""
    return [label(y) for y in range(first, last + 1)]


def in_window(d, hour):
    """True when a date and hour fall on a school-year weekday, 6 am up to 6 pm. An unknown hour (None) is out."""
    return (hour is not None and FIRST_HOUR <= hour < END_HOUR and d.weekday() < 5
            and school_year_start(d) is not None)


def kid_age(v):
    """The victim's age when it is 5 to 18, else None."""
    try:
        age = int(float(v.get("victim_age")))
    except (TypeError, ValueError):
        return None
    return age if AGE_MIN <= age <= AGE_MAX else None


def kid_hurt(v):
    """For an nwes-mmgh victim row, {date, hour, minute, age, year} when the victim counts, else None.

    Needs the row's victim_degree_of_injury, victim_age, collision_datetime and collision_time. A row with no
    collision_time, or one not in HH:MM form, is out: a missing time leaves collision_datetime at 00:00, a fill and not
    midnight. The location is left to the caller, which counts rows without one."""
    if v.get("victim_degree_of_injury") in (None, "No Injury"):
        return None
    age = kid_age(v)
    dts, tm = v.get("collision_datetime") or "", v.get("collision_time") or ""
    if age is None or not dts or not re.match(r"^\d\d?:\d\d", tm):
        return None
    hh, mm = tm.split(":")[:2]
    d, h = datetime.date.fromisoformat(dts[:10]), int(hh)
    if not in_window(d, h):
        return None
    return {"date": d, "hour": h, "minute": int(mm[:2]), "age": age, "year": school_year(d)}


def _selftest():
    D = datetime.date
    assert school_year(D(2021, 8, 1)) == "2021-22" and school_year(D(2022, 5, 31)) == "2021-22"
    assert school_year(D(2022, 6, 1)) is None and school_year(D(2022, 7, 31)) is None
    assert years(2021, 2024) == ["2021-22", "2022-23", "2023-24", "2024-25"]
    assert in_window(D(2023, 3, 1), 6) and not in_window(D(2023, 3, 1), 18) and not in_window(D(2023, 3, 1), 5)
    assert not in_window(D(2023, 3, 4), 12), "a Saturday"
    assert not in_window(D(2023, 6, 1), 12) and not in_window(D(2023, 3, 1), None)
    row = {"victim_degree_of_injury": "Complaint of Pain", "victim_age": "12", "collision_datetime": "2023-03-01T07:45:00",
           "collision_time": "07:45"}
    assert kid_hurt(row) == {"date": D(2023, 3, 1), "hour": 7, "minute": 45, "age": 12, "year": "2022-23"}
    assert kid_hurt(dict(row, collision_time="7:45:00"))["hour"] == 7 and kid_hurt(dict(row, victim_age="12.0"))["age"] == 12
    assert kid_hurt(dict(row, victim_age="19")) is None and kid_hurt(dict(row, victim_degree_of_injury="No Injury")) is None
    assert kid_hurt(dict(row, collision_time=None)) is None and kid_hurt(dict(row, collision_datetime="2023-06-02T07:45:00")) is None


_selftest()
