#!/usr/bin/env python3
"""One page per project: the plan, the dates, the gaps, and the public record.

    tools/projects/project-detail-mockup.py     # → out/project-detail/index.html

Bryan asked for this on 2026-09-22, after the previous attempt handed him raw
record rows: "I was expecting when I click on a project to see a polished
project page that highlights at the top level briefly what DPW's plan is, key
timeline dates, and what are the gaps or unknowns vs. biking and rolling plan?
And then an activity trail of each key event in the public record. With readable
details." On an iPad and a phone, picking from the upcoming projects.

So the page has four parts, in his order: what the city says the project is,
when it happens, what the Biking and Rolling Plan asks for on those blocks that
the project does not mention, and then the dated trail of hearings, board items
and ordinances with every source linked.

The gap section is the point of the tool and the part that has to be honest. It
never says the city is not building a bikeway. It says the plan draws a facility
on these blocks, the published record does not mention bike work, and that is
the determination Public Works Code §2.4.13 requires. Where no record was found
it says no record was found, rather than leaving a count to be misread.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, paths.LIB)
from sfdata import fetch  # noqa: E402
from streetindex import BlockIndex  # noqa: E402

ROOT = paths.ROOT
OUT = os.path.join(ROOT, "out", "project-detail")
STREETS = os.path.join(ROOT, "site", "data", "streets.json")
RECORDS = os.path.join(ROOT, "out", "project-record", "projects.json")
PROJECT_BLOCKS = os.path.join(ROOT, "out", "project-record", "project-blocks.json")

TODAY = dt.date.today()
FEED = "btxj-k9uh"
PAGE_SIZE = 20

# The Google Maps browser key is read from this machine's keychain at build
# time and written only into the generated page, which is gitignored. It is
# never in a commit. The page draws a plain map of the project lines first and
# lets Google's tiles replace it, so a key that is restricted to sf-works.org
# and refused on the mockup host still leaves a readable map behind.
KEYCHAIN_SERVICE = "claude-workspaces-secret.google-maps-browser-key"


def maps_key():
    try:
        raw = subprocess.run(
            ["security", "find-generic-password", "-a", "claude-workspaces",
             "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        import base64
        return base64.b64decode(raw).decode().strip()
    except (subprocess.CalledProcessError, ValueError):
        return ""


def parse_cnns(value):
    """The feed puts a Python list literal in `cnn` when a row spans blocks."""
    raw = str(value or "").strip()
    if not raw:
        return set()
    if raw.startswith("["):
        try:
            return {str(int(float(x))) for x in json.loads(raw.replace("'", '"'))}
        except (ValueError, TypeError):
            return set()
    try:
        return {str(int(float(raw)))}
    except ValueError:
        return set()


def feed_blocks():
    """Every block each feed project touches, by its DotMaps id."""
    out = {}
    for r in fetch(FEED, select="dotmapsid,cnn", floor=1000).rows:
        pid = str(r.get("dotmapsid") or "").strip()
        if pid:
            out.setdefault(pid, set()).update(parse_cnns(r.get("cnn")))
    return out

# Ordered categories, sampled from one sequential ramp so the order is visible
# and lightness carries it. Nothing here is red: red is for links and emphasis,
# and a saturated red on "second best" reads as an alarm the data did not raise.
KINDS = {
    "hearing": ("Engineering hearing", "seq-1"),
    "board": ("SFMTA Board", "seq-2"),
    "supervisors": ("Board of Supervisors", "seq-3"),
    "sfpuc": ("SFPUC Commission", "seq-3"),
}


def esc(s):
    return html.escape(str(s if s is not None else ""))


def when(days):
    """A duration a reader can hold in their head."""
    if days is None:
        return "no date"
    if days < 0:
        return f"{-days} days ago"
    if days == 0:
        return "today"
    if days < 60:
        return f"in {days} days"
    months = round(days / 30.4)
    return f"in {months} months" if months < 24 else f"in {days / 365.25:.1f} years"


def load():
    streets = json.load(open(STREETS))
    records = {p["id"]: p for p in json.load(open(RECORDS))["projects"]}
    # Public Works project pages are NOT offered here. They were, matched on a
    # shared street name, and a check on 2026-09-22 found none of them
    # related: "the method is broken and needs work." A street name is not a
    # place, and scripts/research/dpw-project-join.py measures that join at one
    # defensible match in three. They come back when a match survives a check
    # in space (overlapping blocks) and time, and a graded sample says how
    # often it is right.
    blocks = feed_blocks()
    out = []
    for p in streets["upcoming"]["projects"]:
        if not p.get("segmentsOnPlan"):
            continue
        rec = records.get(f"dotmaps:{p['id']}", {})
        trail = sorted(
            # Co-located records are shown too, because for a paving job "a
            # bike-share dock was legislated on this block" is exactly the
            # kind of thing worth knowing before the street is opened. They
            # are labelled by their relation, never presented as the project's
            # own decision, and they do not count toward "has a record".
            (r for r in rec.get("records", [])
             if r.get("grade") in ("exact", "strong", "probable", "co-located")),
            key=lambda r: r.get("date") or "",
            reverse=True,
        )
        out.append({**p, "trail": trail, "cnns": sorted(blocks.get(str(p["id"]), ()))})

    # Sorted by start date, as Bryan asked on 2026-09-22 ("20 top projects at
    # a time sorted by start date"). Each row still shows time to the END,
    # because that is when it becomes too late to ask.
    # SFMTA's own bike projects, beside the Public Works jobs. Bryan asked for
    # "source links to all related DPW and MTA project pages"; these are the
    # MTA half. They carry no feed dates, so the timeline on their own page
    # stands in, and they carry no plan-gap figures because the gap question
    # is asked of the paving job, not the bikeway.
    pblocks = (json.load(open(PROJECT_BLOCKS))["projects"]
               if os.path.exists(PROJECT_BLOCKS) else {})
    sfmta = []
    for rid, rec in records.items():
        if not rid.startswith("sfmta:") or not rec.get("bike"):
            continue
        node = rid.split(":", 1)[1]
        pb = pblocks.get(node, {})
        trail = sorted(
            (r for r in rec.get("records", [])
             if r.get("grade") in ("exact", "strong", "probable", "co-located")),
            key=lambda r: r.get("date") or "", reverse=True)
        tl = [r for r in trail if r.get("kind") == "project-page"]
        sfmta.append({
            "id": rid.replace(":", "-"), "kind": "sfmta", "name": rec["name"],
            "agency": "SFMTA", "phase": rec.get("phase"), "page": rec.get("page"),
            "streets": [s.replace("st", " st").strip() if False else s for s in pb.get("streets", [])][:6],
            "cnns": sorted(pb.get("cnns", ())), "segments": len(pb.get("cnns", ())),
            "start": None, "end": None, "daysToStart": None, "daysToEnd": None,
            "segmentsOnPlan": 0, "scope": "bike work named", "plannedFacility": [],
            "segmentsWithBikeway": 0, "segmentsLocked": 0, "trail": trail,
            "timeline": tl, "documents": rec.get("pageDocuments") or [],
        })

    # Each Public Works job: the SFMTA projects on its blocks. Block overlap is
    # the right test HERE — the claim is "these two are on the same ground",
    # which is exactly what an advocate wants to know before the street opens.
    by_cnn = {}
    for m in sfmta:
        for c in m["cnns"]:
            by_cnn.setdefault(c, set()).add(m["id"])
    names = {m["id"]: m for m in sfmta}
    for p in out:
        hits = collections.Counter()
        for c in p["cnns"]:
            for mid in by_cnn.get(c, ()):
                hits[mid] += 1
        p["kind"] = "dpw"
        p["nearby"] = [{"id": mid, "name": names[mid]["name"], "blocks": n,
                        "page": names[mid]["page"]} for mid, n in hits.most_common(5)]

    out = out + sfmta
    out.sort(key=lambda p: (p["start"] is None, p["start"] or "", p["name"]))
    return streets, out


def card(p):
    """The list row. Everything here has to survive a phone's width."""
    facility = ", ".join(p.get("plannedFacility") or []) or "—"
    # Whether this project has a public record is the first thing a reader wants
    # from the list, because 201 of the 212 do not and scanning for the ones
    # that do is otherwise a click each. It is stated, not colour-coded: a
    # coloured dot alone would rank without measuring.
    n = len(p["trail"])
    evidence = (
        f"{n} record{'' if n == 1 else 's'}" if n else "no record found"
    )
    lead = when(p["daysToEnd"]) if p.get("kind") != "sfmta" else (p.get("phase") or "SFMTA project")
    return f"""<button class="row" data-id="{esc(p['id'])}">
  <span class="row-when">{esc(lead)} · {esc(evidence)}</span>
  <span class="row-name">{esc(p['name'])}</span>
  <span class="row-meta">{esc(p['agency'])} · {p['segmentsOnPlan']} plan blocks · {esc(facility)}</span>
</button>"""


