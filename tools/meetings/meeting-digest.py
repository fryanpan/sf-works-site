#!/usr/bin/env python3
"""Markdown section for Bryan's morning digest: public meetings and events coming up that name a project on Current Projects.

    tools/meetings/meeting-digest.py              # next 14 days
    tools/meetings/meeting-digest.py --days 30

Bryan, 2026-09-29, on where meeting alerts should go: "For now add to my daily
digest that comes each morning from Team Lead". The Team Lead runs this and
pastes its output.

Read-only. It reads site/data/coordination.json, where tools/projects/project-record.py
has already matched each posted agenda item or event (tools/meetings/upcoming-meetings.py)
to the project it names, and it prints the date those listings were read, so a
stale list says so instead of reading as current. It never fetches: refreshing is
the pipeline's job (pipeline/transportation-update.py).
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import datetime as dt
import json
import os

ROOT = paths.ROOT
SITE = "https://sf-works.org/transportation/bike/projects"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--today", help="YYYY-MM-DD, for testing")
    args = ap.parse_args()
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    end = today + dt.timedelta(days=args.days)

    with open(os.path.join(ROOT, "site", "data", "coordination.json")) as f:
        d = json.load(f)
    read = d["upcoming"]["read"]
    rows = []
    for p in d["projects"]:
        for m in p.get("meetings") or []:
            day = dt.date.fromisoformat(m["date"])
            if today <= day <= end:
                rows.append((m["date"], m.get("time") or "", p, m))
    rows.sort(key=lambda r: (r[0], r[1], r[2]["name"]))
    pending = [a for a in d["upcoming"].get("agendaPending") or []
               if today <= dt.date.fromisoformat(a["date"]) <= end]

    out = [f"### SF Works: meetings on listed street projects, next {args.days} days"]
    age = (today - dt.date.fromisoformat(read)).days
    stale = f" — {age} days old; the list may miss newer agendas" if age > 2 else ""
    out.append(f"Agendas and events read {read}{stale}.")
    if not rows:
        out.append("- No posted meeting or event names a listed project.")
    for date, time, p, m in rows:
        when = dt.date.fromisoformat(date).strftime("%a %-d %b") + (f", {time}" if time else "")
        item = f", item {m['item']}" if m.get("item") else ""
        out.append(f"- **{when}**: [{m['title']}]({m['url']}) ({m['body']}{item}), "
                   f"names [{p['name']}]({SITE}/{p['slug']}/)")
    for a in pending:
        when = dt.date.fromisoformat(a["date"]).strftime("%a %-d %b")
        out.append(f"- **{when}**: [{a['body']}]({a['url']}), agenda not posted yet; check back.")
    print("\n".join(out))


if __name__ == "__main__":
    main()
