#!/usr/bin/env python3
"""Read San Francisco's live legislative record out of Legistar's web interface.

Why this file exists
--------------------
The machine-readable mirror everyone reaches for first, `webapi.legistar.com/v1/sfgov`,
returns HTTP 200 with plausible records and is frozen at 2020-09-17 — its roster
contains none of the supervisors seated in 2025. No credential changes that. The
web interface at sfgov.legistar.com is current, so that is the only live route.

We use the community scraper (opencivicdata/python-legistar-scraper) rather than
writing our own, but San Francisco's Legistar has three quirks the community code
does not handle. All three are patched here:

1. SPONSOR ENUMERATION. The advanced search form has a "Sponsored by" combo box
   (`lstSponsoredBy`, 66 entries) that the community scraper never sets. Setting
   it, together with its Telerik ClientState twin, makes the results grid filter
   server-side. This matters because the PersonDetail page's "Sponsored
   Legislation" tab renders client-side and returns zero rows to a plain HTTP
   client — which is why an earlier attempt could cite an item count but not its
   contents.

2. DECOY LINKS ON ACTION DETAILS. In the per-file history grid, every "Action
   details" cell carries an `href` pointing back at the legislation page you are
   already on. The real URL is inside the `onclick`, as
   `radopen('HistoryDetail.aspx?ID=...')`. The community scraper reads the href,
   so it never reaches the vote table and reports zero roll calls on files that
   plainly passed. We parse the onclick instead.

3. A 100-ROW CAP ON FULL-TEXT SEARCH, WITH NO NOTICE. Legislation.aspx returns
   at most 100 results and prints nothing to say that more matched. "bicycle" in
   2025 answers 100; the same query split by matter type answers 108 across four
   of the nine types. `search` therefore splits by type whenever the plain result
   reaches the cap, and raises rather than returning a short list when even one
   type is still capped. Checked 2026-09-21.

Requires the community scraper on sys.path (clone of
https://github.com/opencivicdata/python-legistar-scraper) plus `scrapelib`.

Usage
-----
    python3 sf_legistar.py sponsored "Bilal Mahmood" primary out.json
    python3 sf_legistar.py votes in.json out.json   # in.json: [{"url": ...}, ...]
    python3 sf_legistar.py search "Better Streets" "All Years" out.json
    python3 sf_legistar.py meetings "Budget and Finance Committee" 2026 out.json
    python3 sf_legistar.py agenda "Budget and Finance Committee" 9/2/2026 out.json

The last two exist because a file CANNOT be reached by ID. `LegislationDetail.aspx?ID=n`
without its `GUID=` returns a 19-byte stub, GUIDs are not derivable, and the community
scraper's `searchLegislation` does not work against SF's install — it returns the
`<html>` element when it finds no results grid, so a caller that checks `if results:`
sees success. Every route to a file therefore has to come through a listing that
already carries the link. The sponsor search is one such listing and misses anything
sponsored off-roster; the meeting agenda is the other, and it misses nothing that was
ever heard. Checked 2026-09-04.
"""
import collections
import json
import os
import re
import sys

REPO = os.environ.get('LEGISTAR_SCRAPER_PATH')
if REPO:
    sys.path.insert(0, REPO)

try:
    from legistar.bills import LegistarBillScraper  # noqa: E402
except ImportError:
    # Re-exec under the environment refresh-legistar.sh builds, so that both
    # documented commands work from a bare shell rather than only from the
    # interpreter that happens to have the scraper installed. Run that script
    # once if the cache does not exist yet.
    # A venv's bin/python is a symlink to the base interpreter, so comparing
    # resolved paths against sys.executable says "already there" when it is
    # not. Use an explicit sentinel to stop a re-exec loop instead.
    _venv = os.path.expanduser(
        os.environ.get('CACHE', '~/.cache/sf-legistar')) + '/venv/bin/python'
    if os.path.exists(_venv) and not os.environ.get('SF_LEGISTAR_REEXEC'):
        os.environ['SF_LEGISTAR_REEXEC'] = '1'
        os.execv(_venv, [_venv, os.path.abspath(__file__)] + sys.argv[1:])
    raise SystemExit(
        'cannot import legistar.bills; run scripts/refresh-legistar.sh once to '
        'build the environment, or set LEGISTAR_SCRAPER_PATH and use an '
        'interpreter that has the scraper installed')