def detail(p):
    facility = ", ".join(p.get("plannedFacility") or []) or "a facility"
    silent = p["scope"] == "the record does not say"

    if p.get("kind") == "sfmta":
        return detail_sfmta(p)

    # 1. What the city says this is.
    plan = f"""<h3>What the city says it is</h3>
<p class="lede">{esc(p['name'])}</p>
<p>{esc(p['agency'])}, in <strong>{esc(p['phase'] or 'an unrecorded phase')}</strong>.
It covers {p['segments']} block{'' if p['segments'] == 1 else 's'} on
{esc(', '.join(p.get('streets') or []) or 'streets the feed does not name')}.</p>"""

    # 2. The dates.
    dates = f"""<h3>When</h3>
<dl class="dates">
  <div><dt>Starts</dt><dd>{esc(p['start'] or 'not published')}<span>{esc(when(p['daysToStart']))}</span></dd></div>
  <div><dt>Ends</dt><dd>{esc(p['end'] or 'not published')}<span>{esc(when(p['daysToEnd']))}</span></dd></div>
</dl>
<p class="note">The feed publishes a start and an end, not a paving-then-striping
sequence. Bike infrastructure goes in near the end, before restriping, so the end
date is the closest published thing to the moment it becomes too late to ask.</p>"""

    # 3. The gap. The section the tool exists for, and the one that has to be
    #    careful: it reports what the record does not say, never what the city
    #    will or will not build.
    if silent:
        gap = f"""<h3>The gap</h3>
<p class="gap">The 2025 Biking and Rolling Plan draws <strong>{esc(facility)}</strong> on
{p['segmentsOnPlan']} of these blocks. Nothing in the published record for this
project mentions bike work.</p>
<p>That is not a finding that the city is leaving the bikeway out. It is the
determination Public Works Code §2.4.13 asks for, and the published record does
not contain it. {p['segmentsWithBikeway']} of the blocks already carry a bikeway
today; {p['segmentsLocked']} sit under a paving moratorium.</p>"""
    else:
        gap = f"""<h3>The gap</h3>
<p class="gap ok">The record names {esc(p['scope'])}, on blocks where the plan draws
{esc(facility)}. Nothing to ask about here.</p>"""

    # 4. The trail.
    if p["trail"]:
        rows = []
        for r in p["trail"]:
            label, tone = KINDS.get(r["kind"], (r["kind"], "seq-3"))
            title = re.sub(r"\s+", " ", r.get("title") or "").strip()
            rows.append(f"""<li class="event {tone}">
  <span class="ev-date">{esc(r.get('date') or 'undated')}</span>
  <span class="ev-kind">{esc(label)}</span>
  <p class="ev-title">{esc(title[:300])}{'…' if len(title) > 300 else ''}</p>
  <p class="ev-outcome">{esc(r.get('decision') or 'no decision recorded')}</p>
  <p class="ev-why">{esc((r.get('relation') or '').capitalize())}. Matched on
     {esc(', '.join(r.get('matchedOn') or []) or 'this corridor')} —
     {esc(r.get('grade'))}.
     <a href="{esc(r.get('url'))}">Read the source</a></p>
</li>""")
        trail = f"""<h3>The public record</h3>
<p class="note">{len(p['trail'])} event{'' if len(p['trail']) == 1 else 's'}, newest
first. Each says why it is here and links the city's own document.</p>
<ol class="trail">{''.join(rows)}</ol>"""
    else:
        trail = """<h3>The public record</h3>
<p class="empty"><strong>No record found.</strong> Nothing in the engineering
hearings, the SFMTA Board agendas or the Board of Supervisors file matched this
project to a standard this page would defend. That means no evidence was found,
not that no decision was taken — the join between a project and a document is
made on street names, and it is the weakest part of this tool.</p>"""

    nearby = ""
    if p.get("nearby"):
        items = "".join(
            f'<li><a href="#" data-go="{esc(n["id"])}">{esc(n["name"])}</a>'
            f'<span>{n["blocks"]} shared block{"s" if n["blocks"] != 1 else ""} · '
            f'<a href="{esc(n["page"])}">SFMTA page</a></span></li>' for n in p["nearby"])
        nearby = f"""<h3>SFMTA projects on these blocks</h3>
<p class="note">Same ground, by the city's own block ids. That is a statement about place,
not that the two are one project.</p>
<ul class="pages">{items}</ul>"""

    return f"""<article class="detail" id="p-{esc(p['id'])}" hidden>
{plan}{dates}{gap}{nearby}{trail}
<p class="src">Project record: <a href="https://data.sf.gov/resource/btxj-k9uh.json?dotmapsid={esc(p['id'])}">the interagency coordination feed</a>.</p>
</article>"""


