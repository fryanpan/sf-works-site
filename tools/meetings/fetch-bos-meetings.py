#!/usr/bin/env python3
"""Mirror every Board of Supervisors and committee agenda item since 2019 from Legistar, full titles and actions, to data/bos-meetings/.

    tools/meetings/fetch-bos-meetings.py                  # since 2019-01-01; fetches only what is new or draft
    tools/meetings/fetch-bos-meetings.py --since 2026-01-01

tools/meetings/bos-street-records.py searches Legistar for 24 phrases and keeps
titles that name a street, so a file that names a project without one of
those phrases was never read. This reads every meeting's agenda grid instead:
each file heard, its full title, type, the action taken and its result, and
its LegislationDetail link.

scripts/legistar-meetings.py keeps a richer mirror of recent meetings (roll
calls, minutes text) in data/legistar/meetings/. This one is wider and
lighter: one request per meeting, no roll calls, so eight years of meetings
are a half-hour read. Both go through scripts/sf_legistar.py.

The Legistar web API (webapi.legistar.com/v1/sfgov) is no help here: its
events endpoint answers "'Agenda Draft Status' ... is not setup in settings"
and its matters stop in 2020 (both checked 2026-09-28).

The per-meeting files are about 30 MB for 2019 on, so data/bos-meetings/meetings/
is gitignored and data/bos-meetings/README.md says how to rebuild it. The
index, which records what was read and what is missing, is tracked.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import datetime as dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    import legistar.bills  # noqa: F401
except ImportError:
    _venv = os.path.expanduser(os.environ.get('CACHE', '~/.cache/sf-legistar')) + '/venv/bin/python'
    if os.path.exists(_venv) and not os.environ.get('SF_LEGISTAR_REEXEC'):
        os.environ['SF_LEGISTAR_REEXEC'] = '1'
        os.execv(_venv, [_venv, os.path.abspath(__file__)] + sys.argv[1:])
    raise SystemExit('cannot import legistar.bills; run scripts/refresh-legistar.sh once')
import sf_legistar  # noqa: E402
from lib.mirror import Mirror, settled, slug, summary  # noqa: E402

BODY = 'BOS and Committees'


def iso(mdy):
    return dt.datetime.strptime(mdy, '%m/%d/%Y').date().isoformat()


# Refresh: this year's and last year's calendars are listed every run. An
# earlier year is listed again only when the held index has a meeting of that
# year that is not final (a draft, not yet held, unreachable), or when
# --relist-all is given: a year whose every meeting is final has nothing left
# to change, and each year's calendar is about 1.5 MB.
FULL_YEARS = 2


def held_years(mirror, today):
    """{year: index rows} for past years whose every listed meeting is final on disk."""
    path = os.path.join(mirror.dir, 'index.json') if hasattr(mirror, 'dir') else None
    try:
        rows = json.load(open(path, encoding='utf-8'))['meetings']
    except (TypeError, FileNotFoundError, ValueError, KeyError):
        return {}
    by_year = {}
    for r in rows:
        by_year.setdefault(int(r['date'][:4]), []).append(r)
    out = {}
    for y, rs in by_year.items():
        if y > today.year - FULL_YEARS:
            continue
        if all(r.get('outcome') == 'empty' or (r.get('outcome') == 'mirrored' and mirror.is_final(r['date'], r['id']))
               for r in rs):
            out[y] = [{k: v for k, v in r.items() if k in ('date', 'id', 'committee', 'outcome', 'reason')} for r in rs]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--since', default='2019-01-01')
    ap.add_argument('--until', help='last year to read, e.g. 2022; default this year')
    ap.add_argument('--rpm', type=int, default=60, help='requests per minute to Legistar')
    ap.add_argument('--relist-all', action='store_true', help='list every year again, even ones all final')
    args = ap.parse_args()
    today = dt.date.today()
    s = sf_legistar._new(rpm=args.rpm)
    mirror = Mirror('bos-meetings', 'Board of Supervisors and its committees',
                    'https://sfgov.legistar.com/Calendar.aspx')
    listed, got, kept = [], 0, 0
    done = {} if args.relist_all else held_years(mirror, today)
    for year in range(int(args.since[:4]), int(args.until or today.year) + 1):
        if year in done:
            listed += done[year]
            kept += sum(1 for r in done[year] if r.get('outcome') == 'mirrored')
            print('  %d: %d meetings, every one final; calendar not re-read' % (year, len(done[year])))
            continue
        ms = list(s.meetings(BODY, str(year)))
        if not ms:
            raise SystemExit('FAIL: zero meetings listed for %s; a misspelled body returns nothing, not an error' % year)
        print('  %d: %d meetings listed' % (year, len(ms)))
        for m in sorted(ms, key=lambda m: iso(m['date'])):
            date = iso(m['date'])
            if date < args.since:
                continue
            mid = slug(m['body'])
            gid = re.search(r'ID=(\d+)', m.get('url') or '')
            if gid:
                mid += '-' + gid.group(1)
            row = {'date': date, 'id': mid, 'committee': m['body']}
            listed.append(row)
            if date > today.isoformat():
                row.update(outcome='no-agenda', reason='not yet held')
                continue
            if mirror.is_final(date, mid):
                row['outcome'] = 'mirrored'
                kept += 1
                continue
            if not m.get('url'):
                row.update(outcome='no-agenda', reason='Legistar links no meeting page')
                continue
            try:
                items = list(s.agenda(m['url']))
            except Exception as exc:
                row.update(outcome='unreachable', reason='%s: %s' % (type(exc).__name__, exc))
                continue
            if not items:
                row.update(outcome='empty', reason='meeting page parsed to no agenda items')
                continue
            has_minutes = bool(m.get('minutes_pdf'))
            rec = {'committee': m['body'], 'date': date, 'id': mid,
                   'status': 'final' if settled(date, has_minutes, today) else 'draft',
                   'sources': {'meeting': m['url'], 'agenda': m.get('agenda_pdf'), 'minutes': m.get('minutes_pdf')},
                   'fetched': today.isoformat(),
                   'items': [{'no': str(i + 1), 'file': it['file'], 'name': it['name'], 'type': it['type'],
                              'title': it['title'] or it['name'], 'decision': ' '.join(x for x in (it['action'], it['result']) if x) or None,
                              'status': it['status'], 'url': it['url']}
                             for i, it in enumerate(items)]}
            mirror.write(rec)
            row['outcome'] = 'mirrored'
            got += 1
            if got % 25 == 0:
                print('    %d fetched, latest %s %s' % (got, date, m['body']))
    idx = mirror.write_index(listed, args.since,
                             notes=['Agenda grids from sfgov.legistar.com MeetingDetail pages; no roll calls. '
                                    'The per-meeting files are gitignored; rebuild with scripts/fetch-bos-meetings.py.'])
    print('  fetched %d, already final %d' % (got, kept))
    print(summary(idx))


if __name__ == '__main__':
    main()