RADOPEN = re.compile(r"radopen\('([^']+)'")

# Telerik RadComboBox posts a hidden JSON twin alongside the visible text input.
# Both have to be set or the server ignores the selection.
CLIENT_STATE = ('{{"logEntries":[],"value":"{v}","text":"{v}","enabled":true,'
                '"checkedIndices":[],"checkedItemsTextOverflows":false}}')


class SFLegistar(LegistarBillScraper):
    BASE_URL = 'https://sfgov.legistar.com'
    LEGISLATION_URL = 'https://sfgov.legistar.com/Legislation.aspx'
    CALENDAR_URL = 'https://sfgov.legistar.com/Calendar.aspx'
    TIMEZONE = 'America/Los_Angeles'
    date_format = '%m/%d/%Y'
    VOTE_OPTIONS = {'ayes': 'yes', 'aye': 'yes', 'noes': 'no', 'no': 'no',
                    'absent': 'absent', 'excused': 'excused',
                    'abstain': 'abstain', 'recused': 'excused'}

    # --- 1. sponsor-filtered search -------------------------------------
    def search_by_sponsor(self, sponsor, primary='primary', years='All'):
        """Yield result pages for one sponsor.

        `primary` is 'primary', 'secondary' or 'both' — the form's own three
        options. Primary sponsorship is authorship; 'both' folds in
        co-sponsorship, which is what inflates the count on the person page.
        """
        page = self._advancedSearch(self.lxmlize(self.LEGISLATION_URL))
        payload = {
            'ctl00$ContentPlaceHolder1$lstSponsoredBy': sponsor,
            'ctl00_ContentPlaceHolder1_lstSponsoredBy_ClientState':
                CLIENT_STATE.format(v=sponsor),
            'ctl00$ContentPlaceHolder1$radPrimary': primary,
            'ctl00_ContentPlaceHolder1_lstMax_ClientState': '{"value":"1000000"}',
            'ctl00_ContentPlaceHolder1_lstYearsAdvanced_ClientState':
                '{"value":"%s"}' % years,
            'ctl00$ContentPlaceHolder1$btnSearch': 'Search Legislation',
        }
        payload.update(self.sessionSecrets(page))
        return self.pages(self.LEGISLATION_URL, payload)

    def sponsored(self, sponsor, primary='primary', years='All'):
        for page in self.search_by_sponsor(sponsor, primary, years):
            for leg in self.parseSearchResults(page):
                yield {'file': leg.get('File\xa0#'),
                       'type': leg.get('Type'),
                       'status': leg.get('Status'),
                       'final_action': leg.get('Final\xa0Action'),
                       'title': (leg.get('Title') or '').strip(),
                       'url': leg['url']}

    def sponsor_options(self):
        """Every name the Sponsored-by box will accept, exactly as spelled."""
        page = self._advancedSearch(self.lxmlize(self.LEGISLATION_URL))
        dd = page.xpath("//div[@id='ctl00_ContentPlaceHolder1_lstSponsoredBy_DropDown']")
        if not dd:
            return []
        return [' '.join(li.text_content().split())
                for li in dd[0].xpath(".//ul[contains(@class,'rcbList')]/li")]

    # --- 2. full-text search ---------------------------------------------
    # Legistar's BASIC search box (Legislation.aspx, not the advanced form the
    # sponsor search drives) is the only route that reaches the TEXT of a file
    # rather than its title. It matters here because San Francisco does not
    # file a departmental report as its own matter: reports arrive inside a
    # weekly "Petitions and Communications" bundle whose title enumerates every
    # submission, so the phrase you are hunting is 4,000 characters into one
    # matter's body and invisible to any title-only search.
    #
    # Three switches on the form, and the defaults are wrong for this job:
    #   chkID          on  by default -- file number
    #   chkText        on  by default -- title and body
    #   chkAttachments OFF by default -- the PDFs. Turn it on or a report that
    #                                    exists only as an attached PDF reads
    #                                    as absent.
    #   chkOther       OFF by default -- indexes and notes.
    # The visible button is wired to a Telerik AJAX manager, but btnSearch is a
    # real Button control underneath, so posting it directly works.
    def search_text(self, text, years='All Years', attachments=True,
                    other=True, matter_type=None):
        """Yield result pages for a full-text search of the legislative record."""
        page = self.lxmlize(self.LEGISLATION_URL)
        payload = {
            'ctl00$ContentPlaceHolder1$txtSearch': text,
            'ctl00$ContentPlaceHolder1$chkID': 'on',
            'ctl00$ContentPlaceHolder1$chkText': 'on',
            'ctl00$ContentPlaceHolder1$lstYears': years,
            'ctl00_ContentPlaceHolder1_lstYears_ClientState':
                CLIENT_STATE.format(v=years),
            'ctl00$ContentPlaceHolder1$btnSearch': 'Search Legislation',
        }
        if matter_type:
            payload['ctl00$ContentPlaceHolder1$lstTypeBasic'] = matter_type
            payload['ctl00_ContentPlaceHolder1_lstTypeBasic_ClientState'] = \
                CLIENT_STATE.format(v=matter_type)
        if attachments:
            payload['ctl00$ContentPlaceHolder1$chkAttachments'] = 'on'
        if other:
            payload['ctl00$ContentPlaceHolder1$chkOther'] = 'on'
        payload.update(self.sessionSecrets(page))
        return self.pages(self.LEGISLATION_URL, payload)

    # The basic search returns AT MOST 100 rows and says nothing about the ones
    # it dropped. Measured 2026-09-21: "bicycle" in 2025 answers 100 unfiltered,
    # and 35 + 50 + 15 + 8 = 108 across Ordinance, Resolution, Motion and
    # Hearing alone. The advanced form's `lstMax` box does not exist on this
    # page, so the ClientState key an earlier version posted for it was a no-op
    # that read as a fix. The only lever the page does carry is the type filter.
    _MATTER_TYPES = ('Charter Amendment', 'Communication', 'Discussion',
                     'Hearing', 'Inquiry', 'Motion', 'Ordinance', 'Report',
                     'Resolution')
    CAP = 100

    def _rows(self, text, years, matter_type=None, **kw):
        for page in self.search_text(text, years, matter_type=matter_type, **kw):
            for leg in self.parseSearchResults(page):
                yield {'file': leg.get('File\xa0#'),
                       'type': leg.get('Type'),
                       'status': leg.get('Status'),
                       'final_action': leg.get('Final\xa0Action'),
                       'title': (leg.get('Title') or '').strip(),
                       'url': leg['url']}

    def search_checked(self, text, years='All Years', log=None, **kw):
        """(rows, types still capped). One request when the result fits.

        When it does not, one per matter type, deduplicated by URL. A type that
        is ITSELF at the cap has no further lever on this form — the caller
        decides whether to narrow the years or to accept a short list knowing
        it is short.
        """
        rows = list(self._rows(text, years, **kw))
        if len(rows) < self.CAP:
            return rows, []
        seen, out, still = {}, [], []
        for t in self._MATTER_TYPES:
            got = list(self._rows(text, years, matter_type=t, **kw))
            if log:
                log(t, len(got))
            if len(got) >= self.CAP:
                still.append(t)
            for r in got:
                if r['url'] not in seen:
                    seen[r['url']] = True
                    out.append(r)
        return out, still

    def search(self, text, years='All Years', log=None, **kw):
        """Every matching file, or a loud failure — never a quiet truncation."""
        rows, still = self.search_checked(text, years, log=log, **kw)
        if still:
            raise SystemExit(
                'FAIL: %r in %r is still at the %d-row cap after splitting by '
                'type: %s. The basic search has no other filter, so this result '
                'would be silently short. Search one year at a time instead, or '
                'call search_checked and handle the short list yourself.'
                % (text, years, self.CAP, ', '.join(still)))
        return rows

    # --- 3. meeting calendar and agendas ---------------------------------
    # The calendar's two filters are RadComboBoxes like the sponsor box, so
    # they need the same visible-value-plus-ClientState-twin treatment. Left
    # unset, Calendar.aspx returns only the current week, which is a listing
    # that silently answers a different question than the one asked.
    def meetings(self, body='BOS and Committees', years='All Years'):
        """Yield every meeting of `body` in `years`, newest first."""
        page = self.lxmlize(self.CALENDAR_URL)
        payload = {
            'ctl00$ContentPlaceHolder1$lstYears': years,
            'ctl00_ContentPlaceHolder1_lstYears_ClientState':
                CLIENT_STATE.format(v=years),
            'ctl00$ContentPlaceHolder1$lstBodies': body,
            'ctl00_ContentPlaceHolder1_lstBodies_ClientState':
                CLIENT_STATE.format(v=body),
        }
        payload.update(self.sessionSecrets(page))
        for page in self.pages(self.CALENDAR_URL, payload):
            tbl = page.xpath("//table[contains(@id,'gridCalendar')]")
            if not tbl:
                continue
            for tr in tbl[0].xpath(".//tr[contains(@class,'rgRow') or "
                                   "contains(@class,'rgAltRow')]"):
                tds = tr.xpath('./td')
                if len(tds) < 8:
                    continue
                cell = lambda i: ' '.join(tds[i].text_content().split())  # noqa: E731

                def href(frag):
                    for a in tr.xpath('.//a[@href]'):
                        if frag in a.get('href'):
                            return a.get('href')
                    return None
                yield {'body': cell(0), 'date': cell(1), 'time': cell(3),
                       'location': cell(4),
                       'url': href('MeetingDetail.aspx'),
                       'agenda_pdf': href('View.ashx?M=A'),
                       'minutes_pdf': href('View.ashx?M=M')}

    def agenda(self, meeting_url):
        """Yield the items on one meeting, each with its LegislationDetail URL.

        This is the only route to a file whose sponsor is not on the mirror's
        roster — the reserve-release hearing 260949 among them.
        """
        page = self.lxmlize(meeting_url)
        tbl = page.xpath("//table[contains(@id,'gridMain')]")
        if not tbl:
            return
        for tr in tbl[0].xpath(".//tr[contains(@class,'rgRow') or "
                               "contains(@class,'rgAltRow')]"):
            tds = tr.xpath('./td')
            if len(tds) < 9:
                continue
            cell = lambda i: ' '.join(tds[i].text_content().split())  # noqa: E731
            url = None
            for a in tr.xpath('.//a[@href]'):
                if 'LegislationDetail.aspx' in a.get('href'):
                    url = a.get('href')
                    break
            # Same decoy-href defect as the per-file history grid: the real
            # action-detail URL is in the onclick, not the href.
            detail = None
            for a in tds[9].xpath('.//a[@onclick]'):
                m = RADOPEN.search(a.get('onclick') or '')
                if m:
                    detail = self.BASE_URL + '/' + m.group(1)
                    break
            yield {'file': cell(0), 'version': cell(1), 'name': cell(3),
                   'type': cell(4), 'status': cell(5), 'title': cell(6),
                   'action': cell(7), 'result': cell(8),
                   'url': url, 'detail_url': detail}

    def agenda_for(self, body, date, years=None):
        """Find one meeting by body and M/D/YYYY date, and return its items."""
        years = years or ('All Years' if '/' not in date
                          else date.rsplit('/', 1)[-1])
        want = [m for m in self.meetings(body, years) if m['date'] == date]
        if not want:
            raise SystemExit(
                'FAIL: no %s meeting on %s in the %s calendar. Legistar spells '
                'bodies exactly as its own filter does and dates as M/D/YYYY '
                'with no leading zeros; an unmatched filter returns a listing '
                'rather than an error.' % (body, date, years))
        if len(want) > 1:
            raise SystemExit('FAIL: %d meetings match %s on %s; disambiguate by '
                             'hand.' % (len(want), body, date))
        meeting = want[0]
        items = list(self.agenda(meeting['url']))
        if not items:
            raise SystemExit(
                'FAIL: %s on %s parsed to ZERO agenda items. A meeting with no '
                'items is not a thing that happens, so this is the grid moving '
                'or the page not loading — not an empty agenda. %s'
                % (body, date, meeting['url']))
        return meeting, items

    # --- 4. history and roll calls --------------------------------------
    def history_rows(self, leg_url):
        page = self.lxmlize(leg_url)
        tbl = page.xpath("//table[@id='ctl00_ContentPlaceHolder1_gridLegislation_ctl00']")
        if not tbl:
            return
        rows = tbl[0].xpath(".//tr[contains(@class,'rgRow') or contains(@class,'rgAltRow')]")
        for tr in rows:
            tds = tr.xpath('./td')
            if len(tds) < 6:
                continue
            cell = lambda i: ' '.join(tds[i].text_content().split())  # noqa: E731
            detail = None
            for a in tds[5].xpath('.//a[@onclick]'):
                m = RADOPEN.search(a.get('onclick') or '')
                if m:
                    detail = self.BASE_URL + '/' + m.group(1)
                    break
            yield {'date': cell(0), 'version': cell(1), 'body': cell(2),
                   'action': cell(3), 'result': cell(4), 'detail_url': detail}

    def roll_call(self, history_detail_url):
        page = self.lxmlize(history_detail_url)
        tbl = page.xpath("//table[@id='ctl00_ContentPlaceHolder1_gridVote_ctl00']")
        if not tbl:
            return []
        out = []
        rows = tbl[0].xpath(".//tr[contains(@class,'rgRow') or contains(@class,'rgAltRow')]")
        for tr in rows:
            tds = tr.xpath('./td')
            if len(tds) < 2:
                continue
            person = ' '.join(tds[0].text_content().split())
            raw = ' '.join(tds[1].text_content().split()).lower()
            out.append({'person': person, 'vote': self.VOTE_OPTIONS.get(raw, raw)})
        return out

    def with_votes(self, legs, log=None):
        """Attach every action and its roll call to each record, in place."""
        for rec in legs:
            rec['actions'] = []
            for h in self.history_rows(rec['url']):
                h['votes'] = self.roll_call(h['detail_url']) if h['detail_url'] else []
                rec['actions'].append(h)
            if log:
                log(rec)
        return legs