def detail_sfmta(p):
    """An SFMTA bike project: its own page's timeline, then its record."""
    plan = f"""<h3>What the city says it is</h3>
<p class="lede">{esc(p['name'])}</p>
<p>SFMTA, in <strong>{esc(p['phase'] or 'an unrecorded phase')}</strong>.
Its published shape covers {p['segments']} block{'' if p['segments'] == 1 else 's'}
on {esc(', '.join(p['streets']) or 'streets its shape does not name')}.
<a href="{esc(p['page'])}">The project page</a>.</p>"""

    if p["timeline"]:
        steps = "".join(
            f'<li><span class="ev-date">{esc(t.get("when") or "")}</span> '
            f'<span class="ev-kind">{esc(t.get("decision") or "")}</span>'
            f'<p class="ev-title">{esc(t.get("title") or "")}</p></li>' for t in p["timeline"])
        dates = f"""<h3>When, in the project's own words</h3>
<p class="note">The timeline SFMTA publishes on the project page. Seasons, not dates,
because that is what the department publishes.</p>
<ol class="trail">{steps}</ol>"""
    else:
        dates = """<h3>When</h3><p class="empty">The project page publishes no timeline.</p>"""

    events = [r for r in p["trail"] if r.get("kind") != "project-page"]
    if events:
        rows = []
        for r in events:
            label, tone = KINDS.get(r["kind"], (r["kind"], "seq-3"))
            title = re.sub(r"\s+", " ", r.get("title") or "").strip()
            rows.append(f"""<li class="event {tone}">
  <span class="ev-date">{esc(r.get('date') or 'undated')}</span>
  <span class="ev-kind">{esc(label)}</span>
  <p class="ev-title">{esc(title)}</p>
  <p class="ev-outcome">{esc(r.get('decision') or '')}</p>
  <p class="ev-why">{esc((r.get('relation') or '').capitalize())}.
     <a href="{esc(r.get('url'))}">Read the source</a></p>
</li>""")
        trail = f"""<h3>The public record</h3>
<p class="note">{len(events)} event{'' if len(events) == 1 else 's'}, newest first.</p>
<ol class="trail">{''.join(rows)}</ol>"""
    else:
        trail = """<h3>The public record</h3>
<p class="empty"><strong>No record found</strong> beyond the project page itself.</p>"""

    docs = ""
    if p["documents"]:
        items = "".join(f'<li><a href="{esc(d["url"])}">{esc(d["title"])}</a></li>'
                        for d in p["documents"][:12])
        docs = f"""<h3>Documents on the project page</h3><ul class="pages">{items}</ul>"""

    return f"""<article class="detail" id="p-{esc(p['id'])}" hidden>
{plan}{dates}{trail}{docs}
</article>"""


CSS = """
:root {
  --bg: #fbfaf8; --fg: #23201d; --muted: #6a635c; --line: #e3ded7;
  --card: #ffffff; --accent: #9c3b2e;
  --seq-3: #2f7d76; --seq-2: #c8a25e; --seq-1: #9c5f3c;
  --seq-3-soft: #e6f0ef; --seq-2-soft: #f7f0e2; --seq-1-soft: #f4eae3;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #17151a; --fg: #ece7e1; --muted: #a49c94; --line: #322d36;
    --card: #201d24; --accent: #e08a7a;
    --seq-3: #7fc9bd; --seq-2: #d8b877; --seq-1: #c98e66;
    --seq-3-soft: #1d2f2d; --seq-2-soft: #302a1e; --seq-1-soft: #2f241d;
  }
}
:root[data-theme="dark"] {
  --bg: #17151a; --fg: #ece7e1; --muted: #a49c94; --line: #322d36;
  --card: #201d24; --accent: #e08a7a;
  --seq-3: #7fc9bd; --seq-2: #d8b877; --seq-1: #c98e66;
  --seq-3-soft: #1d2f2d; --seq-2-soft: #302a1e; --seq-1-soft: #2f241d;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font: 16px/1.55 ui-sans-serif, -apple-system, "Segoe UI", system-ui, sans-serif;
  -webkit-text-size-adjust: 100%;
}
header { padding: 20px 16px 12px; border-bottom: 1px solid var(--line); }
h1 { margin: 0 0 4px; font-size: 1.35rem; letter-spacing: -0.01em; }
header p { margin: 0; color: var(--muted); font-size: .92rem; max-width: 64ch; }
.wrap { display: grid; gap: 0; }
@media (min-width: 860px) {
  .wrap { grid-template-columns: 22rem 1fr; align-items: start; }
  .side { border-right: 1px solid var(--line); height: calc(100vh - 92px); overflow-y: auto; }
}
.side { min-width: 0; }
.list { padding: 8px; }
.map { position: relative; height: 260px; background: var(--card); border-bottom: 1px solid var(--line); }
@media (min-width: 860px) { .map { height: 320px; } }
.map canvas { position: absolute; inset: 0; width: 100%; height: 100%; }
.map .gm { position: absolute; inset: 0; }
.pager { display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 8px 10px; border-bottom: 1px solid var(--line); font-size: .88rem; color: var(--muted); }
.pager button { background: var(--card); color: var(--fg); border: 1px solid var(--line);
  border-radius: 6px; padding: 6px 10px; font: inherit; font-size: .88rem; cursor: pointer; }
.pager button:disabled { opacity: .4; cursor: default; }
.row[hidden] { display: none; }
.pages { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
.pages li { display: flex; gap: 10px; justify-content: space-between; align-items: baseline; flex-wrap: wrap;
  background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; }
.pages span { color: var(--muted); font-size: .82rem; }
.row {
  display: grid; gap: 2px; width: 100%; text-align: left; cursor: pointer;
  background: none; border: 0; border-bottom: 1px solid var(--line);
  padding: 12px 10px; color: inherit; font: inherit;
}
.row:hover, .row:focus-visible { background: var(--card); }
.row[aria-current="true"] { background: var(--card); box-shadow: inset 3px 0 0 var(--accent); }
.row-when { font-size: .78rem; letter-spacing: .04em; text-transform: uppercase; color: var(--muted); }
.row-name { font-weight: 600; }
.row-meta { font-size: .82rem; color: var(--muted); }
.pane { padding: 18px 16px 48px; min-width: 0; }
h3 { margin: 26px 0 8px; font-size: .78rem; letter-spacing: .09em; text-transform: uppercase; color: var(--muted); }
h3:first-child { margin-top: 0; }
.lede { font-size: 1.25rem; font-weight: 600; margin: 0 0 6px; line-height: 1.3; }
p { margin: 0 0 10px; max-width: 68ch; }
.note, .src { color: var(--muted); font-size: .88rem; }
.dates { display: grid; gap: 10px; margin: 0 0 10px; }
@media (min-width: 520px) { .dates { grid-template-columns: 1fr 1fr; } }
.dates > div { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; }
dt { font-size: .75rem; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
dd { margin: 2px 0 0; font-variant-numeric: tabular-nums; font-weight: 600; }
dd span { display: block; font-weight: 400; color: var(--muted); font-size: .86rem; }
.gap { border-left: 4px solid var(--seq-1); background: var(--seq-1-soft); padding: 12px 14px; border-radius: 0 8px 8px 0; }
.gap.ok { border-left-color: var(--seq-3); background: var(--seq-3-soft); }
.empty { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px; }
.trail { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.event { background: var(--card); border: 1px solid var(--line); border-left: 4px solid var(--line); border-radius: 0 8px 8px 0; padding: 12px 14px; }
.event.seq-1 { border-left-color: var(--seq-1); }
.event.seq-2 { border-left-color: var(--seq-2); }
.event.seq-3 { border-left-color: var(--seq-3); }
.ev-date { font-variant-numeric: tabular-nums; font-weight: 600; }
.ev-kind { color: var(--muted); font-size: .82rem; margin-left: 8px; }
.ev-title { margin: 6px 0 4px; }
.ev-outcome { margin: 0 0 6px; font-weight: 600; }
.ev-why { margin: 0; color: var(--muted); font-size: .85rem; }
a { color: var(--accent); }
"""