def _new(rpm=60):
    s = SFLegistar(retry_attempts=2, requests_per_minute=rpm)
    s.verify = False  # the host's chain does not validate under LibreSSL 2.8.3
    return s


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[1]
    s = _new()

    if cmd == 'sponsors':
        for name in s.sponsor_options():
            print(name)
        return 0

    if cmd == 'sponsored':
        sponsor = argv[2]
        primary = argv[3] if len(argv) > 3 else 'primary'
        out = argv[4] if len(argv) > 4 else 'sponsored.json'
        rows = list(s.sponsored(sponsor, primary))
        json.dump(rows, open(out, 'w'), indent=1)
        by_type = collections.Counter(r['type'] for r in rows)
        by_status = collections.Counter(r['status'] for r in rows)
        print(f'{sponsor} ({primary}): {len(rows)} items -> {out}')
        for k, v in by_type.most_common():
            print(f'  type    {k or "(blank)":32s} {v}')
        for k, v in by_status.most_common():
            print(f'  status  {k or "(blank)":32s} {v}')
        return 0

    if cmd == 'search':
        text = argv[2]
        years = argv[3] if len(argv) > 3 else 'All Years'
        out = argv[4] if len(argv) > 4 else 'search.json'
        log = lambda t, n: print(f'  split {t:18s} {n}', flush=True)  # noqa: E731
        # Default is to fail loudly on a result the cap still truncates. A
        # caller sweeping many phrases at once would rather record which ones
        # came back short than stop, so SF_LEGISTAR_ALLOW_SHORT lets it through
        # and writes the capped types beside the rows for it to report.
        if os.environ.get('SF_LEGISTAR_ALLOW_SHORT'):
            rows, still = s.search_checked(text, years, log=log)
            json.dump(still, open(out + '.capped', 'w'))
            if still:
                print(f'  !! still capped in: {", ".join(still)}', flush=True)
        else:
            rows = s.search(text, years, log=log)
        json.dump(rows, open(out, 'w'), indent=1)
        print(f'{text!r} ({years}): {len(rows)} items -> {out}')
        for r in sorted(rows, key=lambda r: r['file'] or ''):
            print(f"  {r['file'] or '':10s} {r['type'] or '':14s} "
                  f"{(r['title'] or '')[:110]}")
        return 0

    if cmd == 'meetings':
        body = argv[2] if len(argv) > 2 else 'BOS and Committees'
        years = argv[3] if len(argv) > 3 else 'All Years'
        out = argv[4] if len(argv) > 4 else 'meetings.json'
        rows = list(s.meetings(body, years))
        if not rows:
            raise SystemExit(
                'FAIL: zero meetings for %r in %r. The calendar filters are '
                'combo boxes that ignore a value they do not recognise and '
                'return a listing anyway, so an empty result usually means a '
                'misspelled body, not a quiet year.' % (body, years))
        json.dump(rows, open(out, 'w'), indent=1)
        print(f'{body} ({years}): {len(rows)} meetings -> {out}')
        for r in rows[:5]:
            print(f"  {r['date']:11s} {r['body']}")
        return 0

    if cmd == 'agenda':
        body, date = argv[2], argv[3]
        out = argv[4] if len(argv) > 4 else 'agenda.json'
        meeting, items = s.agenda_for(body, date)
        json.dump({'meeting': meeting, 'items': items}, open(out, 'w'), indent=1)
        print(f"{meeting['body']} {meeting['date']} {meeting['time']}: "
              f"{len(items)} items -> {out}")
        for it in items:
            print(f"  {it['file']:8s} {it['type']:12s} {it['status']:26s} "
                  f"{it['action']}")
        return 0

    if cmd == 'votes':
        legs = json.load(open(argv[2]))
        out = argv[3] if len(argv) > 3 else 'votes.json'
        tally = collections.defaultdict(collections.Counter)

        def log(rec):
            n = sum(1 for a in rec['actions'] if a['votes'])
            print(f"  {rec.get('file')} {len(rec['actions'])} actions, {n} roll calls",
                  flush=True)

        s.with_votes(legs, log=log)
        for rec in legs:
            for a in rec['actions']:
                for v in a['votes']:
                    tally[v['person']][v['vote']] += 1
        json.dump(legs, open(out, 'w'), indent=1)
        total = sum(1 for r in legs for a in r['actions'] if a['votes'])
        print(f'\n{total} roll calls across {len(legs)} files -> {out}')
        for person, c in sorted(tally.items(), key=lambda kv: -sum(kv[1].values())):
            line = '  '.join(f'{k} {n}' for k, n in c.most_common())
            print(f'  {person:26s} n={sum(c.values()):3d}  {line}')
        return 0

    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