JS = """
const rows = [...document.querySelectorAll('.row')];
const panes = [...document.querySelectorAll('.detail')];
let page = 0, current = null;
const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));

function visible() { return rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE); }

function show(id) {
  current = id;
  panes.forEach(d => { d.hidden = d.id !== 'p-' + id; });
  rows.forEach(r => r.setAttribute('aria-current', String(r.dataset.id === id)));
  draw();
  if (window.matchMedia('(max-width: 859px)').matches) {
    document.querySelector('.pane').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

function paginate() {
  rows.forEach((r, i) => { r.hidden = Math.floor(i / PAGE_SIZE) !== page; });
  document.getElementById('prev').disabled = page === 0;
  document.getElementById('next').disabled = page >= pages - 1;
  const first = page * PAGE_SIZE + 1, last = Math.min(rows.length, (page + 1) * PAGE_SIZE);
  document.getElementById('where').textContent = `${first}–${last} of ${rows.length}, by start date`;
  const v = visible();
  if (!v.some(r => r.dataset.id === current) && v.length) show(v[0].dataset.id); else draw();
}
document.getElementById('prev').addEventListener('click', () => { page--; paginate(); });
document.getElementById('next').addEventListener('click', () => { page++; paginate(); });
rows.forEach(r => r.addEventListener('click', () => show(r.dataset.id)));
document.addEventListener('click', e => {
  const a = e.target.closest('a[data-go]');
  if (!a) return;
  e.preventDefault();
  const i = rows.findIndex(r => r.dataset.id === a.dataset.go);
  if (i >= 0) { page = Math.floor(i / PAGE_SIZE); paginate(); show(a.dataset.go); }
});

// --- The plain map. Always drawn: the projects on this page as lines, the
// selected one emphasised. It is what a reader sees when Google's tiles are
// refused (a key restricted to sf-works.org is refused on the mockup host)
// and it is what is under the tiles when they are not.
const canvas = document.getElementById('fallback');
const tone = getComputedStyle(document.documentElement);
function bounds(ids) {
  let minX = 1e9, minY = 1e9, maxX = -1e9, maxY = -1e9, any = false;
  ids.forEach(id => (GEOM[id] || []).forEach(ln => ln.forEach(([x, y]) => {
    any = true; minX = Math.min(minX, x); maxX = Math.max(maxX, x);
    minY = Math.min(minY, y); maxY = Math.max(maxY, y);
  })));
  return any ? { minX, minY, maxX, maxY } : null;
}
function draw() {
  if (gmap) { drawGoogle(); return; }
  const ids = visible().map(r => r.dataset.id);
  const b = bounds(ids);
  const w = canvas.clientWidth, h = canvas.clientHeight;
  canvas.width = w * devicePixelRatio; canvas.height = h * devicePixelRatio;
  const ctx = canvas.getContext('2d');
  ctx.scale(devicePixelRatio, devicePixelRatio);
  ctx.clearRect(0, 0, w, h);
  if (!b) { ctx.fillStyle = tone.getPropertyValue('--muted'); ctx.font = '13px system-ui';
    ctx.fillText('No block geometry for the projects on this page.', 12, 24); return; }
  // Fit with a margin; correct longitude for latitude so blocks are not squashed.
  const cosLat = Math.cos((b.minY + b.maxY) / 2 * Math.PI / 180);
  const sx = (b.maxX - b.minX) * cosLat || 1e-6, sy = (b.maxY - b.minY) || 1e-6;
  const k = Math.min((w - 32) / sx, (h - 32) / sy);
  const px = ([x, y]) => [16 + (x - b.minX) * cosLat * k + ((w - 32) - sx * k) / 2,
                          16 + (b.maxY - y) * k + ((h - 32) - sy * k) / 2];
  const line = (id, width, color) => {
    ctx.lineWidth = width; ctx.strokeStyle = color; ctx.lineCap = 'round';
    (GEOM[id] || []).forEach(ln => { ctx.beginPath(); ln.map(px).forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); ctx.stroke(); });
  };
  ids.forEach(id => id !== current && line(id, 3, tone.getPropertyValue('--seq-2')));
  if (current) line(current, 6, tone.getPropertyValue('--accent'));
  ctx.fillStyle = tone.getPropertyValue('--muted'); ctx.font = '12px system-ui';
  ctx.fillText('Projects on this page. Selected in red. No basemap: Google tiles were not loaded.', 12, h - 10);
}
window.addEventListener('resize', draw);

// --- Google Maps, when the key is accepted. gm_authFailure is Google's own
// hook for a refused key; when it fires the canvas stays and nothing breaks.
let gmap = null, polylines = [];
window.gm_authFailure = () => { gmap = null; document.querySelectorAll('.map .gm').forEach(e => e.remove()); draw(); };
window.gmReady = () => {
  const el = document.createElement('div'); el.className = 'gm';
  document.getElementById('map').appendChild(el);
  gmap = new google.maps.Map(el, { center: { lat: 37.76, lng: -122.44 }, zoom: 12,
    mapTypeControl: false, streetViewControl: false, fullscreenControl: false,
    styles: [{ featureType: 'poi', stylers: [{ visibility: 'off' }] }] });
  drawGoogle();
};
function drawGoogle() {
  polylines.forEach(p => p.setMap(null)); polylines = [];
  const ids = visible().map(r => r.dataset.id);
  const b = bounds(ids);
  const accent = tone.getPropertyValue('--accent').trim(), other = tone.getPropertyValue('--seq-2').trim();
  ids.forEach(id => (GEOM[id] || []).forEach(ln => {
    const p = new google.maps.Polyline({ path: ln.map(([x, y]) => ({ lat: y, lng: x })),
      strokeColor: id === current ? accent : other, strokeWeight: id === current ? 6 : 3,
      strokeOpacity: id === current ? 1 : .8, zIndex: id === current ? 2 : 1, map: gmap });
    p.addListener('click', () => show(id)); polylines.push(p);
  }));
  if (b) gmap.fitBounds(new google.maps.LatLngBounds({ lat: b.minY, lng: b.minX }, { lat: b.maxY, lng: b.maxX }), 24);
}

paginate();
"""


def geometry(projects):
    """Each project's block lines, rounded to 5 decimals — about a metre."""
    idx = BlockIndex()
    out = {}
    for p in projects:
        lines = idx.geometry(p["cnns"])
        if lines:
            out[str(p["id"])] = [[[round(x, 5), round(y, 5)] for x, y in ln] for ln in lines]
    return out


def main():
    streets, projects = load()
    geom = geometry(projects)
    key = maps_key()
    os.makedirs(OUT, exist_ok=True)
    dpw = [p for p in projects if p.get("kind") != "sfmta"]
    mta = [p for p in projects if p.get("kind") == "sfmta"]
    silent = sum(1 for p in dpw if p["scope"] == "the record does not say")
    with_trail = sum(1 for p in projects
                     if any(r["grade"] != "co-located" for r in p["trail"]))

    doc = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Projects on the plan's network</title>
<style>{CSS}</style>
</head><body>
<header>
  <h1>Projects on the plan's network</h1>
  <p>{len(dpw)} projects in Public Works' coordination feed touch blocks where
  the 2025 Biking and Rolling Plan draws a bikeway; {silent} say nothing about bike
  work. Beside them, SFMTA's {len(mta)} bike projects, each with the record its own
  page carries. {with_trail} of the {len(projects)} carry a public record this page
  would defend. Twenty at a time, by start date; SFMTA projects, which publish no
  feed dates, follow. Data read {esc(TODAY.isoformat())}.</p>
</header>
<div class="wrap">
  <nav class="side">
    <div id="map" class="map" aria-label="Map of the projects on this page">
      <canvas id="fallback"></canvas>
    </div>
    <div class="pager">
      <button id="prev" type="button">‹ Earlier</button>
      <span id="where"></span>
      <button id="next" type="button">Later ›</button>
    </div>
    <div class="list">{''.join(card(p) for p in projects)}</div>
  </nav>
  <main class="pane">{''.join(detail(p) for p in projects)}</main>
</div>
<script>
const GEOM = {json.dumps(geom, separators=(",", ":"))};
const PAGE_SIZE = {PAGE_SIZE};
{JS}
</script>
{f'<script async src="https://maps.googleapis.com/maps/api/js?key={esc(key)}&callback=gmReady&v=weekly"></script>' if key else ''}
</body></html>"""

    path = os.path.join(OUT, "index.html")
    with open(path, "w") as fh:
        fh.write(doc)
    drawn = sum(1 for p in projects if str(p["id"]) in geom)
    print(
        f"project-detail: {len(dpw)} Public Works + {len(mta)} SFMTA projects, {silent} with no bike scope "
        f"published, {with_trail} with a record, {drawn} drawn on the map, "
        f"Google key {'present' if key else 'ABSENT — plain map only'} → {path}"
    )


if __name__ == "__main__":
    main()
